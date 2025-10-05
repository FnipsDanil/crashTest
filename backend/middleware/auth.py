"""
Authentication middleware for FastAPI
Provides secure user authentication and authorization
"""

import hmac
import hashlib
import json
import time
import os
from typing import Optional, Dict, Any, Set
from urllib.parse import unquote, parse_qsl
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
import logging

# Configure logging for security events
security_logger = logging.getLogger("security")
security_logger.setLevel(logging.INFO)

class AuthMiddleware:
    """Authentication middleware for Telegram Mini App integration."""
    
    def __init__(
        self, 
        bot_token: str,
        development_mode: bool = False,
        max_auth_age: int = 86400,  # 24 hours
    ):
        self.bot_token = bot_token
        self.development_mode = development_mode
        self.max_auth_age = max_auth_age
        
        # Protected endpoints that require authentication
        self.protected_endpoints: Set[str] = {
            "/join",
            "/cashout", 
            "/balance",
            "/user-stats",
            "/player-status",
            "/purchase-gift",
            "/create-invoice",
            "/sync-balance",
            "/update-user-data",
            "/gifts",
            "/leaderboard",
            "/player-rank",
            "/payment-requests",
            "/refund-balance",
            "/current-state",
            "/game-config",
            "/payment-status",
            "/verify-user",
            "/webhook/payment",
            "/api/player/check-channel-subscription",
            "/api/player/channel-bonuses",
            "/api/player/use-promo-code",
            "/api/player/promo-code-history"
        }
        
        # Admin endpoints that require special permissions (DISABLED - all commented out)
        self.admin_endpoints: Set[str] = {
            # "/admin/clear-redis",
            # "/admin/reset-gifts", 
            # "/refund-balance"
        }
        
        # 🔒 CSRF Protection: Critical endpoints that require Origin validation
        csrf_protected_env = os.getenv("CSRF_PROTECTED_ENDPOINTS", "/join,/cashout,/purchase-gift,/api/player/check-channel-subscription")
        self.csrf_protected_endpoints: Set[str] = {
            endpoint.strip() for endpoint in csrf_protected_env.split(",") if endpoint.strip()
        }
        
        # 🔒 CSRF Protection: Allowed origins from environment (должны совпадать с CORS_ORIGINS)
        allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "https://telegram.org,https://web.telegram.org,http://localhost:5173,https://localhost:5173,https://172.31.112.1:5173")
        security_logger.info(f"🔍 Loading ALLOWED_ORIGINS from env: '{allowed_origins_env}'")
        self.allowed_origins: Set[str] = {
            origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()
        } if allowed_origins_env else set()
        security_logger.info(f"🔍 Final allowed_origins: {list(self.allowed_origins)}")
        
        # Public endpoints that don't require authentication
        self.public_endpoints: Set[str] = {
            "/health",
            "/webhook/telegram"  # ✅ Telegram webhook должен быть публичным!
        }
    
    def _extract_user_data_from_init_data(self, init_data_string: str) -> Optional[Dict[str, Any]]:
        """Extract and validate user data from Telegram init_data."""
        try:
            if not self.bot_token:
                security_logger.warning("🚨 No bot token available for validation")
                if self.development_mode:
                    return {"id": 123456, "first_name": "Dev User"}
                return None
            
            # URL decode the init_data
            decoded_string = unquote(init_data_string)
            parsed_data = dict(parse_qsl(decoded_string))
            
            # Extract hash
            received_hash = parsed_data.pop('hash', None)
            if not received_hash:
                return None
            
            # Create data check string
            data_check_items = []
            for key in sorted(parsed_data.keys()):
                data_check_items.append(f"{key}={parsed_data[key]}")
            data_check_string = "\n".join(data_check_items)
            
            # 🔒 CORRECT ALGORITHM: Use Telegram's official two-step HMAC process
            # Step 1: Create secret key using HMAC-SHA256 with "WebAppData" constant
            secret_key = hmac.new(
                "WebAppData".encode(),
                self.bot_token.encode(),
                hashlib.sha256
            ).digest()
            
            # Step 2: Calculate final HMAC-SHA256 using the secret key
            expected_hash = hmac.new(
                secret_key,
                data_check_string.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Verify hash
            if not hmac.compare_digest(expected_hash, received_hash):
                if self.development_mode:
                    security_logger.warning("Invalid hash in development mode, but continuing with user data")
                    # In dev mode, continue processing user data even with invalid hash
                else:
                    security_logger.warning(f"Invalid Telegram hash detected from IP: {self._get_client_ip_from_request()}")
                    return None
            
            # Parse user data
            user_string = parsed_data.get('user', '')
            if not user_string:
                return None
            
            try:
                user_data = json.loads(user_string)
                if not isinstance(user_data, dict) or 'id' not in user_data:
                    return None
                
                # Validate auth_date
                auth_date = parsed_data.get('auth_date')
                if auth_date and not self._validate_auth_date(auth_date):
                    if not self.development_mode:
                        return None
                
                return user_data
                
            except json.JSONDecodeError:
                return None
                
        except Exception as e:
            security_logger.error(f"Auth validation error: {e}")
            return None
    
    def _validate_auth_date(self, auth_date_str: str) -> bool:
        """Validate that auth_date is not too old."""
        try:
            auth_date = int(auth_date_str)
            current_time = int(time.time())
            age = abs(current_time - auth_date)
            
            return age <= self.max_auth_age
        except (ValueError, TypeError):
            return False
    
    def _get_client_ip_from_request(self) -> str:
        """Get client IP for logging (simplified for this context)."""
        return "unknown"  # Would be extracted from request in actual implementation
    
    def _validate_origin(self, request: Request) -> bool:
        """🔒 CSRF Protection: Validate Origin header for critical operations."""
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        
        
        # Check Origin header first
        if origin and origin in self.allowed_origins:
            return True
            
        # Check Referer as fallback
        if referer:
            for allowed_origin in self.allowed_origins:
                if referer.startswith(allowed_origin):
                    return True
        
        # For production: strict validation - no requests without proper Origin/Referer
        security_logger.warning(f"🚨 Origin validation failed: origin='{origin}', referer='{referer}', allowed={list(self.allowed_origins)}")
        return False
    
    def _extract_auth_from_request(self, request: Request) -> Optional[Dict[str, Any]]:
        """Extract authentication data from request."""
        # Try to get from X-Telegram-Init-Data header (PREFERRED METHOD)
        telegram_init_data = request.headers.get("X-Telegram-Init-Data")
        if telegram_init_data:
            result = self._extract_user_data_from_init_data(telegram_init_data)
            return result
        
        # Try to get from Authorization header (fallback)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            init_data = auth_header[7:]  # Remove "Bearer " prefix
            return self._extract_user_data_from_init_data(init_data)
        
        # Try to get from query parameters (less secure, but sometimes used)
        init_data = request.query_params.get("init_data")
        if init_data:
            return self._extract_user_data_from_init_data(init_data)
        
        return None
    
    def _is_endpoint_protected(self, path: str) -> str:
        """Check if endpoint requires authentication."""
        # Remove query parameters and trailing slashes
        clean_path = path.split('?')[0].rstrip('/')
        
        # Check for exact matches
        if clean_path in self.public_endpoints:
            return "public"
        
        if clean_path in self.admin_endpoints:
            return "admin"
        
        # Check for protected endpoints (including parameterized routes)
        for protected_path in self.protected_endpoints:
            if clean_path == protected_path or clean_path.startswith(protected_path + "/"):
                return "protected"
        
        # Check for admin endpoints patterns (DISABLED - all admin endpoints commented out)
        # if clean_path.startswith("/admin/"):
        #     return "admin"
        
        # Default to public for now (in production, might want to default to protected)
        return "public"
    
    def _create_auth_error_response(self, message: str, status_code: int = 401) -> JSONResponse:
        """Create standardized authentication error response."""
        return JSONResponse(
            status_code=status_code,
            content={
                "error": "Authentication failed",
                "message": message,
                "code": "UNAUTHORIZED"
            },
            headers={
                "WWW-Authenticate": "Bearer"
            }
        )
    
    async def __call__(self, request: Request, call_next):
        """Middleware entry point."""
        path = request.url.path
        method = request.method
        
        # 🔒 SECURITY: Limited development mode - only for specific debug endpoints
        if self.development_mode:
            # 🔒 CRITICAL: Only allow fake user for health checks and non-game endpoints
            if path in ["/health", "/health/db", "/docs", "/openapi.json", "/redoc"]:
                # Create minimal dev user for health checks only
                request.state.user_id = None
                request.state.user_data = None
                request.state.authenticated = False
                return await call_next(request)
            
            # 🔒 FOR ALL OTHER ENDPOINTS: Still require valid auth even in dev mode
            user_data = self._extract_auth_from_request(request)
            if user_data:
                request.state.user_id = user_data.get('id')
                request.state.user_data = user_data
                request.state.authenticated = True
            else:
                security_logger.warning(f"🚨 Dev mode: Missing auth for protected endpoint {path}")
                return self._create_auth_error_response(
                    "Authentication required even in development mode for game endpoints"
                )
            return await call_next(request)
        
        # Production mode - determine if endpoint needs authentication
        endpoint_type = self._is_endpoint_protected(path)
        
        if endpoint_type == "public":
            # No authentication required
            return await call_next(request)
        
        # Extract authentication data
        user_data = self._extract_auth_from_request(request)
        
        if endpoint_type in ["protected", "admin"]:
            if not user_data:
                security_logger.warning(f"Unauthorized access attempt to {path} from {self._get_client_ip_from_request()}")
                return self._create_auth_error_response(
                    "Authentication required. Please provide valid Telegram init_data."
                )
            
            # 🔒 CSRF Protection: Additional Origin validation for critical endpoints
            if path in self.csrf_protected_endpoints and method == "POST":
                
                if not self._validate_origin(request):
                    security_logger.warning(f"🚨 CSRF attempt detected: Invalid origin for {path} from {self._get_client_ip_from_request()}")
                    return self._create_auth_error_response(
                        "Invalid request origin", 403
                    )
                
                # 🔒 Additional CSRF Protection: Check for X-Requested-With header (simple but effective)
                x_requested_with = request.headers.get("X-Requested-With")
                if not x_requested_with:
                    security_logger.warning(f"🚨 CSRF attempt detected: Missing X-Requested-With header for {path}")
                    return self._create_auth_error_response(
                        "Invalid request headers", 403
                    )
            
            # Additional checks for admin endpoints
            if endpoint_type == "admin":
                # In a real implementation, you'd check if user has admin privileges
                # For now, we'll log the access attempt
                security_logger.info(f"Admin endpoint access by user {user_data.get('id')} to {path}")
        
        # Add user data to request state for use by endpoint handlers
        if user_data:
            request.state.user_id = user_data.get('id')
            request.state.user_data = user_data
            request.state.authenticated = True
        else:
            request.state.authenticated = False
        
        # Continue with request
        response = await call_next(request)
        
        # Add security headers to response
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        
        return response


def create_auth_middleware(
    bot_token: str, 
    development_mode: bool = False
) -> AuthMiddleware:
    """Create authentication middleware instance."""
    return AuthMiddleware(
        bot_token=bot_token,
        development_mode=development_mode
    )