"""
Redis keys configuration for the crash game.
Centralized key management to avoid conflicts.
"""

# Game state keys
CRASH_GAME_KEY = "crash_game_state"
CASHOUTS_KEY = "crash_game_cashouts"

# Player data keys
GAME_PLAYERS_KEY = "crash_game_players"
LAST_GAME_PLAYERS_KEY = "last_game_players"  # Игроки последнего раунда
EMPTY_ROUND_FLAG_KEY = "empty_round_flag"  # Флаг пустого раунда

# Game result keys
LAST_CRASH_COEF_KEY = "last_crash_coefficient"  # Последний коэффициент краша
GAME_CRASHED_FLAG_KEY = "game_just_crashed"  # Флаг что игра только что крашнулась

# User data keys
USER_BALANCES_KEY = "user_balances"
USER_STATS_KEY = "user_stats"  # Статистика игроков

# System keys
GIFTS_KEY = "available_gifts"  # Доступные подарки

# Key patterns for better organization
def get_payment_key(payload: str) -> str:
    """Get payment tracking key."""
    return f"payment:{payload}"

def get_user_session_key(user_id: int) -> str:
    """Get user session key."""
    return f"user_session:{user_id}"

def get_game_round_key(round_id: str) -> str:
    """Get game round specific key."""
    return f"game_round:{round_id}"

# Key expiration times (in seconds)
PAYMENT_KEY_TTL = 3600  # 1 hour
EMPTY_ROUND_FLAG_TTL = 600  # 10 minutes
GAME_CRASHED_FLAG_TTL = 15  # 15 seconds
SESSION_KEY_TTL = 86400  # 24 hours

# Export all keys for easy import
ALL_GAME_KEYS = [
    CRASH_GAME_KEY,
    CASHOUTS_KEY,
    GAME_PLAYERS_KEY,
    LAST_GAME_PLAYERS_KEY,
    EMPTY_ROUND_FLAG_KEY,
    LAST_CRASH_COEF_KEY,
    GAME_CRASHED_FLAG_KEY,
    USER_BALANCES_KEY,
    USER_STATS_KEY,
    GIFTS_KEY
]