"""Game-related API routes for crash game."""

import time
import json
import logging
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

# Setup logging
logger = logging.getLogger(__name__)

# Import from parent modules
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Game configuration - will be passed from FastAPI app state
from services.redis_service import RedisService
from services.promo_code_service import PromoCodeService
from database import AsyncSessionLocal

router = APIRouter(prefix="/api/game", tags=["game"])

# Pydantic models for request/response
class JoinGameRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    bet_amount: Decimal = Field(..., gt=0, le=50000)

class CashoutRequest(BaseModel):
    user_id: int = Field(..., gt=0)

class PlayerStatusResponse(BaseModel):
    in_game: bool
    bet_amount: Decimal = Decimal('0.0')
    cashout_coef: Decimal = Decimal('0.0')
    cashed_out: bool = False
    can_cashout: bool = False
    win_message: str = ""
    round_won: bool = False
    round_lost: bool = False

def get_game_engine(request: Request):
    """Get game engine from app state."""
    # This will be populated by main_new.py
    return getattr(request.app.state, 'game_engine', None)

@router.get("/current-state")
async def get_current_state(request: Request):
    """Get current game state."""
    try:
        game_engine = get_game_engine(request)
        if not game_engine:
            raise HTTPException(500, "Game engine not available")
        
        return await game_engine.get_current_status()
    except Exception as e:
        logger.error(f"❌ Error getting current state: {e}")
        # Fallback response
        return {
            "coefficient": 1.0,
            "crashed": False,
            "crash_point": 0.0,
            "last_crash_coefficient": 0.0,
            "status": "waiting",
            "time_since_start": 0,
            "countdown_seconds": 10,
            "game_just_crashed": False
        }

@router.post("/join")
async def join_game(request_data: JoinGameRequest, request: Request):
    """Join the current game round."""
    try:
        game_engine = get_game_engine(request)
        if not game_engine:
            raise HTTPException(500, "Game engine not available")
        
        # 🔒 NOTE: Promo code withdrawal restriction is checked atomically in game engine
        # after Redis operation and rolled back if needed - this ensures consistency
        success = await game_engine.join_game(
            request_data.user_id, 
            request_data.bet_amount
        )
        
        if success:
            return {"success": True, "message": "Joined game successfully"}
        else:
            return {"success": False, "message": "Cannot join game at this time"}
            
    except Exception as e:
        logger.error(f"❌ Error joining game: {e}")
        raise HTTPException(500, f"Failed to join game: {str(e)}")

@router.post("/cashout")
async def cashout(request_data: CashoutRequest, request: Request):
    """Cash out from current game."""
    logger.info(f"🚀 GAME_ROUTES CASHOUT CALLED for user {request_data.user_id}")
    try:
        game_engine = get_game_engine(request)
        if not game_engine:
            logger.error(f"❌ Game engine not available in game_routes!")
            raise HTTPException(500, "Game engine not available")
        
        logger.info(f"🎯 Using game engine: {type(game_engine).__name__}")
        
        logger.info(f"📞 Calling game_engine.player_cashout({request_data.user_id})")
        coefficient = await game_engine.player_cashout(request_data.user_id)
        logger.info(f"🎯 Cashout result: {coefficient} (type: {type(coefficient)})")
        
        if coefficient is not None:
            return {
                "success": True, 
                "coefficient": coefficient,
                "message": f"Cashed out at {coefficient}x"
            }
        else:
            return {
                "success": False, 
                "message": "Cannot cash out at this time"
            }
            
    except Exception as e:
        logger.error(f"❌ Error cashing out: {e}")
        raise HTTPException(500, f"Failed to cash out: {str(e)}")

@router.get("/player-status/{user_id}")
async def get_player_status(user_id: int, request: Request):
    """Get player status in current/last round."""
    try:
        game_engine = get_game_engine(request)
        if not game_engine:
            raise HTTPException(500, "Game engine not available")
        
        # Get player data from the game engine
        player_data = await game_engine.player_manager.get_player_data(user_id)
        last_round_data = await game_engine.player_manager.get_last_round_player_data(user_id)
        was_empty = await game_engine.player_manager.was_empty_round()
        
        # Get current game state
        game_state = await game_engine.get_current_status()
        
        # Build player status response
        in_game = player_data is not None
        bet_amount = Decimal(str(player_data.get("bet_amount", 0.0))) if player_data else Decimal('0.0')
        cashed_out = player_data.get("cashed_out", False) if player_data else False
        cashout_coef = Decimal(str(player_data.get("cashout_coef", 0.0))) if player_data else Decimal('0.0')
        
        # Determine if player can cash out
        can_cashout = (
            in_game and 
            not cashed_out and 
            game_state.get("status") == "playing" and
            not game_state.get("crashed", False)
        )
        
        # Determine win/loss messages
        win_message = ""
        round_won = False
        round_lost = False
        
        if last_round_data and last_round_data.get("round_ended"):
            if last_round_data.get("cashed_out"):
                round_won = True
                coef = Decimal(str(last_round_data.get("cashout_coef", 0.0)))
                bet = Decimal(str(last_round_data.get("bet_amount", 0.0)))
                winnings = bet * coef
                win_message = f"Вы выиграли {winnings:.2f} монет на коэффициенте {coef}x!"
            elif not was_empty:
                round_lost = True
        
        return PlayerStatusResponse(
            in_game=in_game,
            bet_amount=bet_amount,
            cashout_coef=cashout_coef,
            cashed_out=cashed_out,
            can_cashout=can_cashout,
            win_message=win_message,
            round_won=round_won,
            round_lost=round_lost
        )
        
    except Exception as e:
        logger.error(f"❌ Error getting player status: {e}")
        # Return safe fallback
        return PlayerStatusResponse(
            in_game=False,
            bet_amount=Decimal('0.0'),
            cashout_coef=Decimal('0.0'),
            cashed_out=False,
            can_cashout=False,
            win_message="",
            round_won=False,
            round_lost=False
        )

@router.get("/stats")
async def get_game_stats(request: Request):
    """Get game statistics."""
    try:
        game_engine = get_game_engine(request)
        if not game_engine:
            return {"error": "Game engine not available"}
        
        engine_stats = await game_engine.get_engine_stats()
        return {
            "engine_stats": engine_stats,
            "config": game_engine.config
        }
    except Exception as e:
        logger.error(f"❌ Error getting game stats: {e}")
        return {"error": str(e)}

@router.get("/config")
async def get_game_config(request: Request):
    """Get game configuration."""
    try:
        game_engine = get_game_engine(request)
        if game_engine:
            return game_engine.config
        else:
            # Fallback config
            return {
                "growth_rate": 1.01,
                "tick_ms": 60,
                "max_coefficient": 100.0,
                "waiting_time": 10,
                "join_time": 2
            }
    except Exception as e:
        logger.error(f"❌ Error getting game config: {e}")
        return {
            "growth_rate": 1.01,
            "tick_ms": 60,
            "max_coefficient": 100.0,
            "waiting_time": 10,
            "join_time": 2
        }

# Legacy compatibility endpoints
@router.get("/current-state", include_in_schema=False)
async def get_current_state_legacy(request: Request):
    """Legacy endpoint - redirect to new format"""
    return await get_current_state(request)

@router.post("/join", include_in_schema=False) 
async def join_game_legacy(request_data: JoinGameRequest, request: Request):
    """Legacy endpoint - redirect to new format"""
    return await join_game(request_data, request)

@router.post("/cashout", include_in_schema=False)
async def cashout_legacy(request_data: CashoutRequest, request: Request):
    """Legacy endpoint - redirect to new format"""
    return await cashout(request_data, request)