"""
Telegram authentication for HTTP endpoints
Validates that user_id in request matches Telegram token
"""

import logging
from typing import Optional, Tuple
from fastapi import HTTPException, Header, Request
from services.auth_service import AuthService

logger = logging.getLogger(__name__)

async def validate_telegram_user(
    request: Request,
    user_id: int,
    x_telegram_init_data: Optional[str] = Header(None)
) -> Tuple[bool, str]:
    """
    Validate that user_id matches Telegram init_data
    Returns (is_valid, reason)
    """
    try:
        # Get auth service from app state
        auth_service = getattr(request.app.state, 'auth_service', None)
        if not auth_service:
            logger.error("❌ Auth service not available")
            return False, "Auth service unavailable"
        
        # Check if init_data provided
        if not x_telegram_init_data:
            logger.warning(f"🚨 No Telegram init_data provided for user {user_id}")
            return False, "Missing Telegram authentication"
        
        # Validate Telegram init_data
        is_valid, parsed_data = auth_service.validate_telegram_init_data(x_telegram_init_data)
        if not is_valid:
            logger.warning(f"🚨 Invalid Telegram init_data for user {user_id}")
            return False, "Invalid Telegram authentication"
        
        # Extract user data from init_data
        user_data = parsed_data.get('user')
        if not user_data:
            logger.warning(f"🚨 No user data in init_data for user {user_id}")
            return False, "Invalid user data in token"
        
        # Parse user data (it might be JSON string)
        if isinstance(user_data, str):
            import json
            try:
                user_data = json.loads(user_data)
            except json.JSONDecodeError:
                logger.warning(f"🚨 Invalid user JSON in init_data for user {user_id}")
                return False, "Invalid user data format"
        
        # Get Telegram user ID
        telegram_user_id = user_data.get('id')
        if not telegram_user_id:
            logger.warning(f"🚨 No user ID in Telegram data for user {user_id}")
            return False, "Missing user ID in token"
        
        # Compare user IDs
        if int(telegram_user_id) != int(user_id):
            logger.warning(f"🚨 User ID mismatch: request={user_id}, telegram={telegram_user_id}")
            return False, f"User ID mismatch: {user_id} != {telegram_user_id}"
        
        return True, "Valid"
        
    except Exception as e:
        logger.error(f"❌ Error validating Telegram auth for user {user_id}: {e}")
        return False, f"Validation error: {str(e)}"

def require_telegram_auth(user_id: int, init_data: Optional[str]) -> None:
    """
    Require valid Telegram authentication or raise HTTPException
    """
    if not init_data:
        raise HTTPException(
            status_code=401,
            detail="Missing Telegram authentication. Please restart the app."
        )
    
    # Note: Full validation will be done in the endpoint
    # This is just a preliminary check