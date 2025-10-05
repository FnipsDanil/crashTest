"""
Refactored main.py for crash game backend.
This is the new modular architecture version.
"""

import os
import json
import time
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import our modular components
# Use original configuration from main.py - get from environment and PostgreSQL
import os

# Environment variables (same as original main.py)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://que-crash.fun")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# GAME_CONFIG will be loaded from PostgreSQL SystemSettings during initialization
from config.settings import get_default_game_config, update_game_config
from services import RedisService, DatabaseService, PaymentService, AuthService
from game import GameEngine
from api import game_router, player_router, admin_router
from api.game_routes import CashoutRequest

# Import existing components for compatibility
from database import init_db, get_db
from migration_service import MigrationService
from middleware import create_auth_middleware, create_rate_limit_middleware
from logging_config import setup_secure_logging, get_security_logger
from security_monitor import init_security_monitoring, get_security_monitor
from performance import init_performance, get_performance_optimizer
from monitor_service import SimpleGameMonitor
from utils.image_utils import get_asset_url

# Global instances
redis_service = RedisService(REDIS_URL)
auth_service = AuthService(TG_BOT_TOKEN, development_mode=DEBUG)  # Use DEBUG environment variable
game_engine = None

# 🛡️ Simple idempotency cache (memory-based, safe for production)
import threading
from typing import Dict, Tuple
from datetime import datetime, timedelta

class SimpleIdempotencyCache:
    def __init__(self, ttl_minutes: int = 5):
        self._cache: Dict[str, Tuple[datetime, any]] = {}
        self._lock = threading.Lock()
        self._ttl = timedelta(minutes=ttl_minutes)
    
    def get(self, key: str) -> any:
        with self._lock:
            self._cleanup()
            if key in self._cache:
                timestamp, value = self._cache[key]
                if datetime.now() - timestamp < self._ttl:
                    return value
                del self._cache[key]
        return None
    
    def set(self, key: str, value: any):
        with self._lock:
            self._cleanup()
            self._cache[key] = (datetime.now(), value)
    
    def _cleanup(self):
        now = datetime.now()
        expired_keys = [k for k, (ts, _) in self._cache.items() if now - ts >= self._ttl]
        for k in expired_keys:
            del self._cache[k]

# Global idempotency cache
idempotency_cache = SimpleIdempotencyCache()
payment_service = PaymentService()
database_service = DatabaseService(redis_service)
migration_service = None  # Will be initialized later
monitor = None  # Will be initialized after game_engine

# 🔒 Security initialization
from security import init_game_security
game_security = None  # Will be initialized later

async def initialize_system():
    """Initialize all system components."""
    global game_engine, migration_service, monitor, game_security
    
    try:
        # Initialize secure logging first
        setup_secure_logging()
        security_logger = get_security_logger()
        
        # Initialize performance optimizations
        await init_performance()
        
        # Initialize Redis connection with retry
        for attempt in range(10):
            try:
                redis_client = await redis_service.connect()
                break
            except Exception as e:
                if attempt < 9:
                    await asyncio.sleep(2)
                else:
                    logger.error(f"Redis connection failed after 10 attempts: {e}")
                    raise
        
        # Initialize security monitoring
        await init_security_monitoring(redis_client)
        
        # 🔒 Initialize game security validator
        import secrets
        security_key = os.getenv("GAME_SECURITY_KEY", secrets.token_hex(32))
        game_security = init_game_security(security_key)
        
        # Log security key for development only
        if ENVIRONMENT == "development":
            security_logger.logger.info(f"DEV: HMAC key configured")
        
        # Initialize database with retry logic
        await init_db()  # Now has built-in retry logic
        
        # ✅ Ensure PostgreSQL partitions exist for game_history
        try:
            from create_partitions import ensure_current_partitions
            await ensure_current_partitions()
        except Exception as e:
            logger.warning(f"Warning: Could not create PostgreSQL partitions: {e}")
        
        # Load or initialize system settings FIRST
        async for session in get_db():
            # 🎯 PRIMARY: Load game config from PostgreSQL system_settings
            stored_config = await DatabaseService.get_system_setting(session, "game_config")
            
            if stored_config:
                # ✅ SUCCESS: Use database configuration (preferred)
                update_game_config(stored_config)
                
                # СТАРАЯ ПРОВЕРКА CRASH_RANGES - ЗАКОММЕНТИРОВАНА
                # Ensure crash_ranges exists in loaded config
                # if "crash_ranges" not in stored_config:
                #     default_config = get_default_game_config()
                #     stored_config["crash_ranges"] = default_config["crash_ranges"]
                #     # Update database with crash_ranges
                #     await DatabaseService.set_system_setting(
                #         session, "game_config", stored_config, 
                #         "Updated game configuration with crash_ranges"
                #     )
                
                # НОВАЯ ПРОВЕРКА HOUSE_EDGE
                # Ensure house_edge exists in loaded config
                if "house_edge" not in stored_config:
                    default_config = get_default_game_config()
                    stored_config["house_edge"] = default_config["house_edge"]
                    # Update database with house_edge
                    await DatabaseService.set_system_setting(
                        session, "game_config", stored_config, 
                        "Updated game configuration with house_edge"
                    )
                    update_game_config(stored_config)
            else:
                # ⚠️  FALLBACK: Database is empty, use settings.py defaults
                logger.error("PostgreSQL system_settings is empty! Using fallback config from settings.py")
                logger.error("To fix: Insert game config into system_settings table or run database migration")
                
                default_config = get_default_game_config()
                await DatabaseService.set_system_setting(
                    session, "game_config", default_config, 
                    "FALLBACK: Default game configuration from settings.py"
                )
                update_game_config(default_config)
            
            # Initialize app version (only if not exists)
            app_version_setting = await DatabaseService.get_system_setting(session, "app_version")
            if not app_version_setting:
                await DatabaseService.set_system_setting(
                    session, "app_version", {"version": "2.0.0"}, 
                    "Modular architecture version"
                )
            
            # 🎯 NEW: Initialize player limit setting
            from config.settings import DEFAULT_MAX_PLAYERS_PER_ROUND
            player_limit_setting = await DatabaseService.get_system_setting(session, "game_player_limit")
            if not player_limit_setting:
                # Default player limit from settings.py
                await DatabaseService.set_system_setting(
                    session, "game_player_limit", {"limit": DEFAULT_MAX_PLAYERS_PER_ROUND}, 
                    "Maximum number of players allowed in a single round"
                )
                player_limit = DEFAULT_MAX_PLAYERS_PER_ROUND
            else:
                player_limit = player_limit_setting.get("limit", DEFAULT_MAX_PLAYERS_PER_ROUND)
            
            # Set player limit in Redis for fast atomic access
            redis_client = await redis_service.get_client()
            await redis_client.set("game_player_limit", str(player_limit))
            
            # 🎁 NEW: Initialize daily gift limit setting
            daily_gift_limit_setting = await DatabaseService.get_system_setting(session, "daily_gift_limit")
            if not daily_gift_limit_setting:
                # Default daily gift limit
                await DatabaseService.set_system_setting(
                    session, "daily_gift_limit", {"limit": 5}, 
                    "Maximum number of gifts a user can purchase per day"
                )
            else:
                limit_value = daily_gift_limit_setting.get("limit", 5)

            # 🎯 NEW: Initialize channel bonus configuration
            channel_bonus_setting = await DatabaseService.get_system_setting(session, "channel_bonus_config")
            if not channel_bonus_setting:
                # Default channel bonus configuration
                await DatabaseService.set_system_setting(
                    session, "channel_bonus_config", {
                        "enabled": True,
                        "default_bonus_amount": 10.0,
                        "channels": {
                            "@your_channel": {
                                "bonus_amount": 10.0,
                                "enabled": True,
                                "description": "Main channel subscription bonus"
                            }
                        },
                        "max_attempts_per_user": 10,
                        "cooldown_minutes": 5
                    }, 
                    "Configuration for channel subscription bonuses"
                )
                logger.info("✅ Initialized default channel bonus configuration")
            else:
                logger.info("✅ Channel bonus configuration found in database")
            
            break
        
        # Initialize migration service for legacy compatibility FIRST
        redis_client = await redis_service.get_client()
        migration_service = MigrationService(redis_client)
        
        # Initialize WebSocket manager first 
        from services.websocket_service import WebSocketManager
        websocket_manager = WebSocketManager(auth_service=auth_service)

        # NOW initialize game engine with loaded config, database service, migration service AND websocket manager
        from config.settings import GAME_CONFIG
        global game_engine
        game_engine = GameEngine(redis_service, GAME_CONFIG, database_service, migration_service, websocket_manager)
        
        # Link game engine to WebSocket manager (cross-reference)
        websocket_manager.game_engine = game_engine
        
        await game_engine.start()
        async for session in get_db():
            await migration_service.sync_gifts_to_postgres(session)
            break

        # Initialize monitoring service
        redis_client = await redis_service.get_client()
        monitor = SimpleGameMonitor(redis_client, game_engine)
        asyncio.create_task(monitor.start_monitoring(interval_seconds=30))

        # 🔧 NEW: Setup Telegram webhook for Stars payments
        try:
            webhook_base_url = os.getenv("WEBHOOK_BASE_URL", f"http://localhost:8000")
            webhook_setup_success = await payment_service.setup_webhook(webhook_base_url)
            
            if not webhook_setup_success:
                logger.error("CRITICAL: Webhook not configured - Stars payments NOT WORKING")
                
        except Exception as e:
            logger.error(f"Critical webhook setup error: {e}")

        # Share services with FastAPI app state
        app.state.game_engine = game_engine
        app.state.auth_service = auth_service
        app.state.redis_service = redis_service
        app.state.payment_service = payment_service
        app.state.migration_service = migration_service
        app.state.monitor = monitor
        app.state.websocket_manager = websocket_manager
            
    except Exception as e:
        logger.error(f"System initialization failed: {e}")
        raise

