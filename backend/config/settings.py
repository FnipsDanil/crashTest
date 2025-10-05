"""
Configuration settings for the crash game backend.
Centralized configuration management.
"""

import os
from typing import Dict, Any

# Environment settings
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Telegram Bot configuration
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

# Payment configuration
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

# PostgreSQL feature flags (for gradual migration)
DISABLE_POSTGRESQL_GAME_HISTORY = os.getenv("DISABLE_POSTGRESQL_GAME_HISTORY", "false").lower() == "true"  # ✅ ВКЛЮЧИЛИ PostgreSQL по умолчанию
DISABLE_POSTGRESQL_BALANCE_UPDATES = os.getenv("DISABLE_POSTGRESQL_BALANCE_UPDATES", "false").lower() == "true"

# Game configuration - FALLBACK ONLY
# ⚠️  This is used ONLY when PostgreSQL system_settings is unavailable
# 🎯 Main config should be managed via database for runtime changes
_DEFAULT_GAME_CONFIG: Dict[str, Any] = {
    "growth_rate": "1.01",  # коэффициент умножения за тик
    "tick_ms": 150,        # интервал обновления в мс  
    "max_coefficient": "100.0",  # максимальный коэффициент
    "waiting_time": 10,   # время ожидания между раундами в секундах
    "join_time": 2,       # время для присоединения к раунду в секундах
    "max_players_per_round": 1000,  # максимальное количество игроков в раунде
    
    # СТАРАЯ СИСТЕМА CRASH_RANGES - ЗАКОММЕНТИРОВАНА
    # 🔒 CRITICAL: Fixed crash_point distribution for proper house edge
    # Target: ~5% house edge = 95% RTP  
    # 🚨 Previous settings had NEGATIVE house edge (system losing money!)
    # "crash_ranges": [
    #     {"min": 1.00, "max": 1.05, "probability": 0.10},
    #     {"min": 1.05, "max": 1.10, "probability": 0.10},
    #     {"min": 1.10, "max": 1.15, "probability": 0.08},
    #     {"min": 1.15, "max": 1.20, "probability": 0.07},
    #     {"min": 1.20, "max": 1.25, "probability": 0.06},
    #     {"min": 1.25, "max": 1.30, "probability": 0.05},
    #     {"min": 1.30, "max": 1.40, "probability": 0.06},
    #     {"min": 1.40, "max": 1.50, "probability": 0.0795},
    #     {"min": 1.50, "max": 1.60, "probability": 0.05},
    #     {"min": 1.60, "max": 1.75, "probability": 0.05},
    #     {"min": 1.75, "max": 2.00, "probability": 0.06},
    #     {"min": 2.00, "max": 2.50, "probability": 0.07},
    #     {"min": 2.50, "max": 3.00, "probability": 0.07},
    #     {"min": 3.00, "max": 4.00, "probability": 0.04},
    #     {"min": 4.00, "max": 5.00, "probability": 0.02},
    #     {"min": 5.00, "max": 7.00, "probability": 0.02},
    #     {"min": 7.00, "max": 10.00, "probability": 0.01},
    #     {"min": 10.00, "max": 15.00, "probability": 0.005},
    #     {"min": 15.00, "max": 20.00, "probability": 0.003},
    #     {"min": 20.00, "max": 30.00, "probability": 0.0015},
    #     {"min": 30.00, "max": 40.00, "probability": 0.0005},
    #     {"min": 40.00, "max": 50.00, "probability": 0.0003},
    #     {"min": 50.00, "max": 70.00, "probability": 0.0001},
    #     {"min": 70.00, "max": 80.00, "probability": 0.00005},
    #     {"min": 80.00, "max": 100.00, "probability": 0.00001}
    # ],
    
    # НОВАЯ СИСТЕМА С HOUSE_EDGE
    "house_edge": "0.10"  # 10% house edge по умолчанию
    
    # СТАРЫЕ КОММЕНТАРИИ О МАТЕМАТИЧЕСКОЙ МОДЕЛИ - ЗАКОММЕНТИРОВАНЫ
    # Mathematical expectation with 1/sqrt(avg) model:
    # Range 1: 1/sqrt(1.10) * 0.8 ≈ 0.76
    # Range 2: 1/sqrt(1.60) * 0.15 ≈ 0.12  
    # Range 3: 1/sqrt(6.00) * 0.05 ≈ 0.02
    # Total ≈ 0.90 = 10% house edge (conservative)
    # "crash_ranges": [
    #     {"min": "1.01", "max": "1.20", "probability": "0.7"},   # 70% низкие крахи (avg 1.105, expected 0.7735)
    #     {"min": "1.20", "max": "1.45", "probability": "0.2"},   # 20% средние крахи (avg 1.325, expected 0.265)
    #     {"min": "1.45", "max": "2.15", "probability": "0.1"}    # 10% высокие крахи (avg 1.80, expected 0.18)
    # ]
    # Mathematical verification: 0.7735 + 0.265 + 0.18 = 1.2185 
    # Still needs adjustment: multiply by 0.95/1.2185 = 0.78
}

