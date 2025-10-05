"""
Rate limiting middleware for FastAPI
Provides protection against DoS attacks and API abuse
"""

import time
import redis.asyncio as redis
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Optional
import asyncio
from datetime import datetime, timedelta
import json

class RateLimiter:
    """Rate limiting implementation using Redis for storage."""
    
    def __init__(
        self, 
        redis_client: redis.Redis,
        default_limit: int = 1000,  # requests per minute - increased for development
        default_window: int = 60,  # window in seconds
    ):
        self.redis = redis_client
        self.default_limit = default_limit
        self.default_window = default_window
        
        # Different limits for different endpoints - relaxed for development
        self.endpoint_limits = {
            "/join": {"limit": 100, "window": 60},      # 100 joins per minute
            "/cashout": {"limit": 200, "window": 60},   # 200 cashouts per minute  
            "/verify-user": {"limit": 50, "window": 60}, # 50 auth attempts per minute
            "/create-invoice": {"limit": 30, "window": 60}, # 30 payments per minute
            "/purchase-gift": {"limit": 50, "window": 60},  # 50 gift purchases per minute
            "/current-state": {"limit": 1000, "window": 60}, # Game state - very frequent
            "/player-status": {"limit": 1000, "window": 60}, # Player status - very frequent
            "/balance": {"limit": 500, "window": 60}, # Balance checks
            "/leaderboard": {"limit": 200, "window": 60}, # Leaderboard
            "/user-stats": {"limit": 200, "window": 60}, # User stats
            "/gifts": {"limit": 100, "window": 60}, # Gifts
            "/payment-requests": {"limit": 100, "window": 60}, # Payment requests
            "/webhook/telegram": {"limit": 1000, "window": 60}, # Telegram webhooks - high limit
        }
        
        # IP-based global limits - increased for development
        self.global_limits = {
            "per_ip_per_minute": {"limit": 5000, "window": 60},  # 5000 requests per minute
            "per_ip_per_hour": {"limit": 50000, "window": 3600},  # 50000 per hour
        }
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        # Check for real IP from reverse proxy
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"
    
    def _get_rate_limit_key(self, identifier: str, endpoint: str, window_type: str = "endpoint") -> str:
        """Generate Redis key for rate limiting."""
        current_window = int(time.time()) // (self.endpoint_limits.get(endpoint, {}).get("window", self.default_window))
        return f"rate_limit:{window_type}:{identifier}:{endpoint}:{current_window}"
    
    async def _increment_counter(self, key: str, ttl: int) -> int:
        """Increment counter in Redis with TTL."""
        try:
            # Use pipeline for atomic operations
            pipe = self.redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl)
            results = await pipe.execute()
            return results[0]
        except Exception as e:
            print(f"Rate limiter Redis error: {e}")
            # Fail open in case of Redis issues
            return 0
    
    async def check_rate_limit(
        self, 
        request: Request, 
        identifier: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Check if request should be rate limited.
        Returns dict with 'allowed' boolean and metadata.
        """
        client_ip = self._get_client_ip(request)
        endpoint = request.url.path
        user_identifier = identifier or client_ip
        
        # Get endpoint-specific limits
        endpoint_config = self.endpoint_limits.get(endpoint, {
            "limit": self.default_limit,
            "window": self.default_window
        })
        
        limit = endpoint_config["limit"]
        window = endpoint_config["window"]
        
        # Check endpoint-specific rate limit
        endpoint_key = self._get_rate_limit_key(user_identifier, endpoint, "endpoint")
        endpoint_count = await self._increment_counter(endpoint_key, window)
        
        if endpoint_count > limit:
            return {
                "allowed": False,
                "reason": "endpoint_limit_exceeded",
                "limit": limit,
                "window": window,
                "current_count": endpoint_count,
                "retry_after": window,
                "endpoint": endpoint
            }
        
        # Check global IP limits
        for limit_name, config in self.global_limits.items():
            global_key = self._get_rate_limit_key(client_ip, "global", limit_name)
            global_count = await self._increment_counter(global_key, config["window"])
            
            if global_count > config["limit"]:
                return {
                    "allowed": False,
                    "reason": "global_limit_exceeded",
                    "limit": config["limit"],
                    "window": config["window"],
                    "current_count": global_count,
                    "retry_after": config["window"],
                    "limit_type": limit_name
                }
        
        # Request allowed
        return {
            "allowed": True,
            "endpoint_count": endpoint_count,
            "endpoint_limit": limit,
            "window": window
        }
    
    async def get_rate_limit_info(self, request: Request, identifier: Optional[str] = None) -> Dict:
        """Get current rate limit status without incrementing counters."""
        client_ip = self._get_client_ip(request)
        endpoint = request.url.path
        user_identifier = identifier or client_ip
        
        endpoint_config = self.endpoint_limits.get(endpoint, {
            "limit": self.default_limit,
            "window": self.default_window
        })
        
        # Get current counts without incrementing
        endpoint_key = self._get_rate_limit_key(user_identifier, endpoint, "endpoint")
        
        try:
            endpoint_count = await self.redis.get(endpoint_key)
            endpoint_count = int(endpoint_count) if endpoint_count else 0
        except:
            endpoint_count = 0
        
        return {
            "endpoint": endpoint,
            "limit": endpoint_config["limit"],
            "remaining": max(0, endpoint_config["limit"] - endpoint_count),
            "window": endpoint_config["window"],
            "reset_time": int(time.time()) + endpoint_config["window"]
        }


class RateLimitMiddleware:
    """FastAPI middleware for rate limiting."""
    
    def __init__(self, redis_url: str):
        self.redis_client = None
        self.redis_url = redis_url
        self.rate_limiter = None
        self._initialized = False
    
    async def _ensure_initialized(self):
        """Lazy initialization of Redis connection."""
        if not self._initialized:
            try:
                self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
                self.rate_limiter = RateLimiter(self.redis_client)
                await self.redis_client.ping()  # Test connection
                self._initialized = True
                print("Rate limiter initialized")
            except Exception as e:
                print(f"Rate limiter initialization failed: {e}")
                # Fail open - don't block requests if Redis is down
                self._initialized = False
    
    async def __call__(self, request: Request, call_next):
        """Middleware entry point."""
        await self._ensure_initialized()
        
        # Skip rate limiting if not initialized (Redis down)
        if not self._initialized or not self.rate_limiter:
            return await call_next(request)
        
        # Skip rate limiting for health checks and static assets
        if request.url.path in ["/health", "/health/db"] or request.url.path.startswith("/static"):
            return await call_next(request)
        
        # Extract user identifier from request if available
        user_identifier = None
        if hasattr(request.state, 'user_id'):
            user_identifier = str(request.state.user_id)
        
        # Check rate limits
        try:
            rate_limit_result = await self.rate_limiter.check_rate_limit(request, user_identifier)
            
            if not rate_limit_result["allowed"]:
                # Rate limit exceeded
                error_response = {
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Limit: {rate_limit_result['limit']} per {rate_limit_result['window']} seconds",
                    "retry_after": rate_limit_result["retry_after"],
                    "current_count": rate_limit_result["current_count"]
                }
                
                return JSONResponse(
                    status_code=429,
                    content=error_response,
                    headers={
                        "Retry-After": str(rate_limit_result["retry_after"]),
                        "X-RateLimit-Limit": str(rate_limit_result["limit"]),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time()) + rate_limit_result["retry_after"])
                    }
                )
            
            # Add rate limit headers to successful responses
            response = await call_next(request)
            
            if rate_limit_result.get("endpoint_count") is not None:
                remaining = max(0, rate_limit_result["endpoint_limit"] - rate_limit_result["endpoint_count"])
                response.headers["X-RateLimit-Limit"] = str(rate_limit_result["endpoint_limit"])
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                response.headers["X-RateLimit-Reset"] = str(int(time.time()) + rate_limit_result["window"])
            
            return response
            
        except Exception as e:
            print(f"Rate limiting error: {e}")
            # Fail open - continue with request if rate limiting fails
            return await call_next(request)


# Factory function for easy integration
def create_rate_limit_middleware(redis_url: str) -> RateLimitMiddleware:
    """Create rate limiting middleware instance."""
    return RateLimitMiddleware(redis_url)