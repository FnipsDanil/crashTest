"""Player-related API routes for crash game."""

import math
import logging
import os
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

# Setup logging
logger = logging.getLogger(__name__)

# Import from parent modules
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

router = APIRouter(prefix="/api/player", tags=["player"])

def get_auth_service(request: Request):
    """Get auth service from app state."""
    return getattr(request.app.state, 'auth_service', None)

# Pydantic models
class InitDataRequest(BaseModel):
    init_data: str

class ChannelSubscriptionRequest(BaseModel):
    channel_id: str

class PromoCodeRequest(BaseModel):
    promo_code: str

class BalanceResponse(BaseModel):
    user_id: int
    balance: Decimal

class UserVerificationResponse(BaseModel):
    user_id: int
    user: dict
    auth_date: str
    authenticated: bool

@router.post("/verify-user")
async def verify_user(data: InitDataRequest, request: Request):
    """Verify Telegram user init data."""
    try:
        # Get auth service from app state
        auth_service = get_auth_service(request)
        if not auth_service:
            raise HTTPException(500, "Authentication service not available")
        
        # Validate init data using auth service
        is_valid, parsed_data = auth_service.validate_telegram_init_data(data.init_data)
        
        if not is_valid:
            raise HTTPException(403, "Invalid init data")
        
        # Extract user information
        user_data = parsed_data.get("user", {})
        if not user_data or "id" not in user_data:
            raise HTTPException(400, "User data not found in init data")
        
        user_id = user_data["id"]
        
        # TODO: Create or update user in PostgreSQL with Telegram data
        # This will be connected to the DatabaseService when it's fully integrated
        try:
            # For now, just validate the user data format
            if not auth_service.is_valid_user_id(user_id):
                raise HTTPException(400, "Invalid user ID format")
            
            logger.info(f"✅ User verified: {user_id} ({user_data.get('username', 'no_username')})")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to create/update user in database: {e}")
        
        # Return user info and authentication success
        return UserVerificationResponse(
            user_id=user_id,
            user=user_data,
            auth_date=parsed_data.get("auth_date", ""),
            authenticated=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ User verification error: {e}")
        raise HTTPException(500, f"Authentication failed: {str(e)}")

# These endpoints are implemented in main.py and should be migrated here
# when ready. Removed placeholder implementations to avoid confusion.

@router.get("/profile/{user_id}")
async def get_player_profile(user_id: int):
    """Get player profile information."""
    return {
        "user_id": user_id,
        "username": "placeholder",
        "total_games": 0,
        "total_winnings": Decimal('0.0'),
        "best_coefficient": Decimal('0.0'),
        "win_rate": Decimal('0.0')
    }

@router.get("/history/{user_id}")
async def get_player_history(user_id: int, limit: int = 10, offset: int = 0):
    """Get player game history."""
    return {
        "user_id": user_id,
        "games": [],
        "total_count": 0,
        "limit": limit,
        "offset": offset
    }

@router.post("/check-channel-subscription")
async def check_channel_subscription(
    request: Request,
    data: ChannelSubscriptionRequest
):
    """
    Check channel subscription and grant bonus with maximum security.
    
    🔒 Security Features:
    - Authentication required via middleware
    - Redis locks prevent concurrent requests
    - Comprehensive input validation
    - Telegram API error handling
    - Atomic database transactions
    - ENV-based feature toggle
    """
    from database import get_db
    from services.channel_subscription_service import ChannelSubscriptionService
    
    # 🔄 FEATURE TOGGLE: Check if channel bonus feature is enabled
    channel_bonus_enabled = os.getenv("CHANNEL_BONUS_ENABLED", "true").lower() in ["true", "1", "yes", "on"]
    if not channel_bonus_enabled:
        logger.info("❌ Channel bonus feature is disabled via ENV")
        return {
            "s": False,  # success -> s
            "e": "Feature temporarily disabled"  # error -> e
        }
    
    # 🔒 SECURITY: Authentication is mandatory
    if not hasattr(request.state, 'authenticated') or not request.state.authenticated:
        logger.warning("❌ Unauthorized channel subscription request")
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Get authenticated user data
    if not hasattr(request.state, 'user_data') or not request.state.user_data:
        logger.warning("❌ No user data in authenticated request")
        raise HTTPException(status_code=401, detail="Invalid authentication data")
    
    authenticated_user_id = request.state.user_data["id"]
    
    try:
        # Get services from app state
        redis_service = getattr(request.app.state, 'redis_service', None)
        if not redis_service:
            logger.error("Redis service not available")
            raise HTTPException(status_code=500, detail="Service unavailable")
        
        # Get bot token from environment
        bot_token = os.getenv("TG_BOT_TOKEN")
        if not bot_token:
            logger.error("TG_BOT_TOKEN not configured")
            raise HTTPException(status_code=500, detail="Service configuration error")
        
        # Initialize subscription service
        subscription_service = ChannelSubscriptionService(bot_token, redis_service)
        
        # Get database session
        async for session in get_db():
            try:
                # Check and grant bonus
                result = await subscription_service.check_and_grant_bonus(
                    user_id=authenticated_user_id,
                    channel_id=data.channel_id,
                    authenticated_user_id=authenticated_user_id,
                    session=session
                )
                
                # Log successful operations
                if result.get("success"):
                    # 🚀 КРИТИЧНО: Сжатый ответ для экономии трафика (следуем паттерну проекта)
                    return {
                        "s": True,  # success -> s
                        "a": result.get('bonus_amount'),  # amount -> a
                        "b": result.get('new_balance', 0.0),  # balance -> b
                        "c": data.channel_id  # channel -> c
                    }
                else:
                    # 🚀 КРИТИЧНО: Сжатый ответ для ошибок
                    return {
                        "s": False,  # success -> s
                        "e": result.get('error', 'Unknown error')  # error -> e
                    }
                
            finally:
                await session.close()
        
    except ValueError as e:
        # Validation errors (invalid channel ID, etc.)
        logger.warning(f"Validation error in channel subscription: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        # Unexpected errors
        logger.error(f"❌ Channel subscription error for user {authenticated_user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/user-bonus-status")
async def get_user_bonus_status(request: Request):
    """Get user's bonus status - which bonuses are available/claimed."""
    # 🔒 SECURITY: Authentication is mandatory
    if not hasattr(request.state, 'authenticated') or not request.state.authenticated:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if not hasattr(request.state, 'user_data') or not request.state.user_data:
        raise HTTPException(status_code=401, detail="Invalid authentication data")
    
    user_id = request.state.user_data["id"]
    
    try:
        from database import get_db
        from services.database_service import DatabaseService
        from models import ChannelSubscriptionBonus
        from sqlalchemy import select
        
        # Check channel bonus feature status
        channel_bonus_enabled = os.getenv("CHANNEL_BONUS_ENABLED", "true").lower() in ["true", "1", "yes", "on"]
        
        async for session in get_db():
            result = {
                "promo_codes": {
                    "available": True  # Promo codes are always available
                },
                "channel_bonus": {
                    "available": False,
                    "claimed": False,
                    "enabled": channel_bonus_enabled
                }
            }
            
            if channel_bonus_enabled:
                # Get channel bonus config
                config = await DatabaseService.get_system_setting(session, "channel_bonus_config")
                
                if config and config.get("enabled", False):
                    # Check if user already claimed channel bonus
                    channel_bonus_query = await session.execute(
                        select(ChannelSubscriptionBonus)
                        .where(ChannelSubscriptionBonus.user_id == user_id)
                    )
                    existing_bonus = channel_bonus_query.scalar_one_or_none()
                    
                    result["channel_bonus"] = {
                        "available": existing_bonus is None,
                        "claimed": existing_bonus is not None,
                        "enabled": True,
                        "config": config
                    }
                else:
                    result["channel_bonus"]["enabled"] = False
            
            # 🚀 COMPRESSED: Return minimal response
            return {
                "p": result["promo_codes"]["available"],  # promo_codes available -> p
                "c": result["channel_bonus"]["available"], # channel_bonus available -> c  
                "cc": result["channel_bonus"]["claimed"],  # channel_bonus claimed -> cc
                "ce": result["channel_bonus"]["enabled"],  # channel_bonus enabled -> ce
                "cfg": result["channel_bonus"].get("config") # config -> cfg
            }
            
    except Exception as e:
        logger.error(f"Failed to get user bonus status: {e}")
        return {"p": True, "c": False, "cc": False, "ce": False}

@router.get("/channel-bonus-status") 
async def get_channel_bonus_status(request: Request):
    """Get channel bonus feature status and configuration."""
    # 🔄 FEATURE TOGGLE: Check if channel bonus feature is enabled
    channel_bonus_enabled = os.getenv("CHANNEL_BONUS_ENABLED", "true").lower() in ["true", "1", "yes", "on"]
    if not channel_bonus_enabled:
        return {
            "enabled": False,
            "reason": "Feature disabled via ENV"
        }
    
    # Get configuration from PostgreSQL
    try:
        from database import get_db
        from services.database_service import DatabaseService
        
        async for session in get_db():
            config = await DatabaseService.get_system_setting(session, "channel_bonus_config")
            
            if not config:
                return {
                    "enabled": False,
                    "reason": "Configuration not found in database"
                }
            
            return {
                "enabled": config.get("enabled", False),
                "channels": config.get("channels", {}),
                "default_bonus_amount": config.get("default_bonus_amount", 10.0)
            }
            # НЕ нужно manually закрывать session - get_db() это делает
    except Exception as e:
        logger.error(f"Failed to get channel bonus config: {e}")
        return {
            "enabled": False,
            "reason": "Database error"
        }

@router.get("/channel-bonuses")
async def get_user_channel_bonuses(request: Request):
    """Get all channel bonuses earned by the authenticated user."""
    from database import get_db
    from services.channel_subscription_service import ChannelSubscriptionService
    
    # 🔄 FEATURE TOGGLE: Check if channel bonus feature is enabled
    channel_bonus_enabled = os.getenv("CHANNEL_BONUS_ENABLED", "true").lower() in ["true", "1", "yes", "on"]
    if not channel_bonus_enabled:
        logger.info("❌ Channel bonus feature is disabled via ENV")
        # Return empty results when disabled
        return {
            "b": [],  # bonuses -> b
            "t": 0.0,  # total -> t
            "c": 0  # count -> c
        }
    
    # 🔒 SECURITY: Authentication required
    if not hasattr(request.state, 'authenticated') or not request.state.authenticated:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    authenticated_user_id = request.state.user_data["id"]
    
    try:
        # Get services
        redis_service = getattr(request.app.state, 'redis_service', None)
        bot_token = os.getenv("TG_BOT_TOKEN", "")
        
        subscription_service = ChannelSubscriptionService(bot_token, redis_service)
        
        # Get database session
        async for session in get_db():
            try:
                result = await subscription_service.get_user_channel_bonuses(
                    authenticated_user_id, session
                )
                # 🚀 КРИТИЧНО: Сжатый ответ для экономии трафика
                return {
                    "b": result.get("bonuses", []),  # bonuses -> b
                    "t": result.get("total_earned", 0.0),  # total -> t
                    "c": result.get("channels_count", 0)  # count -> c
                }
                
            finally:
                await session.close()
    
    except Exception as e:
        logger.error(f"Failed to get channel bonuses for user {authenticated_user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/use-promo-code")
async def use_promo_code(
    request: Request,
    data: PromoCodeRequest
):
    """
    Use promo code and grant reward with maximum security.
    
    🔒 Security Features:
    - Authentication required via middleware
    - Redis locks prevent concurrent requests
    - Comprehensive input validation
    - Atomic database transactions
    - Balance tracking with withdrawal requirements
    """
    from database import get_db
    from services.promo_code_service import PromoCodeService
    
    # 🔒 SECURITY: Authentication is mandatory
    if not hasattr(request.state, 'authenticated') or not request.state.authenticated:
        logger.warning("❌ Unauthorized promo code request")
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Get authenticated user data
    if not hasattr(request.state, 'user_data') or not request.state.user_data:
        logger.warning("❌ No user data in authenticated request")
        raise HTTPException(status_code=401, detail="Invalid authentication data")
    
    authenticated_user_id = request.state.user_data["id"]
    
    try:
        # Get services from app state
        redis_service = getattr(request.app.state, 'redis_service', None)
        if not redis_service:
            logger.error("Redis service not available")
            raise HTTPException(status_code=500, detail="Service unavailable")
        
        # Initialize promo code service
        promo_service = PromoCodeService(redis_service)
        
        # Get database session
        async for session in get_db():
            try:
                # Use promo code
                result = await promo_service.use_promo_code(
                    user_id=authenticated_user_id,
                    promo_code=data.promo_code,
                    authenticated_user_id=authenticated_user_id,
                    session=session
                )
                
                # Log successful operations
                if result.get("success"):
                    # 🚀 КРИТИЧНО: Сжатый ответ для экономии трафика
                    return {
                        "s": True,  # success -> s
                        "a": result.get('bonus_amount'),  # amount -> a
                        "b": result.get('new_balance'),  # balance -> b
                        "c": data.promo_code,  # code -> c
                        "wr": result.get('withdrawal_requirement')  # withdrawal_requirement -> wr
                    }
                else:
                    # 🚀 КРИТИЧНО: Сжатый ответ для ошибок
                    return {
                        "s": False,  # success -> s
                        "e": result.get('error', 'Unknown error')  # error -> e
                    }
                
            finally:
                await session.close()
        
    except ValueError as e:
        # Validation errors
        logger.warning(f"Validation error in promo code usage: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        # Unexpected errors
        logger.error(f"❌ Promo code usage error for user {authenticated_user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/promo-code-history")
async def get_promo_code_history(request: Request):
    """Get promo code usage history for the authenticated user."""
    from database import get_db
    from services.promo_code_service import PromoCodeService
    
    # 🔒 SECURITY: Authentication required
    if not hasattr(request.state, 'authenticated') or not request.state.authenticated:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    authenticated_user_id = request.state.user_data["id"]
    
    try:
        # Get services
        redis_service = getattr(request.app.state, 'redis_service', None)
        promo_service = PromoCodeService(redis_service)
        
        # Get database session
        async for session in get_db():
            try:
                result = await promo_service.get_user_promo_uses(
                    authenticated_user_id, session
                )
                # 🚀 КРИТИЧНО: Сжатый ответ для экономии трафика
                return {
                    "p": result.get("promo_uses", []),  # promo_uses -> p
                    "t": result.get("total_earned", "0.00"),  # total -> t
                    "c": result.get("count", 0)  # count -> c
                }
                
            finally:
                await session.close()
    
    except Exception as e:
        logger.error(f"Failed to get promo history for user {authenticated_user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")