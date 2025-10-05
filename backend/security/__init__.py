"""Security module for crash game"""

from .game_security import (
    GameSecurityValidator,
    GameAction,
    get_game_security,
    init_game_security
)
from .simple_protection import check_anti_spam

__all__ = [
    'GameSecurityValidator',
    'GameAction', 
    'get_game_security',
    'init_game_security',
    'check_anti_spam'
]