async def shutdown_system():
    """Shutdown all system components."""
    try:
        if game_engine:
            await game_engine.stop()
        
        await redis_service.disconnect()
        
    except Exception as e:
        logger.error(f"Shutdown error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup
    await initialize_system()
    yield
    # Shutdown
    await shutdown_system()

# Create FastAPI application
app = FastAPI(
    title="CRASHER Game API",
    description="Modular crash gambling game backend",
    version="2.0.0",
    lifespan=lifespan
)

# SECURITY: Add authentication middleware
auth_middleware = create_auth_middleware(
    bot_token=TG_BOT_TOKEN,
    development_mode=DEBUG
)
app.middleware("http")(auth_middleware)

# SECURITY: Add rate limiting middleware
rate_limit_middleware = create_rate_limit_middleware(REDIS_URL)
app.middleware("http")(rate_limit_middleware)

# Mount static files for gift images BEFORE API routers
import os
import mimetypes

# Ensure PNG files are served with correct MIME type
mimetypes.add_type('image/png', '.png')
mimetypes.add_type('image/jpeg', '.jpg')
mimetypes.add_type('image/jpeg', '.jpeg')

# Use custom endpoint for images with proper MIME types and resizing
@app.get("/assets/{file_path:path}")
async def serve_assets(file_path: str):
    from PIL import Image
    from io import BytesIO
    from fastapi.responses import Response
    
    frontend_assets_path = os.path.join(os.path.dirname(__file__), "frontend", "assets")
    full_path = os.path.join(frontend_assets_path, file_path)
    
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Determine MIME type
    if file_path.lower().endswith('.png'):
        media_type = 'image/png'
        format_name = 'PNG'
    elif file_path.lower().endswith(('.jpg', '.jpeg')):
        media_type = 'image/jpeg'
        format_name = 'JPEG'
    elif file_path.lower().endswith('.gif'):
        media_type = 'image/gif'
        format_name = 'GIF'
    elif file_path.lower().endswith('.webp'):
        media_type = 'image/webp'
        format_name = 'WEBP'
    else:
        return FileResponse(full_path, media_type='application/octet-stream')
    
    # Resize image to 72x72
    try:
        with Image.open(full_path) as img:
            # Convert to RGBA if PNG to preserve transparency
            if format_name == 'PNG' and img.mode != 'RGBA':
                img = img.convert('RGBA')
            elif format_name in ['JPEG', 'GIF'] and img.mode not in ['RGB', 'L']:
                img = img.convert('RGB')
            
            # Resize to 72x72
            resized_img = img.resize((72, 72), Image.Resampling.LANCZOS)
            
            # Save to memory
            img_buffer = BytesIO()
            resized_img.save(img_buffer, format=format_name, optimize=True)
            img_buffer.seek(0)
            
            return Response(
                content=img_buffer.getvalue(),
                media_type=media_type,
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "Content-Length": str(len(img_buffer.getvalue()))
                }
            )
    except Exception as e:
        # Fallback to original file if resize fails
        return FileResponse(full_path, media_type=media_type)

# Include API routers
app.include_router(game_router)
app.include_router(player_router)
app.include_router(admin_router)

# 🔧 EXPLICIT OPTIONS HANDLERS FOR DEBUGGING
@app.options("/join")
async def options_join():
    """Explicit OPTIONS handler for /join endpoint"""
    return {"message": "CORS preflight for /join"}

@app.options("/cashout") 
async def options_cashout():
    """Explicit OPTIONS handler for /cashout endpoint"""
    return {"message": "CORS preflight for /cashout"}

# 🔧 CORS DEBUG MIDDLEWARE
@app.middleware("http")
async def cors_debug_middleware(request: Request, call_next):
    """Debug CORS requests"""
    response = await call_next(request)
    return response

# 🔧 Add CORS middleware AFTER all other middleware for proper order
# CORS Origins from environment variable
cors_origins_env = os.getenv("CORS_ORIGINS", "")
CORS_ORIGINS = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()] if cors_origins_env else []
# Always include Telegram origins
CORS_ORIGINS.extend([
    "https://telegram.org",
    "https://web.telegram.org"
])

# 🚀 КРИТИЧНО: GZip compression для экономии HTTP трафика (100 Мбит канал!)
app.add_middleware(
    GZipMiddleware, 
    minimum_size=500,  # Сжимаем ответы больше 500 байт
    compresslevel=6    # Баланс между сжатием и скоростью (1-9, 6 оптимально)
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,  # 🔒 CSRF Protection: Use configured origins instead of "*"
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization", 
        "Content-Type", 
        "Accept", 
        "Origin", 
        "X-Requested-With",
        "X-Telegram-Bot-Api-Secret-Token",
        "X-Telegram-Init-Data",
        "X-Idempotency-Key"  # 🛡️ For duplicate request protection
    ],
)

@app.get("/health")
async def health_check():
    """System health check."""
    try:
        redis_healthy = await redis_service.ping()
        
        # Check database health
        db_healthy = False
        try:
            async for session in get_db():
                db_healthy = await DatabaseService.check_health(session)
                break
        except Exception:
            db_healthy = False
        
        # Check game engine
        engine_healthy = game_engine and game_engine.running if game_engine else False
        
        return {
            "status": "ok" if all([redis_healthy, db_healthy, engine_healthy]) else "degraded",
            "redis": "ok" if redis_healthy else "error",
            "database": "ok" if db_healthy else "error", 
            "game_engine": "ok" if engine_healthy else "error",
            "version": "2.0.0"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "version": "2.0.0"
        }

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "CRASHER Game API",
        "version": "2.0.0",
        "architecture": "modular",
        "status": "running"
    }

# Critical endpoints for immediate compatibility
@app.get("/current-state")
async def current_state(
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """🚀 КРИТИЧНО: Сжатый current-state для экономии трафика (100 Мбит канал!)"""
    try:
        # 🔒 SECURITY: Validate Telegram authentication
        if not x_telegram_init_data:
            raise HTTPException(status_code=401, detail="Telegram authentication required")
            
        is_valid, parsed_data = auth_service.validate_telegram_init_data(x_telegram_init_data)
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid authentication")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth error for current state: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")
        
    game_engine = getattr(request.app.state, 'game_engine', None)
    if game_engine:
        # 🚀 КРИТИЧНО: Получаем полный статус но возвращаем сжатую версию
        full_status = await game_engine.get_current_status()
        # Сжимаем названия полей и убираем избыточные данные для экономии трафика
        return {
            "c": str(full_status.get("coefficient", "1.0")),  # coefficient -> c
            "s": full_status.get("status", "waiting")[:1],    # status -> s, только первая буква
            "cd": full_status.get("countdown_seconds", 0),    # countdown_seconds -> cd
            "cr": 1 if full_status.get("crashed", False) else 0,  # crashed -> cr (bool->int)
            "lc": str(full_status.get("last_crash_coefficient", "1.0")),  # last_crash_coefficient -> lc
            "jc": 1 if full_status.get("game_just_crashed", False) else 0,  # game_just_crashed -> jc
            # Убираем time_since_start и crash_point для экономии и безопасности
        }
    else:
        # Fallback тоже сжимаем
        return {
            "c": "1.0",
            "s": "w",  # waiting -> w
            "cd": 10,
            "cr": 0,
            "lc": "1.0", 
            "jc": 0
        }

from decimal import Decimal
from pydantic import BaseModel, Field

class JoinRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    bet_amount: Decimal = Field(..., gt=0, le=50000)

