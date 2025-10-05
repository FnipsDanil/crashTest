"""API package for crash game backend."""

from .game_routes import router as game_router
from .player_routes import router as player_router
from .admin_routes import router as admin_router

__all__ = [
    "game_router",
    "player_router", 
    "admin_router"
]