# Game configuration - will be set from PostgreSQL in main.py
GAME_CONFIG: Dict[str, Any] = None

# For backward compatibility - will be updated when GAME_CONFIG is loaded
GROWTH_RATE = 1.01
TICK_MS = 150

# Default player limit
DEFAULT_MAX_PLAYERS_PER_ROUND = 1000

def get_default_game_config() -> Dict[str, Any]:
    """Get default game configuration for fallback when PostgreSQL is unavailable."""
    return _DEFAULT_GAME_CONFIG.copy()

def update_game_config(config: Dict[str, Any]) -> None:
    """Update global game configuration from PostgreSQL system_settings.
    
    This is called when config is loaded from database at startup.
    Changes to PostgreSQL system_settings will require server restart.
    """
    from decimal import Decimal
    global GAME_CONFIG, GROWTH_RATE, TICK_MS
    
    # Convert string values back to appropriate types for runtime use
    processed_config = config.copy()
    
    # Convert decimal fields from strings to Decimal objects if needed
    if "growth_rate" in processed_config:
        if isinstance(processed_config["growth_rate"], str):
            processed_config["growth_rate"] = Decimal(processed_config["growth_rate"])
    
    if "max_coefficient" in processed_config:
        if isinstance(processed_config["max_coefficient"], str):
            processed_config["max_coefficient"] = Decimal(processed_config["max_coefficient"])
    
    # СТАРАЯ ОБРАБОТКА CRASH_RANGES - ЗАКОММЕНТИРОВАНА
    # Process crash_ranges
    # if "crash_ranges" in processed_config:
    #     ranges = []
    #     for r in processed_config["crash_ranges"]:
    #         ranges.append({
    #             "min": Decimal(str(r["min"])) if not isinstance(r["min"], Decimal) else r["min"],
    #             "max": Decimal(str(r["max"])) if not isinstance(r["max"], Decimal) else r["max"],
    #             "probability": Decimal(str(r["probability"])) if not isinstance(r["probability"], Decimal) else r["probability"]
    #         })
    #     processed_config["crash_ranges"] = ranges
    
    # НОВАЯ ОБРАБОТКА HOUSE_EDGE
    if "house_edge" in processed_config:
        if isinstance(processed_config["house_edge"], str):
            processed_config["house_edge"] = Decimal(processed_config["house_edge"])
    
    GAME_CONFIG = processed_config
    GROWTH_RATE = processed_config.get("growth_rate", Decimal("1.01"))
    TICK_MS = processed_config.get("tick_ms", 150)  # 🔧 FIX: Consistent with default config

def get_config_summary() -> str:
    """Get configuration summary for logging."""
    return f"""
📊 Configuration Status:
  - Environment: {ENVIRONMENT}
  - Debug: {DEBUG}
  - PostgreSQL Game History: {'DISABLED' if DISABLE_POSTGRESQL_GAME_HISTORY else 'ENABLED'}
  - PostgreSQL Balance Updates: {'DISABLED' if DISABLE_POSTGRESQL_BALANCE_UPDATES else 'ENABLED'}
  - Telegram Bot: {'CONFIGURED' if TG_BOT_TOKEN else 'NOT CONFIGURED'}
  - Payment Provider: {'CONFIGURED' if PAYMENT_PROVIDER_TOKEN else 'NOT CONFIGURED'}
"""