@app.post("/join")
async def join_round(
    req: JoinRequest, 
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Join game round using GameEngine with integrated balance checking"""
    
    # 🔒 Enhanced security validation (non-breaking addition)
    try:
        from security import get_game_security, check_anti_spam
        from security.telegram_auth import validate_telegram_user
        
        # 🔐 CRITICAL: Validate Telegram authentication
        is_auth_valid, auth_reason = await validate_telegram_user(request, req.user_id, x_telegram_init_data)
        if not is_auth_valid:
            # 🔒 SECURITY: Log authentication failure for monitoring
            from security_monitor import get_security_monitor
            try:
                security_monitor = get_security_monitor(await redis_service.get_async_client())
                await security_monitor.log_auth_failure(req.user_id, "join_endpoint", str(request.client.host) if request.client else "unknown")
            except Exception as e:
                logger.error(f"Failed to log security event: {e}")
            raise HTTPException(403, f"Authentication failed: {auth_reason}")
        
        # Simple spam protection (15+ requests/second)
        if not check_anti_spam(req.user_id, "join"):
            raise HTTPException(429, "Too many requests")
        
        security_validator = get_game_security()
        
        # 🔒 SECURITY: Server-side validation only - no client signatures needed
        # Telegram authentication via init_data is sufficient
        
        # Get user balance for validation
        user_balance = await database_service.get_user_balance(req.user_id)
        
        # Validate bet amount with enhanced security checks
        is_valid, validation_msg = security_validator.validate_bet_amount(
            req.user_id, req.bet_amount, user_balance
        )
        
        if not is_valid:
            raise HTTPException(400, f"Invalid bet: {validation_msg}")
            
        
    except ImportError:
        # Graceful fallback if security module not available
        pass
    except Exception as e:
        logger.error(f"Security validation error: {e}")
        # Continue with basic validation instead of failing
    
    game_engine = getattr(request.app.state, 'game_engine', None)
    websocket_manager = getattr(request.app.state, 'websocket_manager', None)
    if not game_engine:
        logger.error("CRITICAL: game_engine is None!")
        raise HTTPException(400, "Game engine not available")
    
    success = await game_engine.join_game(req.user_id, req.bet_amount)
    
    if success:
        balance = await database_service.get_user_balance(req.user_id)
        
        # 🚀 OPTIMIZATION: Send balance update via WebSocket instead of relying on HTTP polling
        if websocket_manager:
            await websocket_manager.broadcast_balance_update(req.user_id, str(balance), "join_game")
        
        return {"joined": True, "balance": balance}
    else:
        # Check if failure was due to player limit
        player_limit = game_engine.get_last_player_limit_error()
        if player_limit:
            error_message = f"Достигнут максимальный лимит игроков в раунде: {player_limit}"
            logger.error(f"Join failed: {error_message}")
            raise HTTPException(400, error_message)
        else:
            logger.error("Join failed")
            raise HTTPException(400, "Failed to join game")

@app.post("/cashout")
async def cashout(
    req: CashoutRequest, 
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Cashout using GameEngine with integrated balance and stats"""
    import logging
    logger = logging.getLogger(__name__)
    
    # 🔒 Enhanced cashout security validation (non-breaking addition)
    try:
        from security import get_game_security, check_anti_spam
        from security.telegram_auth import validate_telegram_user
        
        # 🔐 CRITICAL: Validate Telegram authentication
        is_auth_valid, auth_reason = await validate_telegram_user(request, req.user_id, x_telegram_init_data)
        if not is_auth_valid:
            # 🔒 SECURITY: Log authentication failure for monitoring
            from security_monitor import get_security_monitor
            try:
                security_monitor = get_security_monitor(await redis_service.get_async_client())
                await security_monitor.log_auth_failure(req.user_id, "cashout_endpoint", str(request.client.host) if request.client else "unknown")
            except Exception as e:
                logger.error(f"Failed to log security event: {e}")
            raise HTTPException(403, f"Authentication failed: {auth_reason}")
        
        # Simple spam protection (15+ requests/second)
        if not check_anti_spam(req.user_id, "cashout"):
            raise HTTPException(429, "Too many requests")
        
        security_validator = get_game_security()
        
        # 🔒 SECURITY: Server-side validation only - no client signatures needed  
        # Telegram authentication via init_data is sufficient
        
        game_engine = getattr(request.app.state, 'game_engine', None)
        if game_engine:
            # Get current game state for validation
            game_state = await game_engine.get_current_status()
            if game_state:
                current_coef = game_state.get("coefficient", "1.0")
                game_status = game_state.get("status", "unknown")
                
                # Validate cashout timing
                is_valid, validation_msg = security_validator.validate_cashout_timing(
                    req.user_id, Decimal(str(current_coef)), game_status
                )
                
                if not is_valid:
                    raise HTTPException(400, f"Invalid cashout: {validation_msg}")
                    
        
    except ImportError:
        # Graceful fallback if security module not available
        pass
    except Exception as e:
        logger.error(f"Cashout security validation error: {e}")
        # Continue with basic validation instead of failing
    
    game_engine = getattr(request.app.state, 'game_engine', None)
    websocket_manager = getattr(request.app.state, 'websocket_manager', None)
    if not game_engine:
        logger.error(f"Game engine not available!")
        raise HTTPException(400, "Game engine not available")
    
    cashout_result = await game_engine.player_cashout(req.user_id)
    if cashout_result:
        balance = await database_service.get_user_balance(req.user_id)
        
        # 🚀 OPTIMIZATION: Send balance update via WebSocket instead of relying on HTTP polling
        if websocket_manager:
            await websocket_manager.broadcast_balance_update(req.user_id, str(balance), "cashout")
        
        return {
            "cashed_out": True, 
            "coefficient": cashout_result["coefficient"], 
            "win_amount": cashout_result["win_amount"], 
            "balance": balance
        }
    else:
        raise HTTPException(400, "Cannot cash out")

@app.get("/player-status/{user_id}")
async def get_player_status(
    user_id: int, 
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Get player status with SIMPLE message logic"""
    try:
        # 🔒 SECURITY: Validate Telegram authentication
        if not x_telegram_init_data:
            raise HTTPException(status_code=401, detail="Telegram authentication required")
            
        is_valid, parsed_data = auth_service.validate_telegram_init_data(x_telegram_init_data)
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid authentication")
            
        auth_user_id = parsed_data.get("user", {}).get("id")
        if auth_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth error for player status {user_id}: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")
        
    game_engine = getattr(request.app.state, 'game_engine', None)
    # Get current game status
    try:
        state = await game_engine.get_current_status() if game_engine else {}
        game_status = state.get("status", "unknown")
        game_just_crashed = state.get("game_just_crashed", False)
    except:
        game_status = "unknown"
        game_just_crashed = False
    
    # Check current round first - NO MESSAGES during active play
    if game_engine:
        player_data = await game_engine.redis.get_player_data(user_id)
        if player_data:
            return {
                "in_game": True,
                "joined_at": player_data.get("joined_at"),
                "bet_amount": player_data.get("bet_amount"),
                "cashed_out": player_data.get("cashed_out", False),
                "did_cashout_this_round": player_data.get("cashed_out", False),
                "cashout_coef": player_data.get("cashout_coef"),
                "from_last_round": False,
                "game_status": game_status,
                # NO messages during active play
                "show_win_message": False,
                "show_crash_message": False,
                "win_amount": 0,
                "win_multiplier": 0
            }
        
        # ✅ ПРОСТАЯ ЛОГИКА: показываем сообщения ТОЛЬКО в waiting статусе
        if game_status == "waiting":
            # Проверяем игрока из прошлого раунда
            try:
                last_player_data = await game_engine.redis.cache_get(f"last_player_{user_id}")
                if last_player_data:
                    import json
                    if isinstance(last_player_data, str):
                        last_player_data = json.loads(last_player_data)
                    
                    # ИГРОК ИГРАЛ в прошлом раунде
                    if last_player_data.get("bet_amount"):
                        # 1. Выиграл = кешаутился
                        if last_player_data.get("cashed_out") and last_player_data.get("cashout_coef"):
                            bet_amount = Decimal(str(last_player_data.get("bet_amount", 0)))
                            cashout_coef = Decimal(str(last_player_data.get("cashout_coef", 1)))
                            win_amount = (bet_amount * cashout_coef).quantize(Decimal('0.01'))
                            
                            return {
                                "in_game": False,
                                "joined_at": last_player_data.get("joined_at"),
                                "bet_amount": str(bet_amount),
                                "cashed_out": True,
                                "did_cashout_this_round": True,
                                "cashout_coef": str(cashout_coef),
                                "from_last_round": True,
                                "game_status": game_status,
                                "show_win_message": True,
                                "show_crash_message": False,
                                "win_amount": str(win_amount),
                                "win_multiplier": cashout_coef
                            }
                        
                        # 2. Проиграл = не кешаутился
                        else:
                            
                            return {
                                "in_game": False,
                                "joined_at": last_player_data.get("joined_at"),
                                "bet_amount": str(Decimal(str(last_player_data.get("bet_amount", 0)))),
                                "cashed_out": False,
                                "did_cashout_this_round": False,
                                "cashout_coef": None,
                                "from_last_round": True,
                                "game_status": game_status,
                                "show_win_message": False,
                                "show_crash_message": True,
                                "win_amount": 0,
                                "win_multiplier": 0
                            }
            except Exception as e:
                logger.error(f"⚠️ Error checking last player data: {e}")
            
            # ИГРОК НЕ ИГРАЛ в прошлом раунде - показываем "Краш!" если игра крашнулась
            if game_just_crashed:
                return {
                    "in_game": False,
                    "did_cashout_this_round": False,
                    "from_last_round": False,
                    "game_status": game_status,
                    "show_win_message": False,
                    "show_crash_message": True,  # Info crash for non-players
                    "win_amount": 0,
                    "win_multiplier": 0
                }
    
    # Default: no messages
    return {
        "in_game": False,
        "did_cashout_this_round": False,
        "from_last_round": False,
        "game_status": game_status,
        "show_win_message": False,
        "show_crash_message": False,
        "win_amount": 0,
        "win_multiplier": 0
    }

# === MISSING ENDPOINTS FROM ORIGINAL MAIN.PY ===
# Frontend depends on these endpoints without prefixes

@app.get("/balance/{user_id}")
async def get_user_balance(
    user_id: int,
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Get user balance using DatabaseService"""
    try:
        # 🔒 SECURITY: Validate Telegram authentication
        if not x_telegram_init_data:
            raise HTTPException(status_code=401, detail="Telegram authentication required")
            
        is_valid, parsed_data = auth_service.validate_telegram_init_data(x_telegram_init_data)
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid authentication")
            
        auth_user_id = parsed_data.get("user", {}).get("id")
        if auth_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
            
        balance = await database_service.get_user_balance(user_id)
        # 🚀 КРИТИЧНО: Сжатый ответ для экономии трафика
        return {"b": str(balance)}  # balance -> b, убираем user_id (избыточно)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting balance for {user_id}: {e}")
        return {"b": "0.0"}

@app.get("/user-stats/{user_id}")  
async def get_user_stats(
    user_id: int,
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Get user statistics using DatabaseService"""
    try:
        # 🔒 SECURITY: Validate Telegram authentication
        if not x_telegram_init_data:
            logger.warning(f"❌ Unauthorized stats request for user {user_id}")
            raise HTTPException(status_code=401, detail="Telegram authentication required")
            
        is_valid, parsed_data = auth_service.validate_telegram_init_data(x_telegram_init_data)
        if not is_valid:
            logger.warning(f"❌ Invalid auth for stats request user {user_id}")
            raise HTTPException(status_code=401, detail="Invalid authentication")
            
        auth_user_id = parsed_data.get("user", {}).get("id")
        if auth_user_id != user_id:
            logger.warning(f"❌ User {auth_user_id} attempted to access stats for {user_id}")
            raise HTTPException(status_code=403, detail="Access denied")
            
        stats = await database_service.get_user_stats(user_id)
        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting stats for {user_id}: {e}")
        return {"error": str(e)}

@app.get("/user-language/{user_id}")
async def get_user_language(
    user_id: int,
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Get user language from database"""
    try:
        # 🔒 SECURITY: Validate Telegram authentication
        if not x_telegram_init_data:
            logger.warning("❌ Unauthorized user-language request")
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Validate init_data
        is_valid, parsed_data = auth_service.validate_telegram_init_data(x_telegram_init_data)
        if not is_valid:
            logger.warning(f"🚨 Invalid init_data for user-language request")
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        # Verify user ID matches auth
        auth_user_id = parsed_data.get("user", {}).get("id")
        if auth_user_id != user_id:
            logger.warning(f"🚨 User ID mismatch in user-language: {user_id} != {auth_user_id}")
            raise HTTPException(status_code=403, detail="Access denied")
        
        async for session in get_db():
            user = await DatabaseService.get_user_by_telegram_id(session, user_id)
            if user:
                return {"language_code": user.language_code or "en"}
            else:
                # User not found, return default language
                return {"language_code": "en"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting user language for {user_id}: {e}")
        return {"language_code": "en"}  # Default fallback

@app.post("/user-language/{user_id}")
async def set_user_language(
    user_id: int,
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Set user language in database"""
    try:
        # 🔒 SECURITY: Validate Telegram authentication
        if not x_telegram_init_data:
            logger.warning("❌ Unauthorized set-user-language request")
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Validate init_data
        is_valid, parsed_data = auth_service.validate_telegram_init_data(x_telegram_init_data)
        if not is_valid:
            logger.warning(f"🚨 Invalid init_data for set-user-language request")
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        # Verify user ID matches auth
        auth_user_id = parsed_data.get("user", {}).get("id")
        if auth_user_id != user_id:
            logger.warning(f"🚨 User ID mismatch in set-user-language: {user_id} != {auth_user_id}")
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get language from request body
        data = await request.json()
        language_code = data.get("language_code", "en")
        
        # Validate language code
        if language_code not in ["en", "ru"]:
            raise HTTPException(status_code=400, detail="Invalid language code. Supported: en, ru")
        
        async for session in get_db():
            user = await DatabaseService.get_or_create_user(
                session, user_id,
                language_code=language_code
            )
            return {"success": True, "language_code": language_code}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error setting user language for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/update-user-data")
async def update_user_data(request: Request):
    """Update user data from Telegram init_data"""
    try:
        # 🔒 SECURITY: Auth handled by middleware, user data available in request.state
        if not hasattr(request.state, 'authenticated') or not request.state.authenticated:
            logger.warning("❌ Unauthorized update-user-data request")
            raise HTTPException(status_code=401, detail="Authentication required")
            
        user_data = request.state.user_data
        
        user_info = {
            "id": user_data["id"],
            "first_name": user_data.get("first_name", ""),
            "last_name": user_data.get("last_name", ""),
            "username": user_data.get("username", "")
        }
        
        async for session in get_db():
            await DatabaseService.get_or_create_user(
                session, user_info["id"], 
                first_name=user_info.get("first_name", ""),
                last_name=user_info.get("last_name", ""),
                username=user_info.get("username", ""),
                language_code=user_data.get("language_code", "en")
            )
            return {"success": True, "user": user_info}
    except Exception as e:
        logger.error(f"❌ Error updating user data: {e}")
        return {"success": False, "error": str(e)}

@app.get("/leaderboard")
async def get_leaderboard(
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Get leaderboard"""
    try:
        # 🔒 SECURITY: Validate Telegram authentication
        if not x_telegram_init_data:
            logger.warning("❌ Unauthorized leaderboard request")
            raise HTTPException(status_code=401, detail="Telegram authentication required")
            
        is_valid, parsed_data = auth_service.validate_telegram_init_data(x_telegram_init_data)
        if not is_valid:
            logger.warning("❌ Invalid auth for leaderboard request")
            raise HTTPException(status_code=401, detail="Invalid authentication")
            
        # 🔒 SECURITY: Pass current user's telegram_id to identify them without exposing others
        current_user_telegram_id = parsed_data.get("user", {}).get("id") if parsed_data else None
            
        async for session in get_db():
            leaderboard = await DatabaseService.get_leaderboard(session, current_user_telegram_id=current_user_telegram_id)
            return {"leaderboard": leaderboard}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting leaderboard: {e}")
        return {"leaderboard": []}

@app.get("/player-rank/{user_id}")
async def get_player_rank(
    user_id: int,
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Get player rank"""
    try:
        # 🔒 SECURITY: Validate Telegram authentication
        if not x_telegram_init_data:
            logger.warning(f"❌ Unauthorized player rank request for user {user_id}")
            raise HTTPException(status_code=401, detail="Telegram authentication required")
            
        is_valid, parsed_data = auth_service.validate_telegram_init_data(x_telegram_init_data)
        if not is_valid:
            logger.warning(f"❌ Invalid auth for player rank request user {user_id}")
            raise HTTPException(status_code=401, detail="Invalid authentication")
            
        auth_user_id = parsed_data.get("user", {}).get("id")
        if auth_user_id != user_id:
            logger.warning(f"❌ User {auth_user_id} attempted to access rank for {user_id}")
            raise HTTPException(status_code=403, detail="Access denied")
            
        async for session in get_db():
            rank_info = await DatabaseService.get_user_rank(session, user_id)
            return rank_info or {"rank": None, "total_players": 0}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting rank for {user_id}: {e}")
        return {"rank": None, "total_players": 0}

@app.get("/payment-requests")
async def get_user_payment_requests(
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Get user's payment requests"""
    try:
        # 🔒 SECURITY: Validate Telegram authentication
        if not x_telegram_init_data:
            logger.warning("❌ Unauthorized payment-requests request - no init data header")
            raise HTTPException(status_code=401, detail="Telegram authentication required")
        
        
        is_valid, parsed_data = auth_service.validate_telegram_init_data(x_telegram_init_data)
        if not is_valid:
            logger.warning("❌ Invalid auth for payment-requests request")
            raise HTTPException(status_code=401, detail="Invalid authentication")
            
        user_data = parsed_data.get("user", {})
        user_id = user_data.get("id") if user_data else None
        
        async for session in get_db():
            try:
                from services.database_service import DatabaseService
                payment_requests = await DatabaseService.get_user_payment_requests(session, user_id)
                
                # Format payment requests for frontend
                formatted_requests = []
                for pr in payment_requests:
                    # 🎯 NEW: Используем price_stars - фактически списанную цену в звездах
                    display_price = pr.price_stars if hasattr(pr, 'price_stars') and pr.price_stars else pr.price
                    
                    formatted_requests.append({
                        "id": pr.id,
                        "gift_name": pr.gift_name,
                        "price": str(display_price),  # Фактически списанная цена в звёздах
                        "status": pr.status,
                        "cancel_reason": pr.cancel_reason,
                        "created_at": pr.created_at.isoformat() if pr.created_at else None,
                        "approved_at": pr.approved_at.isoformat() if pr.approved_at else None,
                        "completed_at": pr.completed_at.isoformat() if pr.completed_at else None,
                        "gift": {
                            "emoji": pr.gift.emoji if pr.gift else "🎁",
                            "is_unique": pr.gift.is_unique if pr.gift else True,
                            "ton_price": str(pr.gift.ton_price) if pr.gift and pr.gift.ton_price else None
                        }
                    })
                
                return {
                    "success": True,
                    "payment_requests": formatted_requests
                }
                
            except Exception as e:
                logger.error(f"❌ Error getting payment requests for user {user_id}: {e}")
                return {
                    "success": False,
                    "error": "Failed to get payment requests"
                }
    except Exception as e:
        logger.error(f"❌ Error in payment requests endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/gifts")
async def get_gifts(request: Request):
    """Get available gifts from PostgreSQL"""
    try:
        # 🔒 SECURITY: Auth handled by middleware, user data available in request.state
        if not hasattr(request.state, 'authenticated') or not request.state.authenticated:
            logger.warning("❌ Unauthorized gifts request")
            raise HTTPException(status_code=401, detail="Authentication required")
            
        async for session in get_db():
            gifts = await DatabaseService.get_available_gifts(session)
            # Convert to frontend format
            gifts_data = []
            for gift in gifts:
                # Для уникальных подарков рассчитываем цену в звёздах из TON цены
                price_in_stars = gift.price if gift.price else 0
                if gift.is_unique and gift.ton_price:
                    from services.ton_price_service import ton_price_service
                    calculated_price = await ton_price_service.get_stars_price_for_ton(gift.ton_price)
                    if calculated_price:
                        price_in_stars = calculated_price
                    else:
                        logger.error(f"❌ Failed to calculate price for unique gift {gift.id}")
                        continue  # Skip this gift if price calculation failed
                
                gifts_data.append({
                    "id": gift.id,
                    "name": gift.name,
                    "description": gift.description,
                    "price": price_in_stars,  # price in stars (calculated for unique gifts)
                    "ton_price": str(gift.ton_price) if gift.ton_price else None,
                    "telegram_gift_id": gift.telegram_gift_id,
                    "business_gift_id": gift.business_gift_id,
                    "emoji": gift.emoji,
                    "image_url": get_asset_url(request, gift.image_url),
                    "is_unique": gift.is_unique
                })
            return {"gifts": gifts_data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting gifts from PostgreSQL: {e}")
        return {"gifts": []}

# ❌ УДАЛЕН /crash-history endpoint - заменен на WebSocket события

@app.post("/verify-user")
async def verify_user(request: Request):
    """Verify user from Telegram and create user on first app entry"""
    try:
        data = await request.json()
        init_data = data.get("init_data", "")
        
        # Validate using AuthService
        is_valid, parsed_data = auth_service.validate_telegram_init_data(init_data)
        if is_valid:
            user_data = parsed_data.get("user", {})
            if user_data and "id" in user_data:
                # 🎯 CRITICAL FIX: Create user on first app entry, not during game join
                try:
                    async for session in get_db():
                        user = await DatabaseService.get_or_create_user(
                            session, user_data["id"], 
                            username=user_data.get("username"),
                            first_name=user_data.get("first_name", ""),
                            last_name=user_data.get("last_name", ""),
                            language_code=user_data.get("language_code", "en")
                        )
                        break
                except Exception as db_error:
                    logger.error(f"❌ Database error during user creation: {db_error}")
                    # Continue anyway - user data is valid, database issue is separate
                
                return {"valid": True, "user": user_data}
        
        return {"valid": False, "error": "Invalid init_data"}
    except Exception as e:
        logger.error(f"❌ Error verifying user: {e}")
        return {"valid": False, "error": str(e)}

@app.post("/purchase-gift")
async def purchase_gift(request: Request):
    """Purchase a gift using MigrationService - FULL main.py logic"""
    try:
        # 🔒 SECURITY: Auth handled by middleware, user data available in request.state
        if not hasattr(request.state, 'authenticated') or not request.state.authenticated:
            logger.warning("❌ Unauthorized purchase-gift request")
            raise HTTPException(status_code=401, detail="Authentication required")
            
        user_id = request.state.user_id
        user_data = request.state.user_data
        
        data = await request.json()
        gift_id = data.get("gift_id", "")
        
        # 🛡️ OPTIONAL idempotency key - backward compatible
        idempotency_key = request.headers.get("X-Idempotency-Key")
        if idempotency_key:
                # Check if we already processed this request
            cache_key = f"purchase:{user_id}:{idempotency_key}"
            cached_result = idempotency_cache.get(cache_key)
            if cached_result:
                logger.info(f"🔄 Returning cached result for idempotency key {idempotency_key[:8]}...")
                return cached_result
        
        
        # Get WebSocket manager for balance updates
        websocket_manager = getattr(request.app.state, 'websocket_manager', None)
        
        # Use MigrationService for gift purchase with user_data (EXACT main.py logic)
        async for session in get_db():
            try:
                # Import DatabaseService at the beginning of the try block
                from services.database_service import DatabaseService
                from decimal import Decimal
                
                purchase_info = await migration_service.purchase_gift_hybrid(session, user_id, gift_id, user_data)
                
                # Create gift object for sending (from main.py)
                gift_dict = purchase_info["gift"]
                
                # Different logic for unique vs regular gifts
                if gift_dict.get("is_unique", False):
                    # For unique gifts - create payment request instead of sending immediately
                    # 🔧 FIX: Use internal database user_id, not Telegram user_id
                    internal_user_id = purchase_info["user_id"]
                    # 🎯 NEW: Pass actual price in stars that was deducted from balance
                    actual_price_stars = Decimal(str(gift_dict['price']))
                    payment_request = await DatabaseService.create_payment_request(session, internal_user_id, gift_dict['id'], actual_price_stars)
                    
                    # Mark regular purchase as completed (balance already deducted)
                    if "purchase_id" in purchase_info:
                        await DatabaseService.update_gift_purchase_status(
                            session, purchase_info["purchase_id"], "completed"
                        )
                    
                    # Send Telegram alert about new pending request
                    from services.telegram_alerts_service import send_pending_payment_alert
                    await send_pending_payment_alert(
                        user_id=user_id,
                        username=user_data.get('username', ''),
                        gift_name=gift_dict['name'],
                        price=Decimal(str(gift_dict['price']))
                    )
                    
                    # Notify about manual processing
                    gift_result = {
                        "success": True,
                        "message": "Уникальный подарок добавлен в очередь на обработку. Ожидайте до 24 часов."
                    }
                    
                else:
                    # Regular gifts - send immediately
                    from services.telegram_gifts_service import send_telegram_gift_direct
                    gift_result = await send_telegram_gift_direct(user_id, gift_dict)
                
                # Update purchase status based on result (only for regular gifts)
                if "purchase_id" in purchase_info and not gift_dict.get("is_unique", False):
                    if gift_result["success"]:
                        await DatabaseService.update_gift_purchase_status(
                            session, purchase_info["purchase_id"], "sent"
                        )
                        logger.info(f"✅ Gift {gift_dict['name']} sent successfully to user {user_id}")
                    else:
                        await DatabaseService.update_gift_purchase_status(
                            session, purchase_info["purchase_id"], "failed", gift_result.get("error")
                        )
                        logger.error(f"❌ Failed to send gift {gift_dict['name']} to user {user_id}: {gift_result.get('error')}")
                        
                        # Return error to user if gift sending failed
                        return {
                            "success": False,
                            "error": f"Failed to send gift: {gift_result.get('error')}"
                        }
                
                # 🚀 OPTIMIZATION: Send balance update via WebSocket instead of relying on HTTP polling
                if websocket_manager and gift_result["success"]:
                    await websocket_manager.broadcast_balance_update(user_id, str(purchase_info["new_balance"]), "gift_purchase")
                
                # 🎁 Add temporary gift limit notice to success message
                base_message = gift_result.get("message", "Подарок отправлен!")
                limit_message = f"{base_message}\n\n⚠️ Временно действует ограничение до 5 подарков в день."
                
                result = {
                    "success": True,
                    "gift_sent": gift_dict,
                    "cost": gift_dict["price"], 
                    "new_balance": purchase_info["new_balance"],
                    "message": limit_message
                }
                
                # 🛡️ Cache successful result if idempotency key provided
                if idempotency_key:
                    idempotency_cache.set(cache_key, result)
                
                return result
                
            except Exception as e:
                # Handle different error types (from main.py)
                if "Insufficient balance" in str(e):
                    logger.warning(f"💰 Insufficient balance for user {user_id}")
                    return {"success": False, "error": str(e)}
                elif "Gift not found" in str(e):
                    logger.warning(f"🎁 Gift not found: {gift_id}")
                    return {"success": False, "error": str(e)}
                elif "дневной лимит" in str(e) or "daily limit" in str(e):
                    # Don't log daily limit as error - it's normal business logic
                    return {"success": False, "error": str(e)}
                else:
                    logger.error(f"❌ Error in gift purchase transaction: {e}")
                    # For other errors, try to refund if balance was deducted
                    try:
                        await migration_service.update_user_balance_hybrid(session, user_id, 0, "error_check")
                    except Exception as restore_e:
                        logger.error(f"❌ Failed to restore balance: {restore_e}")
                    return {"success": False, "error": f"Failed to process gift purchase: {str(e)}"}
            break
            
    except Exception as e:
        logger.error(f"❌ Error purchasing gift: {e}")
        return {"success": False, "error": str(e)}

@app.post("/create-invoice")
async def create_invoice(request: Request):
    """Create payment invoice using PaymentService with idempotency protection"""
    try:
        # 🔒 SECURITY: Auth handled by middleware, user data available in request.state
        if not hasattr(request.state, 'authenticated') or not request.state.authenticated:
            logger.warning("❌ Unauthorized create-invoice request")
            raise HTTPException(status_code=401, detail="Authentication required")
            
        user_id = request.state.user_id
        
        data = await request.json()
        
        # 🔒 SECURITY FIX: Строгая валидация amount на входе
        try:
            amount = int(data.get("amount", 100))
            if not (10 <= amount <= 1000000):  # Минимальный депозит 10 звёзд
                return {"success": False, "error": "Amount must be between 10 and 1000000 stars"}
        except (ValueError, TypeError):
            return {"success": False, "error": "Invalid amount format - must be integer"}
            
        title = data.get("title", "Пополнение баланса")
        description = data.get("description", "Покупка звёзд для игры")
        
        # 🔒 IDEMPOTENCY: Check for existing pending invoice
        existing_invoice = await redis_service.get_pending_invoice(user_id, amount)
        if existing_invoice:
            # Verify invoice is still valid (not expired)
            created_at = existing_invoice.get("created_at", 0)
            import time
            if time.time() - created_at < 3600:  # 1 hour validity
                return existing_invoice
            else:
                # Remove expired invoice from cache
                await redis_service.delete_cache(f"invoice_pending:{user_id}:{amount}")
                logger.info(f"🗑️ Removed expired invoice for user {user_id}, amount {amount}")
        
        # Create new invoice using PaymentService
        invoice_result = await payment_service.create_telegram_invoice(
            user_id=user_id,
            amount=amount,
            title=title,
            description=f"{description} - {amount} звёзд"
        )
        
        # Save payment info to Redis for tracking (existing logic)
        import time
        payment_info = {
            "user_id": user_id,
            "amount": amount,
            "payload": invoice_result["payment_payload"],
            "status": "pending",
            "created_at": time.time()
        }
        await redis_service.cache_set(f"payment:{invoice_result['payment_payload']}", payment_info, 3600)
        
        # Prepare response data
        response_data = {
            "success": True,
            "payment_payload": invoice_result["payment_payload"],
            "message_id": invoice_result["message_id"],
            "invoice_link": invoice_result["invoice_link"],
            "invoice_slug": invoice_result["invoice_slug"],
            "amount": amount,
            "message": f"Invoice created for {amount} stars",
            "created_at": time.time()
        }
        
        # 🔒 IDEMPOTENCY: Cache this response for duplicate protection
        await redis_service.set_pending_invoice(user_id, amount, response_data, 3600)
        
        return response_data
        
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"❌ Error creating invoice: {e}")
        return {"success": False, "error": "Failed to create invoice"}

@app.get("/payment-status/{payment_payload}")
async def get_payment_status(payment_payload: str):
    """Get payment status"""
    try:
        # Check payment status from Redis cache
        payment_info = await redis_service.cache_get(f"payment:{payment_payload}")
        if payment_info:
            return {"status": payment_info.get("status", "pending"), "payload": payment_payload}
        return {"status": "pending", "payload": payment_payload}
    except Exception as e:
        logger.error(f"❌ Error getting payment status: {e}")
        return {"status": "error", "error": str(e)}

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Handle Telegram payment webhooks for Stars payments"""
    try:
        body = await request.body()
        
        # 🔒 SECURITY: Validate webhook secret token if configured
        secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not payment_service.validate_webhook_secret_token(secret_token):
            logger.warning("❌ Invalid webhook secret token")
            raise HTTPException(status_code=403, detail="Invalid secret token")
        
        data = await request.json()
        
        # Handle pre_checkout_query
        if "pre_checkout_query" in data:
            query = data["pre_checkout_query"]
            query_id = query["id"]
            
            
            # Answer pre-checkout query (approve all valid requests)
            import aiohttp
            import os
            async with aiohttp.ClientSession() as session:
                url = f"https://api.telegram.org/bot{os.getenv('TG_BOT_TOKEN')}/answerPreCheckoutQuery"
                response_data = {"pre_checkout_query_id": query_id, "ok": True}
                
                async with session.post(url, json=response_data) as response:
                    if response.status != 200:
                        logger.error(f"❌ Failed to approve pre-checkout query: {await response.text()}")
        
        # Handle regular messages (commands)
        elif "message" in data and not data["message"].get("successful_payment"):
            message = data["message"]
            user_id = message["from"]["id"]
            text = message.get("text", "")
            
            
            # Handle /start command
            if text == "/start":
                await handle_start_command(user_id)
            # Handle /support command  
            elif text == "/support":
                await handle_support_command(user_id)
            # Handle /help command
            elif text == "/help":
                await handle_help_command(user_id)
            # Handle any other text message (for unique gift interaction requirement)
            else:
                await handle_any_message(user_id, text)
        
        # Handle callback queries
        elif "callback_query" in data:
            callback = data["callback_query"]
            user_id = callback["from"]["id"]
            callback_data = callback.get("data", "")
            message_id = callback["message"]["message_id"]
            
            
            # Answer callback query first
            await answer_callback_query(callback["id"])
            
            # Handle different callback types
            if callback_data == "support":
                await handle_support_callback(user_id, message_id)
            elif callback_data == "help":
                await handle_help_callback(user_id, message_id)
            elif callback_data == "main_menu":
                await handle_main_menu_callback(user_id, message_id)
        
        # Handle successful_payment
        elif "message" in data and data["message"].get("successful_payment"):
            payment = data["message"]["successful_payment"]
            user_id = data["message"]["from"]["id"]
            
            # 🔒 SECURITY FIX: Валидация user_id из Telegram webhook
            try:
                user_id = int(user_id)
                if user_id <= 0:
                    logger.error(f"🚨 Invalid user_id in webhook: {user_id}")
                    return {"ok": False, "error": "Invalid user_id"}
            except (ValueError, TypeError):
                logger.error(f"🚨 Non-integer user_id in webhook: {user_id}")
                return {"ok": False, "error": "Invalid user_id format"}
            
            
            # Parse payment payload to get amount and user info
            payload_info = payment_service.get_payment_info(payment["invoice_payload"])
            
            if payload_info["type"] == "stars":
                amount = payload_info["amount"]
                
                # 🔒 SECURITY FIX: Дополнительная валидация amount из payload
                if not isinstance(amount, int) or amount < 10 or amount > 1000000:
                    logger.error(f"🚨 Invalid amount in parsed payload: {amount}")
                    return {"ok": False, "error": "Invalid payment amount"}
                telegram_charge_id = payment.get("telegram_payment_charge_id")
                provider_charge_id = payment.get("provider_payment_charge_id")
                
                
                # Credit user balance using existing database service
                extra_data = {
                    "telegram_payment_charge_id": telegram_charge_id,
                    "provider_payment_charge_id": provider_charge_id,
                    "invoice_payload": payment["invoice_payload"]
                }
                
                try:
                    # 🔓 PROMO CODE: Balance unlock now happens inside update_user_balance_safe for deposit transactions
                    new_balance = await database_service.update_user_balance_safe(
                        user_id, amount, "deposit", extra_data
                    )
                    
                    # Update payment status in cache
                    payment_info = await redis_service.cache_get(f"payment:{payment['invoice_payload']}")
                    if payment_info:
                        payment_info["status"] = "completed"
                        await redis_service.cache_set(f"payment:{payment['invoice_payload']}", payment_info, 3600)
                    
                    # Clear idempotency cache - payment completed
                    await redis_service.delete_cache(f"invoice_pending:{user_id}:{amount}")
                    
                    # Send WebSocket balance update if available
                    websocket_manager = getattr(request.app.state, 'websocket_manager', None)
                    if websocket_manager:
                        await websocket_manager.broadcast_balance_update(user_id, str(new_balance), "telegram_payment")
                    
                except Exception as balance_error:
                    logger.error(f"❌ Failed to update balance for user {user_id}: {balance_error}")
                    return {"ok": False, "error": "Balance update failed"}
            else:
                logger.warning(f"⚠️ Unknown payment type: {payload_info['type']}")
        
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"❌ Telegram webhook error: {e}")
        return {"ok": False, "error": str(e)}

# Security monitoring endpoints  
# @app.get("/admin/security/dashboard")
# async def get_security_dashboard():
#     """Get security monitoring dashboard data"""
#     monitor = get_security_monitor(redis_service.get_client())
#     dashboard_data = monitor.get_dashboard_data()
#     return {"security_dashboard": dashboard_data}

# @app.get("/admin/performance/stats")
# async def get_performance_stats():
#     """Get performance statistics"""
#     optimizer = get_performance_optimizer()
#     stats = optimizer.get_performance_stats()
#     return {"performance_stats": stats}

# @app.get("/admin/system/status")
# async def get_system_status():
#     """Get simple system status from monitoring service"""
#     try:
#         if hasattr(app.state, 'monitor') and app.state.monitor:
#             dashboard_data = await app.state.monitor.get_dashboard_data()
#             return {"status": "ok", "data": dashboard_data}
#         else:
#             return {"status": "error", "error": "Monitor not available"}
#     except Exception as e:
#         return {"status": "error", "error": str(e)}

# @app.get("/admin/system/dashboard")
# async def system_dashboard():
#     """Simple HTML dashboard for system monitoring"""
#     html = """
#     <!DOCTYPE html>
#     <html><head><title>🚀 Crash Stars Game Monitor</title></head>
#     <body style="font-family: monospace; background: #1a1a1a; color: #00ff00; padding: 20px;">
#         <h1>🚀 Crash Stars Game System Status</h1>
#         <div id="status">Loading...</div>
#         <script>
#             async function updateStatus() {
#                 try {
#                     const res = await fetch('/admin/system/status');
#                     const data = await res.json();
#                     document.getElementById('status').innerHTML = 
#                         '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
#                 } catch (e) {
#                     document.getElementById('status').innerHTML = 
#                         '<span style="color: red;">Error loading status: ' + e.message + '</span>';
#                 }
#             }
            
#             updateStatus();
#             setInterval(updateStatus, 5000); // Update every 5 seconds
#         </script>
#     </body></html>
#     """
#     from fastapi.responses import HTMLResponse
#     return HTMLResponse(html)

# WebSocket endpoint for real-time updates - OPTIMIZED VERSION
# 🔒 SECURITY: WebSocket validation constants
WEBSOCKET_MAX_MESSAGE_SIZE = 1024  # 1KB per message
WEBSOCKET_ALLOWED_MESSAGE_TYPES = {"subscribe", "unsubscribe", "ping", "pong", "get_player_status"}
WEBSOCKET_ALLOWED_EVENT_TYPES = {"game_state", "crash_history", "player_status", "balance_update"}

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int, init_data: str = ""):
    """WebSocket endpoint for real-time game updates - OPTIMIZED to replace high-frequency HTTP polling"""
    ws_manager = getattr(app.state, 'websocket_manager', None)
    if not ws_manager:
        logger.error("❌ WebSocket manager not available")
        await websocket.close(code=4503, reason="Service unavailable")
        return
    
    # 🚀 КРИТИЧНО: Включаем WebSocket compression на уровне протокола для максимальной экономии трафика
    # Проверяем поддержку compression в заголовках клиента
    accept_extensions = websocket.headers.get("sec-websocket-extensions", "")
    supports_compression = "permessage-deflate" in accept_extensions.lower()
    
    if supports_compression:
        pass
    else:
        pass
    
    # Connect user
    connected = await ws_manager.connect(websocket, user_id, init_data)
    if not connected:
        return
    
    try:
        # Auto-subscribe to game events (replaces polling) - avoid duplicates
        # Check current subscriptions first
        current_subs = ws_manager.connection_info.get(user_id, {}).get("subscriptions", set())
        if "game_state" not in current_subs:
            await ws_manager.subscribe(user_id, "game_state")
        if "crash_history" not in current_subs:
            await ws_manager.subscribe(user_id, "crash_history")
        if "player_status" not in current_subs:
            await ws_manager.subscribe(user_id, "player_status")
        if "balance_update" not in current_subs:
            await ws_manager.subscribe(user_id, "balance_update")
        
        # IMMEDIATE: Send current state right after connection for instant loading
        try:
            # Send immediate game state
            if ws_manager.game_engine:
                current_state = await ws_manager.game_engine.get_current_status()
                if current_state:
                    game_data = {
                        "coefficient": str(current_state.get("coefficient", "1.0")),
                        "status": current_state.get("status", "waiting"),
                        "countdown": int(current_state.get("countdown_seconds", 0)),
                        "crashed": current_state.get("crashed", False),
                        "crash_point": str(current_state.get("crash_point", "0.0")),
                        "last_crash_coefficient": str(current_state.get("last_crash_coefficient", "1.0")),
                        "time_since_start": int(current_state.get("time_since_start", 0)),
                        "game_just_crashed": current_state.get("game_just_crashed", False)
                    }
                    import time
                    await ws_manager.send_to_user(user_id, {
                        "type": "game_state",
                        "timestamp": time.time(),
                        "data": game_data
                    })
            
            # 📈 Crash history now sent automatically in subscribe() method
            
            # Send immediate player status
            player_status = await ws_manager._get_player_status(user_id)
            if player_status:
                await ws_manager.send_to_user(user_id, {
                    "type": "player_status",
                    "timestamp": time.time(),
                    "data": player_status
                })
                
        except Exception as e:
            logger.error(f"⚠️ Error sending immediate data to user {user_id}: {e}")
        
        # Listen for client messages
        while True:
            try:
                # Wait for client messages
                data = await websocket.receive_text()
                
                # 🔒 SECURITY: Message size validation (prevent DoS attacks)
                if len(data) > WEBSOCKET_MAX_MESSAGE_SIZE:
                    logger.warning(f"🚨 WebSocket message too large from user {user_id}: {len(data)} bytes > {WEBSOCKET_MAX_MESSAGE_SIZE}")
                    # Update behavior score for sending oversized messages
                    ws_manager._update_user_behavior_score(user_id, "oversized_message")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Message too large",
                        "timestamp": time.time()
                    }))
                    continue
                
                message = json.loads(data)
                
                # 🔒 SECURITY: Basic message structure validation (prevent malformed messages)
                if not isinstance(message, dict):
                    logger.warning(f"🚨 WebSocket message not a dict from user {user_id}: {type(message)}")
                    ws_manager._update_user_behavior_score(user_id, "malformed_message")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Message must be a JSON object",
                        "timestamp": time.time()
                    }))
                    continue
                
                message_type = message.get("type")
                
                # 🔒 SECURITY: Validate message type (prevent arbitrary message types)
                if message_type not in WEBSOCKET_ALLOWED_MESSAGE_TYPES:
                    logger.warning(f"🚨 Unknown WebSocket message type from user {user_id}: {message_type}")
                    ws_manager._update_user_behavior_score(user_id, "unknown_message_type")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Unknown message type",
                        "timestamp": time.time()
                    }))
                    continue
                
                if message_type == "subscribe":
                    event_type = message.get("event")
                    
                    # 🔒 SECURITY: Validate event type for subscribe messages
                    if not event_type or not isinstance(event_type, str) or event_type not in WEBSOCKET_ALLOWED_EVENT_TYPES:
                        logger.warning(f"🚨 Invalid event type in subscribe from user {user_id}: {event_type}")
                        ws_manager._update_user_behavior_score(user_id, "invalid_event_type")
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Invalid event type",
                            "timestamp": time.time()
                        }))
                        continue
                    
                    if event_type:
                        await ws_manager.subscribe(user_id, event_type)
                        await websocket.send_text(json.dumps({
                            "type": "subscribed",
                            "event": event_type,
                            "timestamp": time.time()
                        }))
                
                elif message_type == "unsubscribe":
                    event_type = message.get("event")
                    
                    # 🔒 SECURITY: Validate event type for unsubscribe messages (same as subscribe)
                    if not event_type or not isinstance(event_type, str) or event_type not in WEBSOCKET_ALLOWED_EVENT_TYPES:
                        logger.warning(f"🚨 Invalid event type in unsubscribe from user {user_id}: {event_type}")
                        ws_manager._update_user_behavior_score(user_id, "invalid_event_type")
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Invalid event type",
                            "timestamp": time.time()
                        }))
                        continue
                    
                    if event_type:
                        await ws_manager.unsubscribe(user_id, event_type)
                        await websocket.send_text(json.dumps({
                            "type": "unsubscribed", 
                            "event": event_type,
                            "timestamp": time.time()
                        }))
                
                elif message_type == "pong":
                    # Client responded to ping - update last activity
                    if user_id in ws_manager.connection_info:
                        ws_manager.connection_info[user_id]["last_ping"] = time.time()
                
                elif message_type == "ping":
                    # Client sent ping - respond with pong
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": time.time()
                    }))
                
                elif message_type == "get_player_status":
                    # Send current player status immediately
                    player_status = await ws_manager._get_player_status(user_id)
                    if player_status:
                        await websocket.send_text(json.dumps({
                            "type": "player_status",
                            "timestamp": time.time(),
                            "data": player_status
                        }))
                
            except json.JSONDecodeError as e:
                # 🔒 SECURITY: Log malformed JSON attempts and update behavior score
                logger.warning(f"🚨 Invalid JSON from user {user_id}: {str(e)[:100]}...")
                ws_manager._update_user_behavior_score(user_id, "malformed_json")
                
                # 🔒 SECURITY: Log to security monitor if available
                try:
                    from security_monitor import get_security_monitor
                    security_monitor = get_security_monitor(await ws_manager.redis.get_async_client())
                    await security_monitor.log_security_event(
                        "WEBSOCKET_MALFORMED_JSON",
                        "MEDIUM", 
                        "unknown_ip",  # TODO: Pass real IP from request
                        {
                            "user_id": user_id,
                            "message_size": len(data) if 'data' in locals() else 0,
                            "error": str(e)[:200],
                            "event_type": "websocket_validation"
                        }
                    )
                except Exception as sec_e:
                    logger.error(f"Failed to log security event: {sec_e}")
                
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON format",
                    "timestamp": time.time()
                }))
            except Exception as e:
                # Ignore connection close errors - they're normal when user closes app
                error_str = str(e).strip()
                error_repr = repr(e)
                
                # Check for WebSocket close exceptions and empty errors
                is_normal_close = (
                    not error_str or  # Empty string after strip
                    error_str == "()" or  # Empty tuple
                    "close message has been sent" in error_str or
                    "1001" in error_str or  # GOING_AWAY
                    "1000" in error_str or  # NORMAL_CLOSURE  
                    "1005" in error_str or  # NO_STATUS_RCVD
                    "NO_STATUS_RCVD" in error_str or
                    "NORMAL_CLOSURE" in error_str or
                    "GOING_AWAY" in error_str or
                    "(1000," in error_str or  # Tuple format
                    "(1001," in error_str or  # Tuple format
                    "(1005," in error_str or  # Tuple format
                    "ConnectionClosedError" in error_repr or
                    "ConnectionClosedOK" in error_repr
                )
                
                if not is_normal_close:
                    logger.error(f"❌ Error processing WebSocket message from user {user_id}: {e}")
                break
                
    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket disconnected: user_id={user_id}")
    except Exception as e:
        logger.error(f"❌ WebSocket error for user {user_id}: {e}")
    finally:
        await ws_manager.disconnect(user_id)

