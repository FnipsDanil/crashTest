"""Configuration package for crash game backend."""

from .settings import (
    DEBUG,
    ENVIRONMENT,
    TG_BOT_TOKEN,
    REDIS_URL,
    GAME_CONFIG,
    GROWTH_RATE,
    TICK_MS,
    DISABLE_POSTGRESQL_GAME_HISTORY,
    DISABLE_POSTGRESQL_BALANCE_UPDATES,
    get_config_summary,
    get_default_game_config,
    update_game_config
)

from .redis_keys import (
    CRASH_GAME_KEY,
    GAME_PLAYERS_KEY,
    LAST_GAME_PLAYERS_KEY,
    EMPTY_ROUND_FLAG_KEY,
    LAST_CRASH_COEF_KEY,
    GAME_CRASHED_FLAG_KEY,
    USER_BALANCES_KEY,
    USER_STATS_KEY,
    GIFTS_KEY,
    get_payment_key,
    ALL_GAME_KEYS
)

# Import from the main config file at backend/config.py
import os
import sys
import importlib.util

try:
    # Load config.py directly
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.py')
    spec = importlib.util.spec_from_file_location("main_config", config_path)
    main_config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main_config)
    
    # Import variables from the loaded module
    REDIS_KEYS = main_config.REDIS_KEYS
    PERFORMANCE_CONFIG = main_config.PERFORMANCE_CONFIG
    CORS_ORIGINS = main_config.CORS_ORIGINS
    DATABASE_URL = main_config.DATABASE_URL
    PAYMENT_PROVIDER_TOKEN = main_config.PAYMENT_PROVIDER_TOKEN
    WEBHOOK_SECRET = main_config.WEBHOOK_SECRET
    validate_config = main_config.validate_config
    get_config = main_config.get_config
except (ImportError, FileNotFoundError, AttributeError):
    # Fallback in case config.py doesn't exist
    REDIS_KEYS = {
        "CRASH_GAME": "crash_game_state",
        "GAME_PLAYERS": "crash_game_players",
        "LAST_GAME_PLAYERS": "last_game_players", 
        "EMPTY_ROUND_FLAG": "empty_round_flag",
        "LAST_CRASH_COEF": "last_crash_coefficient",
        "GAME_CRASHED_FLAG": "game_just_crashed",
        "USER_BALANCES": "user_balances",
        "USER_STATS": "user_stats",
        "GIFTS": "available_gifts"
    }
    PERFORMANCE_CONFIG = {
        "redis_pool_size": 20,
        "db_pool_size": 10,
        "db_max_overflow": 20,
        "cache_ttl": 300,
        "batch_size": 100,
        "batch_flush_interval": 1.0
    }
    
    # Import from environment variables or use fallback
    import os
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,https://localhost:5173").split(",")
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
    
    def validate_config():
        """Validate configuration - fallback implementation"""
        return True
    
    def get_config():
        """Get configuration summary - fallback implementation"""
        return {
            "redis_keys": REDIS_KEYS,
            "performance": PERFORMANCE_CONFIG
        }

__all__ = [
    # Settings
    "DEBUG",
    "ENVIRONMENT", 
    "TG_BOT_TOKEN",
    "REDIS_URL",
    "GAME_CONFIG",
    "GROWTH_RATE",
    "TICK_MS",
    "DISABLE_POSTGRESQL_GAME_HISTORY",
    "DISABLE_POSTGRESQL_BALANCE_UPDATES",
    "get_config_summary",
    "get_default_game_config",
    "update_game_config",
    
    # Redis keys
    "CRASH_GAME_KEY",
    "GAME_PLAYERS_KEY",
    "LAST_GAME_PLAYERS_KEY", 
    "EMPTY_ROUND_FLAG_KEY",
    "LAST_CRASH_COEF_KEY",
    "GAME_CRASHED_FLAG_KEY",
    "USER_BALANCES_KEY",
    "USER_STATS_KEY",
    "GIFTS_KEY",
    "get_payment_key",
    "ALL_GAME_KEYS",
    
    # From main config
    "REDIS_KEYS",
    "PERFORMANCE_CONFIG", 
    "CORS_ORIGINS",
    "DATABASE_URL",
    "PAYMENT_PROVIDER_TOKEN",
    "WEBHOOK_SECRET",
    "validate_config",
    "get_config"
]