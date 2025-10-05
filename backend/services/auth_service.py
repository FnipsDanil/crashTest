"""
Authentication service for Telegram Mini App integration
Handles init_data validation and user authentication
"""

import hmac
import hashlib
import json
import time
from typing import Dict, Any, Optional, Tuple
from urllib.parse import unquote, parse_qsl

import os

# Auth configuration from environment
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
from logging_config import get_security_logger

class AuthService:
    """Telegram Mini App authentication service"""
    
    def __init__(self, bot_token: str = TG_BOT_TOKEN, development_mode: bool = DEBUG):
        self.bot_token = bot_token
        self.development_mode = development_mode
        self.max_auth_age = 86400  # 24 hours
        self.security_logger = get_security_logger()
        
    def validate_telegram_init_data(self, init_data_string: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate Telegram Mini App init data according to official documentation
        Returns (is_valid, parsed_data)
        """
        if not self.bot_token:
            self.security_logger.logger.error("TG_BOT_TOKEN not configured")
            if not self.development_mode:
                return False, {}
        
        # SECURITY: Don't log the raw init_data as it contains sensitive information
        
        try:
            # Parse the init data as query parameters
            decoded_string = unquote(init_data_string)
            parsed_data = dict(parse_qsl(decoded_string))
            
            if not parsed_data or "hash" not in parsed_data:
                self.security_logger.logger.warning("No hash found in parsed init_data")
                return False, {}
            
            # Extract the hash
            received_hash = parsed_data.pop("hash")
            
            # Create the data check string (sorted by key)
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
            calculated_hash = hmac.new(
                secret_key,
                data_check_string.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Verify the hash
            is_valid = calculated_hash == received_hash
            
            
            # SECURITY: Log validation result without exposing hashes
            
            # Parse user data if present
            user_id = None
            if "user" in parsed_data:
                try:
                    parsed_data["user"] = json.loads(parsed_data["user"])
                    user_id = parsed_data["user"].get("id")
                    # SECURITY: Don't log full user data
                except json.JSONDecodeError:
                    self.security_logger.logger.warning("Failed to parse user JSON")
                    pass
            
            # Validate auth_date
            auth_date = parsed_data.get("auth_date")
            if auth_date:
                auth_timestamp = int(auth_date)
                current_timestamp = int(time.time())
                age_seconds = current_timestamp - auth_timestamp
                
                # SECURITY: Log auth date validation without exposing timestamps
                if abs(age_seconds) > self.max_auth_age:
                    self.security_logger.logger.warning(f"Auth date too old/future (age: {age_seconds}s)")
                    if not self.development_mode:
                        is_valid = False
            
            # Log only FAILED authentication attempts for security
            if not is_valid:
                self.security_logger.auth_attempt(
                    str(user_id) if user_id else None, 
                    is_valid, 
                    "unknown", 
                    "telegram_init_data"
                )
            
            # 🔒 CRITICAL SECURITY FIX: Only allow invalid hash in development mode
            if not is_valid and "user" in parsed_data and self.development_mode:
                self.security_logger.logger.warning("Development mode: accepting invalid hash but valid user data")
                return True, parsed_data
            
            return is_valid, parsed_data
            
        except Exception as e:
            self.security_logger.logger.error(f"Init data validation error: {type(e).__name__}")
            return False, {}
    
    def extract_user_data(self, parsed_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract user information from parsed init data"""
        try:
            user_data = parsed_data.get("user", {})
            if not user_data or "id" not in user_data:
                return None
            
            return {
                "id": user_data["id"],
                "first_name": user_data.get("first_name", ""),
                "last_name": user_data.get("last_name", ""),
                "username": user_data.get("username", ""),
                "language_code": user_data.get("language_code", "en"),
                "is_premium": user_data.get("is_premium", False),
                "auth_date": parsed_data.get("auth_date"),
                "start_param": parsed_data.get("start_param")
            }
        except Exception as e:
            self.security_logger.logger.error(f"Error extracting user data: {e}")
            return None
    
    def validate_user_permissions(self, user_data: Dict[str, Any], required_permissions: list = None) -> bool:
        """Validate user permissions for specific actions"""
        if not user_data:
            return False
        
        # For now, all authenticated users have basic permissions
        # This can be extended for admin users, premium users, etc.
        return True
    
    def is_admin_user(self, user_id: int) -> bool:
        """Check if user has admin privileges"""
        # TODO: Implement admin user detection
        # This could check against a database or configuration
        admin_users = []  # Add admin user IDs here
        return user_id in admin_users
    
    def create_session_token(self, user_data: Dict[str, Any]) -> str:
        """Create a session token for authenticated user"""
        # This is a simplified implementation
        # In production, you might want to use JWT or similar
        session_data = {
            "user_id": user_data["id"],
            "created_at": time.time(),
            "expires_at": time.time() + 86400  # 24 hours
        }
        return json.dumps(session_data)
    
    def validate_session_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate session token"""
        try:
            session_data = json.loads(token)
            if time.time() > session_data.get("expires_at", 0):
                return None  # Token expired
            return session_data
        except Exception:
            return None
    
    def get_auth_stats(self) -> Dict[str, Any]:
        """Get authentication service statistics"""
        return {
            "development_mode": self.development_mode,
            "bot_token_configured": bool(self.bot_token),
            "max_auth_age_hours": self.max_auth_age / 3600
        }