@app.get("/ws/stats")
async def websocket_stats(request: Request):
    """Get WebSocket connection statistics"""
    ws_manager = getattr(request.app.state, 'websocket_manager', None)
    if ws_manager:
        return {"websocket_stats": ws_manager.get_stats()}
    else:
        return {"websocket_stats": {"error": "WebSocket manager not available"}}

# Business account endpoints for unique gifts
# @app.get("/admin/business-account/gifts")
# async def get_business_account_gifts(
#     offset: int = 0, 
#     limit: int = 50,
#     is_unique: bool = None
# ):
#     """Get gifts from business account"""
#     try:
#         from services.telegram_gifts_service import telegram_gifts_service
        
#         if not telegram_gifts_service:
#             return {"success": False, "error": "Telegram service not available"}
        
#         result = await telegram_gifts_service.get_business_account_gifts(
#             offset=offset,
#             limit=limit,
#             is_unique=is_unique
#         )
        
#         return result
#     except Exception as e:
#         return {"success": False, "error": str(e)}

# @app.get("/admin/business-account/balance")
# async def get_business_account_balance():
#     """Get business account star balance"""
#     try:
#         from services.telegram_gifts_service import telegram_gifts_service
        
#         if not telegram_gifts_service:
#             return {"success": False, "error": "Telegram service not available"}
        
