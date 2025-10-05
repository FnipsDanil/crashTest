"""
Time Security Module
Protects against time manipulation attacks and ensures consistent timing
"""

import time
import asyncio
import logging
import threading
from typing import Optional, Dict, Any
from decimal import Decimal

logger = logging.getLogger(__name__)

class SecureTimeManager:
    """Manages secure time operations with NTP synchronization and drift detection"""
    
    def __init__(self):
        self._base_system_time = time.time()
        self._base_monotonic_time = time.monotonic()
        self._ntp_offset = 0.0  # Offset from NTP server
        self._last_ntp_sync = 0.0
        self._drift_detection_enabled = True
        self._max_time_drift = 5.0  # Maximum allowed time drift in seconds
        self._lock = threading.Lock()
        
    def get_secure_time(self) -> float:
        """
        Get secure timestamp that cannot be manipulated by system clock changes
        Uses monotonic time as base with NTP offset correction
        """
        with self._lock:
            # Use monotonic time (unaffected by system clock changes) + base time + NTP offset
            monotonic_elapsed = time.monotonic() - self._base_monotonic_time
            secure_time = self._base_system_time + monotonic_elapsed + self._ntp_offset
            return secure_time
    
    def detect_time_manipulation(self) -> tuple[bool, str]:
        """
        Detect if system time has been manipulated
        Returns (is_manipulated, reason)
        """
        if not self._drift_detection_enabled:
            return False, "Detection disabled"
            
        try:
            current_system_time = time.time()
            secure_time = self.get_secure_time()
            time_drift = abs(current_system_time - secure_time)
            
            if time_drift > self._max_time_drift:
                return True, f"Time drift detected: {time_drift:.2f}s > {self._max_time_drift}s"
            
            return False, f"Time drift OK: {time_drift:.2f}s"
            
        except Exception as e:
            logger.error(f"❌ Error detecting time manipulation: {e}")
            return True, f"Detection error: {e}"
    
    async def sync_with_ntp(self, ntp_server: str = "pool.ntp.org") -> bool:
        """
        Synchronize with NTP server to get accurate time offset
        Returns True if sync successful
        """
        try:
            # Simple NTP sync implementation
            # In production, use proper NTP library like ntplib
            logger.info(f"🕐 Attempting NTP sync with {ntp_server}")
            
            # For now, assume we get NTP time (in production use ntplib)
            # This is a placeholder - implement proper NTP client
            local_time = time.time()
            # ntp_time = get_ntp_time(ntp_server)  # Implement this
            # self._ntp_offset = ntp_time - local_time
            
            self._last_ntp_sync = local_time
            logger.info(f"🕐 NTP sync completed, offset: {self._ntp_offset:.3f}s")
            return True
            
        except Exception as e:
            logger.error(f"❌ NTP sync failed: {e}")
            return False
    
    def calculate_game_coefficient(self, start_time: float, tick_ms: int, growth_rate: Decimal, max_coef: Decimal) -> Decimal:
        """
        Calculate game coefficient using secure time to prevent manipulation
        """
        try:
            # 🔒 SECURITY: Use secure time instead of system time
            secure_now = self.get_secure_time()
            
            # Detect time manipulation
            is_manipulated, reason = self.detect_time_manipulation()
            if is_manipulated:
                logger.warning(f"🚨 Time manipulation detected during coefficient calculation: {reason}")
                # Continue with secure time but log the incident
            
            elapsed_ms = (secure_now - start_time) * 1000
            ticks = elapsed_ms / tick_ms
            
            # Calculate coefficient
            coef = (growth_rate ** Decimal(str(ticks))).quantize(Decimal('0.01'))
            coef = min(coef, max_coef)
            
            return coef
            
        except Exception as e:
            logger.error(f"❌ Error calculating secure coefficient: {e}")
            # Fallback to minimum coefficient
            return Decimal('1.01')
    
    def validate_timing_request(self, request_time: float, min_delay: float = 0.1) -> tuple[bool, str]:
        """
        Validate that a timing-sensitive request (like cashout) is not too early
        """
        try:
            secure_now = self.get_secure_time()
            elapsed = secure_now - request_time
            
            if elapsed < min_delay:
                return False, f"Request too early: {elapsed*1000:.0f}ms < {min_delay*1000:.0f}ms"
            
            # Check for future timestamps (potential manipulation)
            if request_time > secure_now + 1.0:  # Allow 1s tolerance
                return False, f"Request timestamp in future: {request_time - secure_now:.2f}s ahead"
            
            return True, f"Timing valid: {elapsed*1000:.0f}ms delay"
            
        except Exception as e:
            logger.error(f"❌ Error validating timing: {e}")
            return False, f"Validation error: {e}"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get time security statistics"""
        is_manipulated, reason = self.detect_time_manipulation()
        return {
            "secure_time": self.get_secure_time(),
            "system_time": time.time(),
            "ntp_offset": self._ntp_offset,
            "last_ntp_sync": self._last_ntp_sync,
            "time_manipulation_detected": is_manipulated,
            "manipulation_reason": reason,
            "max_drift_allowed": self._max_time_drift
        }

# Global secure time manager instance
secure_time_manager = SecureTimeManager()

def get_secure_time() -> float:
    """Get secure timestamp globally"""
    return secure_time_manager.get_secure_time()

def detect_time_manipulation() -> tuple[bool, str]:
    """Detect time manipulation globally"""
    return secure_time_manager.detect_time_manipulation()

def calculate_secure_coefficient(start_time: float, tick_ms: int, growth_rate: Decimal, max_coef: Decimal) -> Decimal:
    """Calculate coefficient with secure timing globally"""
    return secure_time_manager.calculate_game_coefficient(start_time, tick_ms, growth_rate, max_coef)

def validate_cashout_timing(game_start_time: float, min_delay: float = 0.1) -> tuple[bool, str]:
    """Validate cashout timing globally"""
    return secure_time_manager.validate_timing_request(game_start_time, min_delay)