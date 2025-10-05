"""
Security monitoring and alerting system for crash game backend
Tracks security events and provides real-time monitoring capabilities
"""

import time
import json
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import redis.asyncio as redis
from logging_config import get_security_logger

@dataclass
class SecurityEvent:
    """Security event data structure"""
    timestamp: float
    event_type: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    source_ip: str
    user_id: Optional[str]
    endpoint: Optional[str]
    details: Dict[str, Any]
    resolved: bool = False

class SecurityMetrics:
    """Tracks security metrics and patterns"""
    
    def __init__(self):
        self.failed_auth_attempts = defaultdict(int)  # IP -> count
        self.rate_limit_violations = defaultdict(int)  # IP -> count
        self.suspicious_patterns = defaultdict(list)  # pattern -> events
        self.recent_events = deque(maxlen=1000)  # Last 1000 events
        
    def add_event(self, event: SecurityEvent):
        """Add a security event to metrics"""
        self.recent_events.append(event)
        
        # Track specific patterns
        if event.event_type == "auth_failure":
            self.failed_auth_attempts[event.source_ip] += 1
        elif event.event_type == "rate_limit_exceeded":
            self.rate_limit_violations[event.source_ip] += 1
    
    def get_suspicious_ips(self, window_minutes: int = 10) -> List[str]:
        """Get IPs with suspicious activity in the time window"""
        cutoff_time = time.time() - (window_minutes * 60)
        suspicious_ips = set()
        
        for event in self.recent_events:
            if event.timestamp < cutoff_time:
                continue
                
            # Multiple failed auth attempts
            if (event.event_type == "auth_failure" and 
                self.failed_auth_attempts[event.source_ip] >= 5):
                suspicious_ips.add(event.source_ip)
            
            # Rate limit violations
            if (event.event_type == "rate_limit_exceeded" and 
                self.rate_limit_violations[event.source_ip] >= 3):
                suspicious_ips.add(event.source_ip)
        
        return list(suspicious_ips)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of security metrics"""
        now = time.time()
        last_hour = now - 3600
        last_day = now - 86400
        
        hour_events = [e for e in self.recent_events if e.timestamp > last_hour]
        day_events = [e for e in self.recent_events if e.timestamp > last_day]
        
        return {
            "total_events": len(self.recent_events),
            "events_last_hour": len(hour_events),
            "events_last_day": len(day_events),
            "failed_auth_attempts": dict(self.failed_auth_attempts),
            "rate_limit_violations": dict(self.rate_limit_violations),
            "suspicious_ips": self.get_suspicious_ips(),
            "event_types_last_hour": self._count_event_types(hour_events),
            "severity_breakdown": self._count_by_severity(day_events)
        }
    
    def _count_event_types(self, events: List[SecurityEvent]) -> Dict[str, int]:
        """Count events by type"""
        counts = defaultdict(int)
        for event in events:
            counts[event.event_type] += 1
        return dict(counts)
    
    def _count_by_severity(self, events: List[SecurityEvent]) -> Dict[str, int]:
        """Count events by severity"""
        counts = defaultdict(int)
        for event in events:
            counts[event.severity] += 1
        return dict(counts)

class SecurityMonitor:
    """Main security monitoring system"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.security_logger = get_security_logger()
        self.metrics = SecurityMetrics()
        self.alert_thresholds = {
            "failed_auth_per_ip": 10,
            "rate_limit_violations_per_ip": 5,
            "events_per_minute": 100,
            "critical_events_per_hour": 5
        }
        self.monitoring_active = True
        
    async def log_security_event(
        self,
        event_type: str,
        severity: str,
        source_ip: str,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log a security event"""
        event = SecurityEvent(
            timestamp=time.time(),
            event_type=event_type,
            severity=severity,
            source_ip=source_ip,
            user_id=user_id,
            endpoint=endpoint,
            details=details or {}
        )
        
        # Add to metrics
        self.metrics.add_event(event)
        
        # Store in Redis for persistence
        await self._store_event_in_redis(event)
        
        # Log using security logger
        self.security_logger.logger.info(
            f"Security event: {event_type} ({severity}) from {source_ip}",
            extra={
                'security_event': event_type,
                'security_level': severity,
                'source_ip_masked': True,
                'endpoint': endpoint
            }
        )
        
        # Check for alerts
        await self._check_alerts(event)
    
    async def _store_event_in_redis(self, event: SecurityEvent):
        """Store security event in Redis"""
        try:
            key = f"security_event:{int(event.timestamp * 1000)}"
            value = json.dumps(asdict(event))
            await self.redis.setex(key, 86400, value)  # Store for 24 hours
        except Exception as e:
            self.security_logger.logger.error(f"Failed to store security event: {e}")
    
    async def _check_alerts(self, event: SecurityEvent):
        """Check if event triggers any alerts"""
        if event.severity == "CRITICAL":
            await self._send_alert(f"CRITICAL security event: {event.event_type}", event)
        
        # Check IP-based thresholds
        ip_auth_failures = self.metrics.failed_auth_attempts.get(event.source_ip, 0)
        if ip_auth_failures >= self.alert_thresholds["failed_auth_per_ip"]:
            await self._send_alert(
                f"Excessive auth failures from IP: {ip_auth_failures} attempts",
                event
            )
        
        ip_rate_violations = self.metrics.rate_limit_violations.get(event.source_ip, 0)
        if ip_rate_violations >= self.alert_thresholds["rate_limit_violations_per_ip"]:
            await self._send_alert(
                f"Excessive rate limit violations from IP: {ip_rate_violations} violations",
                event
            )
    
    async def _send_alert(self, message: str, event: SecurityEvent):
        """Send security alert"""
        self.security_logger.logger.warning(
            f"SECURITY ALERT: {message}",
            extra={
                'security_event': 'alert',
                'security_level': 'CRITICAL',
                'alert_message': message,
                'triggering_event': event.event_type
            }
        )
        
        # Store alert in Redis
        alert_data = {
            "timestamp": time.time(),
            "message": message,
            "triggering_event": asdict(event),
            "resolved": False
        }
        
        try:
            await self.redis.lpush("security_alerts", json.dumps(alert_data))
            await self.redis.ltrim("security_alerts", 0, 99)  # Keep only last 100 alerts
        except Exception as e:
            self.security_logger.logger.error(f"Failed to store alert: {e}")
    
    async def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent security events"""
        recent_events = list(self.metrics.recent_events)[-limit:]
        return [asdict(event) for event in recent_events]
    
    async def get_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent security alerts"""
        try:
            alerts_raw = await self.redis.lrange("security_alerts", 0, limit - 1)
            alerts = []
            for alert_raw in alerts_raw:
                try:
                    alert = json.loads(alert_raw)
                    alerts.append(alert)
                except json.JSONDecodeError:
                    continue
            return alerts
        except Exception as e:
            self.security_logger.logger.error(f"Failed to get alerts: {e}")
            return []
    
    async def resolve_alert(self, alert_index: int) -> bool:
        """Mark an alert as resolved"""
        try:
            alerts = await self.get_alerts(100)
            if 0 <= alert_index < len(alerts):
                alerts[alert_index]["resolved"] = True
                # Update in Redis (simplified approach)
                await self.redis.lset("security_alerts", alert_index, json.dumps(alerts[alert_index]))
                return True
            return False
        except Exception as e:
            self.security_logger.logger.error(f"Failed to resolve alert: {e}")
            return False
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive security dashboard data"""
        metrics_summary = self.metrics.get_metrics_summary()
        
        # Add additional dashboard-specific data
        dashboard_data = {
            "status": "monitoring" if self.monitoring_active else "disabled",
            "last_updated": datetime.utcnow().isoformat() + 'Z',
            "metrics": metrics_summary,
            "alert_thresholds": self.alert_thresholds,
            "monitoring_config": {
                "max_recent_events": 1000,
                "event_retention_hours": 24,
                "alert_retention_count": 100
            }
        }
        
        return dashboard_data
    
    # 🎮 GAME-SPECIFIC SECURITY MONITORING METHODS
    
    async def log_auth_failure(self, user_id: int, endpoint: str, source_ip: str):
        """Log authentication failure (critical security event)"""
        await self.log_security_event(
            event_type="auth_failure",
            severity="HIGH", 
            source_ip=source_ip,
            user_id=str(user_id),
            endpoint=endpoint,
            details={
                "failure_type": "telegram_auth_validation",
                "endpoint": endpoint,
                "timestamp": time.time()
            }
        )
        
        # Track failed auth attempts for rate limiting
        self.metrics.failed_auth_attempts[source_ip] = (
            self.metrics.failed_auth_attempts.get(source_ip, 0) + 1
        )
    
    async def log_duplicate_bet_attempt(self, user_id: int, existing_bet, 
                                       attempted_bet, source_ip: str):
        """Log duplicate bet attempt (critical security violation)"""
        await self.log_security_event(
            event_type="duplicate_bet_attempt",
            severity="HIGH",
            source_ip=source_ip,
            user_id=str(user_id),
            endpoint="/join",
            details={
                "existing_bet": str(existing_bet),
                "attempted_bet": str(attempted_bet),
                "violation_type": "double_spending_attempt"
            }
        )
    
    async def log_timing_attack(self, user_id: int, timing_ms: float, 
                               min_allowed_ms: float, source_ip: str):
        """Log potential timing attack on cashout"""
        await self.log_security_event(
            event_type="timing_attack_detected",
            severity="CRITICAL",
            source_ip=source_ip,
            user_id=str(user_id),
            endpoint="/cashout",
            details={
                "timing_ms": timing_ms,
                "min_allowed_ms": min_allowed_ms,
                "violation_ms": min_allowed_ms - timing_ms,
                "attack_type": "early_cashout_attempt"
            }
        )
    
    async def log_cashout_after_crash(self, user_id: int, coefficient,
                                     crash_point, source_ip: str):
        """Log attempt to cashout after crash (critical violation)"""
        await self.log_security_event(
            event_type="cashout_after_crash",
            severity="CRITICAL",
            source_ip=source_ip,
            user_id=str(user_id),
            endpoint="/cashout",
            details={
                "coefficient": str(coefficient),
                "crash_point": str(crash_point),
                "violation_amount": str(coefficient - crash_point),
                "attack_type": "post_crash_cashout"
            }
        )
    
    async def log_balance_overflow_attempt(self, user_id: int, attempted_balance,
                                          max_allowed, source_ip: str):
        """Log balance overflow attempt"""
        await self.log_security_event(
            event_type="balance_overflow_attempt",
            severity="MEDIUM",
            source_ip=source_ip,
            user_id=str(user_id),
            details={
                "attempted_balance": str(attempted_balance),
                "max_allowed": str(max_allowed),
                "overflow_amount": str(attempted_balance - max_allowed),
                "attack_type": "balance_manipulation"
            }
        )
    
    async def log_redis_state_corruption(self, corruption_type: str, 
                                        expected_checksum: str, actual_checksum: str,
                                        user_id: int = None):
        """Log Redis state corruption detection"""
        await self.log_security_event(
            event_type="redis_state_corruption",
            severity="CRITICAL",
            source_ip="internal",
            user_id=str(user_id) if user_id else None,
            details={
                "corruption_type": corruption_type,
                "expected_checksum": expected_checksum[:16] + "...",  # Truncate for security
                "actual_checksum": actual_checksum[:16] + "...",
                "system_integrity": "compromised"
            }
        )
    
    async def log_suspicious_game_pattern(self, user_id: int, pattern_type: str,
                                         pattern_details: dict, source_ip: str):
        """Log suspicious gaming patterns (potential cheating)"""
        await self.log_security_event(
            event_type="suspicious_game_pattern",
            severity="MEDIUM",
            source_ip=source_ip,
            user_id=str(user_id),
            details={
                "pattern_type": pattern_type,
                "pattern_details": pattern_details,
                "analysis_type": "behavioral_detection"
            }
        )
    
    async def start_monitoring(self):
        """Start background monitoring tasks"""
        self.monitoring_active = True
        self.security_logger.logger.info("🔒 Security monitoring started")
        
        # Start background cleanup task
        asyncio.create_task(self._cleanup_task())
    
    async def stop_monitoring(self):
        """Stop security monitoring"""
        self.monitoring_active = False
        self.security_logger.logger.info("🔒 Security monitoring stopped")
    
    async def _cleanup_task(self):
        """Background task to clean up old events and metrics"""
        while self.monitoring_active:
            try:
                # Clean up old metrics (older than 24 hours)
                cutoff_time = time.time() - 86400
                
                # Clean failed auth attempts
                for ip in list(self.metrics.failed_auth_attempts.keys()):
                    # Reset counters periodically to prevent indefinite blocking
                    if time.time() % 3600 < 60:  # Reset every hour
                        self.metrics.failed_auth_attempts[ip] = 0
                
                # Clean rate limit violations similarly
                for ip in list(self.metrics.rate_limit_violations.keys()):
                    if time.time() % 3600 < 60:
                        self.metrics.rate_limit_violations[ip] = 0
                
                await asyncio.sleep(300)  # Run every 5 minutes
            except Exception as e:
                self.security_logger.logger.error(f"Cleanup task error: {e}")
                await asyncio.sleep(60)

# Global security monitor instance
_security_monitor: Optional[SecurityMonitor] = None

def get_security_monitor(redis_client: redis.Redis) -> SecurityMonitor:
    """Get or create global security monitor instance"""
    global _security_monitor
    if _security_monitor is None:
        _security_monitor = SecurityMonitor(redis_client)
    return _security_monitor

async def init_security_monitoring(redis_client: redis.Redis):
    """Initialize security monitoring system"""
    monitor = get_security_monitor(redis_client)
    await monitor.start_monitoring()
    return monitor

# Convenience functions for common security events
async def log_auth_failure(redis_client: redis.Redis, source_ip: str, user_id: Optional[str] = None, details: Optional[Dict] = None):
    """Log authentication failure"""
    monitor = get_security_monitor(redis_client)
    await monitor.log_security_event(
        event_type="auth_failure",
        severity="MEDIUM",
        source_ip=source_ip,
        user_id=user_id,
        details=details
    )

async def log_rate_limit_exceeded(redis_client: redis.Redis, source_ip: str, endpoint: str, details: Optional[Dict] = None):
    """Log rate limit exceeded"""
    monitor = get_security_monitor(redis_client)
    await monitor.log_security_event(
        event_type="rate_limit_exceeded",
        severity="MEDIUM",
        source_ip=source_ip,
        endpoint=endpoint,
        details=details
    )

async def log_suspicious_activity(redis_client: redis.Redis, source_ip: str, activity_type: str, severity: str = "HIGH", details: Optional[Dict] = None):
    """Log suspicious activity"""
    monitor = get_security_monitor(redis_client)
    await monitor.log_security_event(
        event_type="suspicious_activity",
        severity=severity,
        source_ip=source_ip,
        details={"activity_type": activity_type, **(details or {})}
    )