#         result = await telegram_gifts_service.get_business_account_star_balance()
        
#         return result
#     except Exception as e:
#         return {"success": False, "error": str(e)}

# Telegram Bot Message Handlers
async def send_telegram_message(user_id: int, text: str, reply_markup=None):
    """Send message to Telegram user"""
    import aiohttp
    
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": user_id,
            "text": text,
            "parse_mode": "HTML"
        }
        if reply_markup:
            data["reply_markup"] = reply_markup
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                if response.status == 200:
                    return True
                else:
                    logger.error(f"❌ Failed to send message: {await response.text()}")
                    return False
    except Exception as e:
        logger.error(f"❌ Error sending message: {e}")
        return False

async def send_telegram_photo(user_id: int, photo_url: str, caption: str = "", reply_markup=None):
    """Send photo message to Telegram user"""
    import aiohttp
    
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
        data = {
            "chat_id": user_id,
            "photo": photo_url,
            "parse_mode": "HTML"
        }
        if caption:
            data["caption"] = caption
        if reply_markup:
            data["reply_markup"] = reply_markup
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                if response.status == 200:
                    return True
                else:
                    logger.error(f"❌ Failed to send photo: {await response.text()}")
                    return False
    except Exception as e:
        logger.error(f"❌ Error sending photo: {e}")
        return False

