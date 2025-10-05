"""
Simple monitoring service for the crash game system.
Provides health checks and basic metrics without external dependencies.
"""

import time
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from database import get_db
from services.database_service import DatabaseService


class SimpleGameMonitor:
    """Minimal monitoring through logs and Redis."""
    
    def __init__(self, redis_client, game_engine):
        self.redis = redis_client
        self.game_engine = game_engine
        self.logger = logging.getLogger("game_monitor")
        self.start_time = time.time()
        
        # Set up basic logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    async def collect_basic_metrics(self) -> Dict[str, Any]:
        """Collect simple metrics from Redis."""
        try:
            # Basic game state metrics
            if self.game_engine:
                engine_stats = await self.game_engine.get_engine_stats()
                current_status = await self.game_engine.get_current_status()
            else:
                engine_stats = {}
                current_status = {}
            
            # Redis health
            redis_healthy = await self.redis.ping() if self.redis else False
            
            # Basic database stats
            db_healthy = False
            total_users = 0
            try:
                async for session in get_db():
                    db_healthy = await DatabaseService.check_health(session)
                    if db_healthy:
                        # Simple user count
                        from sqlalchemy import text
                        result = await session.execute(text("SELECT COUNT(*) FROM users"))
                        total_users = result.scalar() or 0
                    break
            except Exception as e:
                self.logger.error(f"Database metrics error: {e}")
                db_healthy = False
            
            metrics = {
                "timestamp": datetime.now().isoformat(),
                "uptime_seconds": time.time() - self.start_time,
                "system_health": {
                    "redis": "ok" if redis_healthy else "error",
                    "database": "ok" if db_healthy else "error",
                    "game_engine": "ok" if self.game_engine and engine_stats.get('running') else "error"
                },
                "game_stats": {
                    "status": current_status.get('status', 'unknown'),
                    "coefficient": current_status.get('coefficient', 0),
                    "current_players": engine_stats.get('current_players', 0),
                    "uptime": engine_stats.get('uptime_seconds', 0)
                },
                "platform_stats": {
                    "total_users": total_users
                }
            }
            
            # Log key metrics
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"❌ Error collecting metrics: {e}")
            return {"error": str(e), "timestamp": datetime.now().isoformat()}
    
    async def check_system_health(self) -> bool:
        """Comprehensive health check."""
        try:
            # Check Redis
            redis_ok = await self.redis.ping() if self.redis else False
            if not redis_ok:
                self.logger.critical("❌ Redis unavailable!")
                return False
            
            # Check Database
            db_ok = False
            try:
                async for session in get_db():
                    db_ok = await DatabaseService.check_health(session)
                    break
            except Exception as e:
                self.logger.error(f"Database health check failed: {e}")
                db_ok = False
            
            if not db_ok:
                self.logger.critical("❌ Database unavailable!")
                return False
            
            # Check Game Engine
            if not self.game_engine:
                self.logger.warning("⚠️ Game engine not initialized")
                return False
            
            try:
                state = await self.game_engine.get_current_status()
                if not state:
                    self.logger.error("❌ Game engine not responding")
                    return False
            except Exception as e:
                self.logger.error(f"Game engine health check failed: {e}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.critical(f"❌ System health check crashed: {e}")
            return False
    
    async def start_monitoring(self, interval_seconds: int = 30):
        """Start background monitoring loop."""
        self.logger.info(f"🔄 Starting monitoring (interval: {interval_seconds}s)")
        
        while True:
            try:
                # Health check
                health_ok = await self.check_system_health()
                
                # Collect metrics only if healthy
                if health_ok:
                    metrics = await self.collect_basic_metrics()
                    
                    # Store latest metrics in Redis for dashboard
                    if self.redis and metrics:
                        await self.redis.setex(
                            "system_metrics", 
                            interval_seconds * 2,  # TTL = 2x interval
                            str(metrics)
                        )
                else:
                    # System unhealthy - shorter check interval
                    await asyncio.sleep(10)
                    continue
                
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                self.logger.error(f"❌ Monitoring loop error: {e}")
                await asyncio.sleep(10)  # Short pause on errors
    
    async def get_dashboard_data(self) -> Dict[str, Any]:
        """Get dashboard data for admin endpoint."""
        try:
            # Get latest metrics from Redis
            if self.redis:
                metrics_data = await self.redis.get("system_metrics")
                if metrics_data:
                    import json
                    return json.loads(metrics_data.replace("'", '"'))
            
            # Fallback: collect fresh metrics
            return await self.collect_basic_metrics()
            
        except Exception as e:
            self.logger.error(f"Error getting dashboard data: {e}")
            return {
                "error": str(e), 
                "timestamp": datetime.now().isoformat()
            }