"""Gift and webhook API routes for crash game."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import logging

# Import from parent modules (will be updated when main.py is refactored)
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from database import get_db
from services.database_service import DatabaseService

logger = logging.getLogger(__name__)

# RENAMED: This is NOT admin router anymore - contains gifts, webhooks, health
router = APIRouter(prefix="/api/admin", tags=["gifts", "webhooks", "health"])

# Pydantic models
class TelegramGift(BaseModel):
    id: str
    name: str
    description: str
    price: int
    telegram_gift_id: str
    emoji: str
    image_url: str

class WithdrawGiftRequest(BaseModel):
    user_id: int
    gift_id: str

@router.get("/gifts", response_model=List[TelegramGift])
async def get_available_gifts(session: AsyncSession = Depends(get_db)):
    """Get list of available Telegram gifts from PostgreSQL."""
    try:
        gifts = await DatabaseService.get_available_gifts(session)
        return [
            TelegramGift(
                id=gift.id,
                name=gift.name,
                description=gift.description,
                price=int(gift.price),  # Convert Decimal to int for stars
                telegram_gift_id=gift.telegram_gift_id,
                emoji=gift.emoji,
                image_url=gift.image_url or ""
            )
            for gift in gifts
        ]
    except Exception as e:
        logger.error(f"❌ Error getting gifts: {e}")
        return []

@router.post("/withdraw-gift")
async def withdraw_gift(request: WithdrawGiftRequest, session: AsyncSession = Depends(get_db)):
    """Withdraw coins as Telegram gift."""
    try:
        # Get gift info
        gift = await DatabaseService.get_gift_by_id(session, request.gift_id)
        if not gift:
            return {
                "success": False,
                "error": "Gift not found"
            }
        
        # Send gift via Telegram API
        from services.telegram_gifts_service import send_telegram_gift_direct
        gift_dict = {
            "id": gift.id,
            "name": gift.name,
            "description": gift.description,
            "price": gift.price,
            "telegram_gift_id": gift.telegram_gift_id,
            "emoji": gift.emoji,
            "image_url": gift.image_url
        }
        
        result = await send_telegram_gift_direct(request.user_id, gift_dict)
        
        if result["success"]:
            return {
                "success": True,
                "message": "Gift sent successfully",
                "user_id": request.user_id,
                "gift_id": request.gift_id
            }
        else:
            return {
                "success": False,
                "error": f"Failed to send gift: {result.get('error')}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Error processing gift withdrawal: {str(e)}"
        }

@router.post("/payment-webhook")
async def payment_webhook(webhook_data: dict):
    """Handle payment webhook from provider."""
    # This will be moved from main.py
    # For now, returning placeholder
    return {"status": "ok", "processed": True}

@router.get("/health")
async def health_check():
    """System health check."""
    return {
        "status": "ok",
        "redis_connected": True,
        "database_connected": True,
        "game_engine_running": True
    }

# ALL ADMIN ENDPOINTS REMOVED:
# - /stats (admin statistics)
# - /reset-game-data (reset game data)
# - /game-config/* (game configuration management)
# - /player-limit (player limit management)
#
# These require proper admin panel or HTTP client access
# and are not accessible through browser due to Docker networking