async def edit_telegram_message(user_id: int, message_id: int, text: str, reply_markup=None):
    """Edit existing Telegram message"""
    import aiohttp
    
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageText"
        data = {
            "chat_id": user_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML"
        }
        if reply_markup:
            data["reply_markup"] = reply_markup
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                if response.status == 200:
                    return True
                else:
                    logger.error(f"❌ Failed to edit message: {await response.text()}")
                    return False
    except Exception as e:
        logger.error(f"❌ Error editing message: {e}")
        return False

async def answer_callback_query(callback_query_id: str):
    """Answer callback query"""
    import aiohttp
    
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery"
        data = {"callback_query_id": callback_query_id}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                return response.status == 200
    except Exception as e:
        logger.error(f"❌ Error answering callback query: {e}")
        return False

async def handle_start_command(user_id: int):
    """Handle /start command"""
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "🚀 Запустить игру", "web_app": {"url": WEB_APP_URL}}],
            [
                {"text": "🆘 Поддержка", "callback_data": "support"},
                {"text": "ℹ️ Помощь", "callback_data": "help"}
            ],
            [{"text": "📢 Наш канал", "url": "https://t.me/crasherapp"}]
        ]
    }
    
    text = (
        "🎮 <b>Добро пожаловать в CRASHER!</b>\n\n"
        "🎯 Играй, побеждай и выводи подарки!\n"
        "🎁 Твои выигрыши можно вывести в виде реальных Telegram подарков.\n\n"
        "💎 Подпишись на наш канал и получи единоразовый бонус в 5 звёзд! Функция находится во вкладке \"Профиль\" -> \"Бонусы\".\n\n"
        "Нажми кнопку ниже, чтобы начать:"
    )
    
    await send_telegram_message(user_id, text, keyboard)

async def handle_support_command(user_id: int):
    """Handle /support command"""
    await handle_support_request(user_id)

async def handle_help_command(user_id: int):
    """Handle /help command"""
    keyboard = {
        "inline_keyboard": [
            [{"text": "🚀 Запустить игру", "web_app": {"url": WEB_APP_URL}}],
            [
                {"text": "🆘 Поддержка", "callback_data": "support"},
                {"text": "🔙 Главное меню", "callback_data": "main_menu"}
            ]
        ]
    }
    
    text = (
        "ℹ️ <b>Инструкция по игре CRASHER</b>\n\n"
        "🎮 <b>Как играть:</b>\n"
        "• Делайте ставки и наблюдайте за множителем графика\n"
        "• Заберите выигрыш до того, как множитель графика упадет\n"
        "• Чем дольше ждете, тем больше множитель\n\n"
        "🎁 <b>Вывод подарков:</b>\n"
        "• Выигранные монеты можно обменять на Telegram подарки\n"
        "• Обработка уникальных подарков занимает до 24 часов\n"
        "• Обычные подарки отправляются мгновенно\n\n"
        "• После покупки уникального подарка необходимо написать в чат боту любое сообщение, иначе заявка автоматически отклонится спустя некоторое время\n\n"
        "• Для покупки подарка необходимо выиграть (без учёта проигрышей) сумму, равную половине стоимости подарка\n\n"
        "💰 <b>Баланс:</b>\n"
        "• При покупке подарка средства списываются сразу\n"
        "• Статус заявки можно отслеживать в профиле\n\n"
        "❓ Остались вопросы? Обратитесь в поддержку!"
    )
    
    await send_telegram_message(user_id, text, keyboard)

async def handle_any_message(user_id: int, text: str):
    """Handle any text message - for unique gift interaction requirement"""
    try:
        # Check if user has pending unique gift requests
        async for session in get_db():
            result = await database_service.check_pending_gift_requests(session, user_id)
            if result and result.get("has_pending_unique_gifts"):
                logger.info(f"✅ User {user_id} interacted with message '{text}' - unique gift requirement satisfied")
                
                # Send confirmation
                await send_telegram_message(
                    user_id, 
                    "✅ <b>Спасибо за сообщение!</b>\n\n"
                    "Ваша заявка на уникальный подарок обработана. "
                    "Подарок будет отправлен в течение 24 часов."
                )
            break
    except Exception as e:
        logger.error(f"❌ Error handling user message: {e}")
        
    # For any other message, just acknowledge
    if not text.startswith('/'):
        await send_telegram_message(
            user_id,
            "👋 Привет! Используй команды /start или /help для навигации по боту."
        )

async def handle_support_callback(user_id: int, message_id: int):
    """Handle support callback"""
    await handle_support_request(user_id, message_id)

async def handle_help_callback(user_id: int, message_id: int):
    """Handle help callback"""
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "🚀 Запустить игру", "web_app": {"url": WEB_APP_URL}}],
            [
                {"text": "🆘 Поддержка", "callback_data": "support"},
                {"text": "🔙 Главное меню", "callback_data": "main_menu"}
            ]
        ]
    }
    
    text = (
        "ℹ️ <b>Инструкция по игре CRASHER</b>\n\n"
        "🎮 <b>Как играть:</b>\n"
        "• Делайте ставки и наблюдайте за множителем графика\n"
        "• Заберите выигрыш до того, как множитель графика упадет\n"
        "• Чем дольше ждете, тем больше множитель\n\n"
        "🎁 <b>Вывод подарков:</b>\n"
        "• Выигранные монеты можно обменять на Telegram подарки\n"
        "• Обработка уникальных подарков занимает до 24 часов\n"
        "• Обычные подарки отправляются мгновенно\n\n"
        "• После покупки уникального подарка необходимо написать в чат боту любое сообщение, иначе заявка автоматически отклонится спустя некоторое время\n\n"
        "• Для покупки подарка необходимо выиграть (без учёта проигрышей) сумму, равную половине стоимости подарка\n\n"
        "💰 <b>Баланс:</b>\n"
        "• При покупке подарка средства списываются сразу\n"
        "• Статус заявки можно отслеживать в профиле\n\n"
        "❓ Остались вопросы? Обратитесь в поддержку!"
    )
    
    await edit_telegram_message(user_id, message_id, text, keyboard)

async def handle_main_menu_callback(user_id: int, message_id: int):
    """Handle main menu callback"""
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "🚀 Запустить игру", "web_app": {"url": WEB_APP_URL}}],
            [
                {"text": "🆘 Поддержка", "callback_data": "support"},
                {"text": "ℹ️ Помощь", "callback_data": "help"}
            ]
        ]
    }
    
    text = (
        "🎮 <b>Добро пожаловать в CRASHER!</b>\n\n"
        "🎯 Играй, побеждай и выводи подарки!\n"
        "🎁 Твои выигрыши можно вывести в виде реальных Telegram подарков\n\n"
        "Нажми кнопку ниже, чтобы начать:"
    )
    
    await edit_telegram_message(user_id, message_id, text, keyboard)

async def handle_support_request(user_id: int, message_id: int = None):
    """Handle support request"""
    SUPPORT_USER_ID = os.getenv("SUPPORT_USER_ID", "")
    
    if not SUPPORT_USER_ID:
        text = (
            "❌ <b>Техподдержка временно недоступна</b>\n\n"
            "Попробуйте обратиться позже."
        )
        keyboard = {
            "inline_keyboard": [
                [{"text": "🔙 Главное меню", "callback_data": "main_menu"}]
            ]
        }
        
        if message_id:
            await edit_telegram_message(user_id, message_id, text, keyboard)
        else:
            await send_telegram_message(user_id, text, keyboard)
        return
    
    # Create support link
    if SUPPORT_USER_ID.isdigit():
        support_url = f"tg://user?id={SUPPORT_USER_ID}"
        button_text = "👤 Открыть профиль поддержки"
        instructions = (
            "👇 <b>Как связаться с поддержкой:</b>\n"
            "1️⃣ Нажмите кнопку ниже\n"
            "2️⃣ Откроется профиль специалиста\n"
            "3️⃣ Нажмите <b>\"Написать\"</b> для отправки сообщения"
        )
    else:
        username = SUPPORT_USER_ID.lstrip('@')
        support_url = f"https://t.me/{username}"
        button_text = "💬 Написать в поддержку"
        instructions = (
            "👇 <b>Как связаться с поддержкой:</b>\n"
            "1️⃣ Нажмите кнопку ниже\n"
            "2️⃣ Откроется чат с поддержкой\n"
            "3️⃣ Напишите ваш вопрос"
        )
    
    keyboard = {
        "inline_keyboard": [
            [{"text": button_text, "url": support_url}],
            [{"text": "🔙 Главное меню", "callback_data": "main_menu"}]
        ]
    }
    
    text = (
        "🆘 <b>Техническая поддержка</b>\n\n"
        "📝 Если у вас возникли вопросы или проблемы с:\n"
        "• Выводом подарков\n"
        "• Игровым балансом\n"
        "• Работой приложения\n"
        "• Статусом заявок\n\n"
        f"{instructions}\n\n"
        "⏰ Время ответа: обычно в течение 1-2 часов"
    )
    
    if message_id:
        await edit_telegram_message(user_id, message_id, text, keyboard)
    else:
        await send_telegram_message(user_id, text, keyboard)

# Legacy endpoints (to be migrated to routers)
# These will be moved to their respective router files

# if __name__ == "__main__":
#     import uvicorn
#     server_host = os.getenv("SERVER_HOST", "0.0.0.0")
#     server_port = int(os.getenv("SERVER_PORT", "8000"))
#     uvicorn.run(
#         "main:app", 
#         host=server_host, 
#         port=server_port, 
#         reload=True,
#         log_level="info"
#     )