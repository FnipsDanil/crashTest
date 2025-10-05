"""
Game engine for crash game - ported from main.py
Handles game loop, state management, and player operations
"""

import asyncio
import time
import secrets
import json
import math
import hashlib
import logging
from decimal import Decimal, getcontext
from typing import Dict, Any, Optional, List

# Import database services
from services.database_service import DatabaseService

# Set high precision for Decimal operations
getcontext().prec = 28

# Setup logging
logger = logging.getLogger(__name__)

# 🔒 SECURITY: Import secure time management
try:
    from security.time_security import get_secure_time, detect_time_manipulation, calculate_secure_coefficient, validate_cashout_timing
    SECURE_TIME_AVAILABLE = True
    # Secure time module loaded
except ImportError as e:
    logger.warning(f"🔒 Secure time module not available: {e}, using system time")
    SECURE_TIME_AVAILABLE = False
    
    import os
    import secrets
    
    # 🔒 SECURITY: Enhanced fallback functions with anti-manipulation measures
    def get_secure_time():
        # Basic protection against time manipulation
        system_time = time.time()
        
        # Add entropy to make time harder to predict/manipulate
        entropy = secrets.randbits(32) / (2**32)  # 0-1 float
        jitter = (entropy - 0.5) * 0.001  # ±0.5ms jitter
        
        return system_time + jitter
    
    def detect_time_manipulation():
        # Basic heuristic: if time jumps too much between calls, it might be manipulated
        now = time.time()
        if hasattr(detect_time_manipulation, 'last_time'):
            time_diff = abs(now - detect_time_manipulation.last_time)
            if time_diff > 5.0:  # More than 5 second jump is suspicious
                return True, f"Large time jump detected: {time_diff:.2f}s"
        detect_time_manipulation.last_time = now
        return False, "No manipulation detected"
    
    def calculate_secure_coefficient(start_time, tick_ms, growth_rate, max_coef):
        # Use protected time calculation
        now = get_secure_time()
        elapsed_ms = (now - start_time) * 1000
        ticks = elapsed_ms / tick_ms
        try:
            coef = (growth_rate ** Decimal(str(ticks))).quantize(Decimal('0.01'))
            return min(coef, max_coef)
        except (OverflowError, Exception):
            return max_coef
    
    def validate_cashout_timing(game_start_time, min_delay=0.2):  # Increased from 0.1 to 0.2
        now = get_secure_time()  # Use secure time
        elapsed = now - game_start_time
        if elapsed < min_delay:
            return False, f"Request too early: {elapsed*1000:.0f}ms < {min_delay*1000:.0f}ms"
        return True, f"Timing valid: {elapsed*1000:.0f}ms delay"

# Game configuration (will be passed from main.py)
from services.redis_service import RedisService
from game.crash_generator import CrashGenerator

class GameEngine:
    """Core game engine for crash game"""
    
    def __init__(self, redis_service: RedisService, game_config: Dict[str, Any], database_service=None, migration_service=None, websocket_manager=None):
        self.redis = redis_service
        self.database = database_service
        self.migration_service = migration_service
        self.websocket_manager = websocket_manager
        self.running = False
        self.game_task: Optional[asyncio.Task] = None
        self.config = game_config
        self.secure_random = secrets.SystemRandom()
        
        # 🔒 SECURITY: Use improved CrashGenerator with proper house edge validation
        # ОБНОВЛЕНО: передаем database_service для динамического получения house_edge из БД
        house_edge = game_config.get("house_edge", Decimal('0.10'))
        self.crash_generator = CrashGenerator(database_service=database_service, house_edge=house_edge)
        
        # Game state
        self.current_state = None
        
        # Player limit error tracking
        self.last_player_limit_error = None
        
    async def start(self):
        """Start the game engine"""
        if self.running:
            return
        
        self.running = True
        self.game_task = asyncio.create_task(self._game_loop())
    
    async def stop(self):
        """Stop the game engine"""
        self.running = False
        if self.game_task:
            self.game_task.cancel()
            try:
                await self.game_task
            except asyncio.CancelledError:
                pass
    
    async def _game_loop(self):
        """Main game loop with precise timing - ported from main.py"""
        while self.running:
            try:
                # 🔒 TIMING: Record loop start time for precise timing
                loop_start_time = get_secure_time() if SECURE_TIME_AVAILABLE else time.time()
                
                state = await self.redis.get_game_state()
                
                if not state:
                    await self._start_waiting_period()
                    await asyncio.sleep(1)
                    continue
                
                # 🔒 SECURITY: Use secure time for all timing operations
                now = get_secure_time() if SECURE_TIME_AVAILABLE else time.time()
                
                # Check for time manipulation periodically
                if SECURE_TIME_AVAILABLE:
                    is_manipulated, reason = detect_time_manipulation()
                    if is_manipulated:
                        logger.warning(f"Time manipulation detected: {reason}")
                
                # Waiting period logic
                if state["status"] == "waiting":
                    if now - state["start_time"] >= self.config["waiting_time"]:
                        await self._start_new_round()
                    else:
                        await asyncio.sleep(0.5)
                    continue
                
                # Playing period logic - use secure coefficient calculation
                if SECURE_TIME_AVAILABLE:
                    coef = calculate_secure_coefficient(
                        state["start_time"],
                        self.config["tick_ms"], 
                        Decimal(str(self.config["growth_rate"])),
                        Decimal(str(self.config["max_coefficient"]))
                    )
                else:
                    # Fallback calculation
                    elapsed_ms = (now - state["start_time"]) * 1000
                    ticks = elapsed_ms / self.config["tick_ms"]
                    
                    max_coef = Decimal(str(self.config["max_coefficient"]))
                    growth_rate = Decimal(str(self.config["growth_rate"]))
                    try:
                        coef = (growth_rate ** Decimal(str(ticks))).quantize(Decimal('0.01'))
                        if coef > max_coef:
                            coef = max_coef
                    except (OverflowError, Exception):
                        coef = max_coef
                
                # Check for crash
                if coef >= Decimal(str(state["crash_point"])) and state["status"] != "crashed":
                    await self._handle_crash(state, coef)
                    continue  # Immediately continue to process waiting state
                else:
                    # 🔒 TIMING FIX: Use precise timing to prevent drift accumulation
                    tick_ms = self.config["tick_ms"]
                    target_sleep = tick_ms / 1000.0  # Convert ms to seconds
                    
                    # 🔒 CRITICAL: Account for processing time to maintain consistent intervals
                    loop_end_time = get_secure_time() if SECURE_TIME_AVAILABLE else time.time()
                    processing_time = loop_end_time - loop_start_time
                    
                    # Adjust sleep to maintain precise timing
                    adjusted_sleep = max(0.001, target_sleep - processing_time)  # Min 1ms sleep
                    await asyncio.sleep(adjusted_sleep)
                
            except Exception as e:
                logger.error(f"Game loop error: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _start_waiting_period(self):
        """Start waiting period between rounds - FROM main.py logic"""
        # 🔒 SECURITY: Use secure time for consistency
        current_time = get_secure_time() if SECURE_TIME_AVAILABLE else time.time()
        
        # SAVE last round players BEFORE clearing - CRITICAL for cashout button
        all_players = await self.redis.get_all_players()
        
        # 🔒 CRITICAL: Atomic cleanup of old keys to prevent partial clearing
        keys_to_delete = ["last_game_players", "empty_round_flag"]
        pattern_keys = ["last_player_*"]
        
        cleanup_success = await self.redis.atomic_cache_cleanup(keys_to_delete, pattern_keys)
        if not cleanup_success:
            logger.error("Atomic cache cleanup failed - system may be in inconsistent state")
        
        if all_players:
            saved_count = 0
            for user_id, player_data in all_players.items():
                try:
                    # Add timestamp when saved - use secure time
                    player_data["saved_at"] = current_time
                    player_data["round_ended"] = True
                    
                    # Save in individual keys too (for faster lookup)
                    await self.redis.cache_set(f"last_player_{user_id}", player_data, 600)
                    saved_count += 1
                except Exception as e:
                    logger.error(f"Error saving player {user_id}: {e}")
        else:
            # Set empty round flag if no players
            empty_flag = {"empty_round": True, "round_ended_at": current_time}
            await self.redis.cache_set("empty_round_flag", empty_flag, 600)
        
        # ✅ Создаем новый раунд в PostgreSQL СРАЗУ в waiting период
        game_id = None
        try:
            from config.settings import DISABLE_POSTGRESQL_GAME_HISTORY
            from database import AsyncSessionLocal
            from services.database_service import DatabaseService
            async with AsyncSessionLocal() as session:
                if self.migration_service and not DISABLE_POSTGRESQL_GAME_HISTORY:
                    # Сначала завершаем предыдущий раунд
                    await DatabaseService.complete_previous_round(session)
                    
                    # Создаем новый раунд БЕЗ crash_point (будет установлен позже)
                    game_id = await DatabaseService.create_game_round_without_crash(session)
                    await session.commit()
                    
                    # Сохраняем game_id в Redis для использования при ставках
                    await self.redis.cache_set("current_game_id", str(game_id))
                else:
                    logger.warning("📊 Game round NOT created (PostgreSQL disabled)")
        except Exception as e:
            logger.error(f"⚠️ Failed to create game round in waiting period: {e}")
        
        # Set waiting state
        waiting_state = {
            "start_time": current_time,
            "crash_point": 0.0,
            "status": "waiting"
        }
        await self.redis.set_game_state(waiting_state)
        await self.redis.clear_all_players()  # NOW clear current players
    
    async def _start_new_round(self):
        """Start a new game round"""
        crash_point = await self._generate_crash_point()
        # 🔒 SECURITY: Use secure time for game start
        start_time = get_secure_time() if SECURE_TIME_AVAILABLE else time.time()
        
        # 🔒 CRITICAL: Atomic cleanup of message keys at new round start
        keys_to_delete = ["empty_round_flag", "game_just_crashed"]
        pattern_keys = ["last_player_*"]
        
        cleanup_success = await self.redis.atomic_cache_cleanup(keys_to_delete, pattern_keys)
        if not cleanup_success:
            logger.error("⚠️ New round cache cleanup failed - old messages may persist")
            # Continue anyway as this is not critical for gameplay
        
        game_state = {
            "start_time": start_time,
            "crash_point": str(crash_point),
            "status": "playing"
        }
        
        await self.redis.set_game_state(game_state)
        
        # ✅ Обновляем crash_point в существующем раунде PostgreSQL
        try:
            from config.settings import DISABLE_POSTGRESQL_GAME_HISTORY
            from database import AsyncSessionLocal
            from services.database_service import DatabaseService
            
            # Получаем game_id созданный в waiting период
            game_id_str = await self.redis.cache_get("current_game_id")
            if game_id_str and not DISABLE_POSTGRESQL_GAME_HISTORY:
                game_id = int(game_id_str)
                async with AsyncSessionLocal() as session:
                    if self.migration_service:
                        # Обновляем crash_point в существующем раунде
                        await DatabaseService.update_game_round_crash_point(session, game_id, crash_point)
                        await session.commit()
                    else:
                        logger.warning("📊 Game round NOT updated (migration service disabled)")
            else:
                logger.warning("📊 No current_game_id found or PostgreSQL disabled - crash point not saved")
        except Exception as e:
            logger.error(f"⚠️ Failed to update game round crash point: {e}")
        
    
    async def _handle_crash(self, state: Dict, coef: Decimal):
        """Handle game crash, record losses, and transition to waiting"""
        crash_coef = min(coef, Decimal(str(state["crash_point"])))
        
        # 🔒 CRITICAL: Atomic crash handling to prevent race conditions
        redis_client = await self.redis.get_async_client()
        
        # Watch both game state and players to prevent concurrent modifications  
        await redis_client.watch(self.redis.keys["CRASH_GAME"], self.redis.keys["GAME_PLAYERS"])
        
        try:
            # ШАГ 1: Получаем всех игроков atomically
            all_players = await self.redis.get_all_players()
            
            # ШАГ 2: Атомарно обновляем состояние игры
            pipe = redis_client.pipeline()
            pipe.multi()
            
            # Update game state to crashed
            state["status"] = "crashed"
            # 🔒 CRITICAL FIX: Use SET (not HSET) to match RedisService.set_game_state()
            # Add checksum for consistency with RedisService
            state_with_checksum = state.copy()
            state_with_checksum["_checksum"] = self.redis._calculate_state_checksum(state)
            state_with_checksum["_timestamp"] = time.time()
            pipe.set(self.redis.keys["CRASH_GAME"], json.dumps(state_with_checksum, default=str))
            
            # Cache crash data atomically
            pipe.set("last_crash_coefficient", str(crash_coef))
            pipe.setex("game_just_crashed", 15, "true")
            pipe.lpush("crash_history", str(crash_coef))
            pipe.ltrim("crash_history", 0, 49)
            
            # Execute atomic transaction
            result = await pipe.execute()
            if not result:
                logger.error("🚨 Atomic crash handling failed - concurrent modification detected")
                return  # Retry will happen in next game loop iteration
                
            
        except Exception as e:
            await redis_client.unwatch()
            logger.error(f"❌ Atomic crash handling error: {e}")
            return
        
        # ✅ Записываем total_bet из всех игроков Redis в GameHistory и финализируем раунд
        try:
            from config.settings import DISABLE_POSTGRESQL_GAME_HISTORY
            from services.database_service import DatabaseService
            game_id_str = await self.redis.cache_get("current_game_id")
            if game_id_str and all_players:
                game_id = int(game_id_str)
                from database import AsyncSessionLocal
                async with AsyncSessionLocal() as session:
                    if self.migration_service and not DISABLE_POSTGRESQL_GAME_HISTORY:
                        # Подсчитываем total_bet от ВСЕХ игроков (и выигравших, и проигравших)
                        total_bet_from_all = Decimal('0.00')
                        all_player_count = 0
                        
                        for user_id, player_data in all_players.items():
                            bet_amount = Decimal(str(player_data["bet_amount"]))
                            total_bet_from_all += bet_amount
                            all_player_count += 1
                        
                        # Обновляем GameHistory: устанавливаем правильный total_bet и player_count
                        from sqlalchemy import update
                        from models import GameHistory
                        await session.execute(
                            update(GameHistory)
                            .where(GameHistory.id == game_id)
                            .values(
                                total_bet=total_bet_from_all,
                                player_count=all_player_count
                            )
                        )
                        
                        # Теперь финализируем раунд с правильным house_profit
                        await DatabaseService.finalize_game_round(session, game_id)
                        await session.commit()
        except Exception as e:
            logger.error(f"⚠️ Failed to finalize game round: {e}")
        
        # ШАГ 4: ✅ СИНХРОННАЯ запись в PostgreSQL для гарантированной записи
        if all_players:
            
            for user_id, player_data in all_players.items():
                if not player_data.get("cashed_out", False):
                    bet_amount = player_data["bet_amount"]
                    try:
                        from config.settings import DISABLE_POSTGRESQL_GAME_HISTORY
                        
                        from database import AsyncSessionLocal
                        async with AsyncSessionLocal() as session:
                            if self.migration_service and not DISABLE_POSTGRESQL_GAME_HISTORY:
                                try:
                                    # ✅ Получаем game_id текущего раунда
                                    game_id_str = await self.redis.cache_get("current_game_id")
                                    game_id = int(game_id_str) if game_id_str else None
                                    
                                    if game_id:
                                        # 🔒 FIX: Record ONLY history without touching balance (balance already deducted in join_game)
                                        current_balance = Decimal(str(await self.redis.get_user_balance(user_id)))
                                        user_obj = await DatabaseService.get_user_by_telegram_id(session, user_id)
                                        if user_obj:
                                            await DatabaseService.record_player_bet(
                                                session, user_obj.id, 
                                                game_id, Decimal(str(bet_amount)), current_balance
                                            )
                                        else:
                                            logger.error(f"❌ User {user_id} not found in database during loss recording")
                                        # Player loss recorded to history
                                    else:
                                        logger.warning(f"💸⚠️ No game_id found for player {user_id} loss")
                                        # Fallback к старому методу
                                        await self.migration_service.record_game_hybrid(
                                            session, int(user_id), Decimal(str(bet_amount)), None, Decimal('0.0'),
                                            None, None
                                        )
                                except Exception as e:
                                    logger.error(f"⚠️ PostgreSQL recording failed for {user_id}: {e}")
                            else:
                                logger.warning(f"💸⚠️ Player {user_id} loss NOT recorded (PostgreSQL disabled)")
                    except Exception as e:
                        logger.error(f"❌ Database error for player {user_id}: {e}")
            
        
        # ШАГ 5: НЕМЕДЛЕННО уведомляем игроков через WebSocket
        if self.websocket_manager:
            try:
                await self.websocket_manager.broadcast_immediate_player_status()
                
                # 🔍 DIAGNOSTIC: Check for remaining delayed tasks after immediate broadcast
                remaining_tasks = len(self.websocket_manager.pending_delayed_tasks) if hasattr(self.websocket_manager, 'pending_delayed_tasks') else 0
                if remaining_tasks > 0:
                    await self.websocket_manager.cancel_all_delayed_tasks()
                else:
                    pass
                    
            except Exception as e:
                logger.error(f"❌ Failed to broadcast immediate player status: {e}")
        
        # ШАГ 6: НЕМЕДЛЕННО переходим к waiting (НЕ ДОЖИДАЯСЬ PostgreSQL)
        await self._start_waiting_period()
    
    async def _generate_crash_point(self) -> Decimal:
        """
        Generate crash point using secure CrashGenerator.
        🔒 SECURITY: Now uses improved generator with house edge validation and anti-prediction measures.
        """
        try:
            # Use improved CrashGenerator with cryptographic security and dynamic house_edge from DB
            crash_point = await self.crash_generator.generate_crash_point()
            return crash_point
        except Exception as e:
            logger.error(f"❌ Error in crash generator: {e}")
            # Emergency fallback to ensure game continues
            emergency_crash = Decimal('1.01')  # Minimal crash to protect house edge
            logger.warning(f"⚠️ Emergency fallback crash point: {emergency_crash}")
            return emergency_crash
    
    # 🔒 LUA SCRIPT: Атомарная проверка и создание ставки
    _JOIN_GAME_LUA_SCRIPT = """
    local game_state_key = KEYS[1]
    local players_key = KEYS[2]
    local user_id = ARGV[1]
    local bet_amount = ARGV[2]
    local joined_at = ARGV[3]
    
    -- Проверка состояния игры
    local game_state = redis.call('GET', game_state_key)
    if not game_state then
        return {0, "NO_GAME_STATE"}
    end
    
    local state = cjson.decode(game_state)
    if state.status ~= "waiting" then
        return {0, "GAME_NOT_WAITING"}
    end
    
    -- Проверка что игрок еще не присоединился
    local existing_player = redis.call('HGET', players_key, user_id)
    if existing_player then
        return {0, "ALREADY_JOINED"}
    end
    
    -- Атомарное добавление игрока
    local player_data = cjson.encode({
        joined_at = tonumber(joined_at),
        bet_amount = tonumber(bet_amount),
        cashed_out = false,
        cashout_count = 0
    })
    
    redis.call('HSET', players_key, user_id, player_data)
    return {1, "SUCCESS"}
    """

    # 🔒 ULTIMATE ATOMIC JOIN: Single Lua script that does EVERYTHING atomically
    _ATOMIC_JOIN_GAME_LUA_SCRIPT = """
    local game_key = KEYS[1]
    local players_key = KEYS[2] 
    local balance_key = KEYS[3]
    local user_id = ARGV[1]
    local bet_amount = tonumber(ARGV[2])
    local join_time = tonumber(ARGV[3])
    
    -- ATOMIC CHECK 1: Game must be in waiting state
    local game_state_raw = redis.call('GET', game_key)
    if not game_state_raw then
        return {0, "NO_GAME_STATE"}
    end
    
    local game_state = cjson.decode(game_state_raw)
    if game_state.status ~= "waiting" then
        return {0, "GAME_NOT_WAITING"}
    end
    
    -- ATOMIC CHECK 2: Player not already joined
    local existing_player = redis.call('HGET', players_key, user_id)
    if existing_player and existing_player ~= "RESERVING" then
        return {0, "ALREADY_JOINED"}
    end
    
    -- ATOMIC CHECK 3: Sufficient balance
    local current_balance_raw = redis.call('HGET', balance_key, user_id)
    local current_balance = current_balance_raw and tonumber(current_balance_raw) or 0.00
    
    if current_balance < bet_amount then
        return {0, "INSUFFICIENT_BALANCE"}
    end
    
    -- ATOMIC OPERATION 1: Deduct balance
    local new_balance = current_balance - bet_amount
    redis.call('HSET', balance_key, user_id, tostring(new_balance))
    
    -- ATOMIC OPERATION 2: Add player to game
    local player_data = {
        user_id = tonumber(user_id),
        bet_amount = bet_amount,
        joined_at = join_time,
        cashed_out = false,
        win_amount = 0,
        cashout_coef = 0
    }
    
    redis.call('HSET', players_key, user_id, cjson.encode(player_data))
    
    -- Return success with new balance
    return {1, "SUCCESS", tostring(new_balance)}
    """

    # Player operations
    async def join_game(self, user_id: int, bet_amount) -> bool:
        """Player joins current game with 100% atomic operations (МАКСИМАЛЬНО ПРАВИЛЬНОЕ РЕШЕНИЕ)"""
        try:
            # Clear any previous player limit error
            self.last_player_limit_error = None
            
            # 🔒 STEP 1: ULTIMATE ATOMIC OPERATION - All in one Lua script
            redis_client = await self.redis.get_async_client()
            
            try:
                # Execute the ULTIMATE atomic operation
                result = await redis_client.eval(
                    self._ATOMIC_JOIN_GAME_LUA_SCRIPT,
                    3,  # number of KEYS
                    self.redis.keys["CRASH_GAME"],
                    self.redis.keys["GAME_PLAYERS"],
                    self.redis.keys["USER_BALANCES"],
                    str(user_id),
                    str(bet_amount),
                    str(get_secure_time() if SECURE_TIME_AVAILABLE else time.time())
                )
                
                success, message = result[0], result[1]
                
                if not success:
                    if message == "ALREADY_JOINED":
                        logger.warning(f"🚨 Player {user_id} already joined this round")
                        # 🔒 SECURITY: Log duplicate bet attempt
                        try:
                            from security_monitor import get_security_monitor
                            security_monitor = get_security_monitor(await self.redis.get_async_client())
                            await security_monitor.log_duplicate_bet_attempt(
                                user_id, 0, bet_amount, "unknown_ip"
                            )
                        except Exception as e:
                            logger.error(f"Failed to log security event: {e}")
                    
                    logger.error(f"❌ Atomic join failed: {message}")
                    return False
                
                # 🔒 SUCCESS: Everything completed atomically
                new_balance = Decimal(result[2])
                
                # 🔒 STEP 2: Sync to PostgreSQL (CRITICAL REQUIREMENT - НЕ ЗАБУДЬ ЧТО В ПГ ТОЖЕ НАДО ОБНОВЛЯТЬ)
                if self.database:
                    try:
                        # Update PostgreSQL balance to match Redis (sync source of truth)
                        # Get game_id for bet transaction
                        game_id_str = await self.redis.cache_get("current_game_id")
                        game_id = int(game_id_str) if game_id_str else None
                        
                        # 🔒 CRITICAL: This call includes withdrawal_locked_balance check
                        # If it fails due to promo code restrictions, we need to rollback Redis operation
                        await self.database.update_user_balance(user_id, -Decimal(str(bet_amount)), "game_bet", game_id=game_id)
                        
                        # Record bet history in PostgreSQL if enabled
                        from config.settings import DISABLE_POSTGRESQL_GAME_HISTORY
                        from database import AsyncSessionLocal
                        
                        if not DISABLE_POSTGRESQL_GAME_HISTORY:
                            async with AsyncSessionLocal() as session:
                                if self.migration_service:
                                    # Get game_id for current round
                                    game_id_str = await self.redis.cache_get("current_game_id")
                                    game_id = int(game_id_str) if game_id_str else None
                                    
                                    # NOTE: Больше НЕ создаем game_loss здесь!
                                    # game_loss создается только при реальном проигрыше
                                        
                    except Exception as e:
                        error_msg = str(e)
                        
                        # 🔒 CRITICAL: If promo code withdrawal restriction triggered, rollback Redis operation
                        if "promo_balance_locked|" in error_msg:
                            logger.warning(f"🔒 Promo code withdrawal restriction triggered for user {user_id}, rolling back Redis operation")
                            try:
                                # Rollback Redis balance change
                                await redis_client.eval(
                                    """
                                    local balance_key = KEYS[1]
                                    local players_key = KEYS[2]
                                    local user_id = ARGV[1]
                                    local bet_amount = tonumber(ARGV[2])
                                    
                                    -- Restore balance
                                    local current_balance = redis.call('HGET', balance_key, user_id)
                                    if current_balance then
                                        local restored_balance = tonumber(current_balance) + bet_amount
                                        redis.call('HSET', balance_key, user_id, tostring(restored_balance))
                                    end
                                    
                                    -- Remove player from game
                                    redis.call('HDEL', players_key, user_id)
                                    
                                    return 1
                                    """,
                                    2,  # number of KEYS
                                    self.redis.keys["USER_BALANCES"],
                                    self.redis.keys["GAME_PLAYERS"],
                                    str(user_id),
                                    str(bet_amount)
                                )
                                # Redis operation rolled back successfully
                                
                                # Return the promo code error to the user
                                return False
                                
                            except Exception as rollback_error:
                                logger.error(f"❌ CRITICAL: Failed to rollback Redis operation for user {user_id}: {rollback_error}")
                                # This is a critical state - Redis and PostgreSQL are now inconsistent
                                return False
                        else:
                            logger.warning(f"⚠️ PostgreSQL sync failed for user {user_id}: {e}")
                            # Don't fail the join for other errors - Redis operation was successful
                
                return True
                
            except Exception as lua_error:
                logger.error(f"❌ Atomic Lua script failed for user {user_id}: {lua_error}")
                return False
                
        except Exception as e:
            logger.error(f"Join game error for user {user_id}: {e}", exc_info=True)
            return False
    
    async def player_cashout(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Player cashes out with atomic race condition protection"""
        try:
            # 🔒 SECURITY: Atomic cashout operation to prevent race conditions
            redis_client = await self.redis.get_async_client()
            
            # 🔒 CRITICAL FIX: Correct Redis WATCH/MULTI order
            # Step 1: Watch keys BEFORE starting transaction
            await redis_client.watch(self.redis.keys["CRASH_GAME"], self.redis.keys["GAME_PLAYERS"])
            
            try:
                # Get current state atomically
                state = await self.redis.get_game_state()
                if not state or state["status"] != "playing":
                    await redis_client.unwatch()
                    return None
                
                player_data = await self.redis.get_player_data(user_id)
                if not player_data or player_data.get("cashed_out") or player_data.get("cashout_count", 0) > 0:
                    await redis_client.unwatch()
                    logger.warning(f"🚨 Cashout rejected for user {user_id}: already cashed out (count: {player_data.get('cashout_count', 0) if player_data else 0})")
                    return None
                
                # 🔒 ATOMIC: Calculate coefficient and check crash in single atomic moment
                crash_point = Decimal(str(state["crash_point"]))
                game_start_time = state["start_time"]
                
                # 🔒 CRITICAL: Single atomic time measurement to prevent race conditions
                if SECURE_TIME_AVAILABLE:
                    # Use secure time with manipulation detection
                    is_manipulated, manipulation_reason = detect_time_manipulation()
                    if is_manipulated:
                        await redis_client.unwatch()
                        logger.warning(f"🚨 Time manipulation detected during cashout: {manipulation_reason}")
                        return None
                    
                    raw_coef = calculate_secure_coefficient(
                        game_start_time, 
                        self.config["tick_ms"],
                        Decimal(str(self.config["growth_rate"])),
                        Decimal(str(self.config["max_coefficient"]))
                    )
                    
                    # 🔒 FIX: Ограничиваем коэффициент crash_point-ом для синхронности
                    coef = min(raw_coef, crash_point)
                    
                    # Atomic timing validation - SYNCHRONIZED with WebSocket display delay
                    min_delay_seconds = (self.config["tick_ms"] * 2) / 1000.0  # Same as display delay
                    is_timing_valid, timing_reason = validate_cashout_timing(game_start_time, min_delay_seconds)
                    if not is_timing_valid:
                        await redis_client.unwatch()
                        logger.warning(f"🚨 Secure cashout timing validation failed for user {user_id}: {timing_reason}")
                        return None
                        
                else:
                    # Fallback atomic calculation
                    now = time.time()
                    
                    # Atomic timing check - SYNCHRONIZED with WebSocket display delay
                    MIN_CASHOUT_DELAY = (self.config["tick_ms"] * 2) / 1000.0  # tick_ms * 2 converted to seconds
                    timing_ms = (now - game_start_time) * 1000
                    if timing_ms < MIN_CASHOUT_DELAY * 1000:
                        await redis_client.unwatch()
                        logger.warning(f"🚨 Cashout rejected for user {user_id}: too early ({timing_ms:.0f}ms < {MIN_CASHOUT_DELAY*1000:.0f}ms)")
                        
                        # 🔒 SECURITY: Log timing attack attempt
                        try:
                            from security_monitor import get_security_monitor
                            security_monitor = get_security_monitor(await self.redis.get_async_client())
                            await security_monitor.log_timing_attack(
                                user_id, 
                                timing_ms,
                                MIN_CASHOUT_DELAY * 1000,
                                "unknown_ip"  # TODO: Pass real IP from request
                            )
                        except Exception as e:
                            logger.error(f"Failed to log security event: {e}")
                        
                        return None
                    
                    # Atomic coefficient calculation at exact moment
                    elapsed_ms = (now - game_start_time) * 1000
                    ticks = elapsed_ms / self.config["tick_ms"]
                    
                    try:
                        growth_rate = Decimal(str(self.config["growth_rate"]))
                        raw_coef = (growth_rate ** Decimal(str(ticks))).quantize(Decimal('0.01'))
                        raw_coef = min(raw_coef, Decimal(str(self.config["max_coefficient"])))
                        
                        # 🔒 FIX: Ограничиваем коэффициент crash_point-ом, как в get_current_status()
                        # Это обеспечивает синхронность между отображением и кэшаутом
                        coef = min(raw_coef, crash_point)
                        
                    except (OverflowError, Exception):
                        coef = min(Decimal(str(self.config["max_coefficient"])), crash_point)
                
                # 🔒 ATOMIC: Check crash immediately after calculation - NO RACE CONDITION
                if coef >= crash_point:
                    await redis_client.unwatch()
                    logger.warning(f"🚨 Cashout rejected for user {user_id}: coef {coef} >= crash_point [HIDDEN] (ATOMIC CHECK)")
                    
                    # 🔒 SECURITY: Log cashout after crash attempt
                    try:
                        from security_monitor import get_security_monitor
                        security_monitor = get_security_monitor(await self.redis.get_async_client())
                        await security_monitor.log_cashout_after_crash(
                            user_id, 
                            coef,
                            crash_point,
                            "unknown_ip"  # TODO: Pass real IP from request
                        )
                    except Exception as e:
                        logger.error(f"Failed to log security event: {e}")
                    
                    return None
                
                # Step 2: Prepare transaction after validation
                # 🔒 CRITICAL FIX: Start transaction AFTER watch and validation
                pipe = redis_client.pipeline()
                pipe.multi()
                
                # Atomic update player data
                player_data["cashed_out"] = True
                player_data["cashout_coef"] = coef
                player_data["cashout_count"] = player_data.get("cashout_count", 0) + 1  # 🔒 Increment counter
                # 🔒 SECURITY: Use secure timestamp
                cashout_timestamp = get_secure_time() if SECURE_TIME_AVAILABLE else time.time()
                player_data["cashout_timestamp"] = cashout_timestamp
                
                # 🔒 CRITICAL: Update player data in hash table with atomic operation
                pipe.hset(self.redis.keys["GAME_PLAYERS"], str(user_id), json.dumps(player_data, default=str))
                result = await pipe.execute()
                
                if not result:
                    # Transaction failed due to concurrent modification
                    logger.warning(f"🚨 Cashout transaction failed for user {user_id} - concurrent modification detected")
                    return None
                
                # 🔒 DOUBLE-CHECK: Verify we are the ones who set cashed_out=True
                final_player_data = await self.redis.get_player_data(user_id)
                if not final_player_data or not final_player_data.get("cashed_out"):
                    logger.error(f"🚨 CRITICAL: Cashout verification failed for user {user_id} - state inconsistent!")
                    return None
                    
                # Calculate delay for logging
                current_time = get_secure_time() if SECURE_TIME_AVAILABLE else time.time()
                delay_ms = (current_time - game_start_time) * 1000
                
            except Exception as tx_error:
                await redis_client.unwatch()
                logger.error(f"❌ Cashout transaction error for user {user_id}: {tx_error}")
                return None
            
            # Calculate and add winnings using Decimal for precision
            bet_amount = Decimal(str(player_data["bet_amount"]))
            coefficient = Decimal(str(coef))
            total_payout = (bet_amount * coefficient).quantize(Decimal('0.01'))  # Total amount received
            win_amount = (total_payout - bet_amount).quantize(Decimal('0.01'))  # Net profit only
            
            # Update balance and record statistics using MigrationService (как в main.py)
            try:
                # Import config instead of duplicating
                from config.settings import DISABLE_POSTGRESQL_GAME_HISTORY
                
                from database import AsyncSessionLocal
                async with AsyncSessionLocal() as session:
                    # Use migration service from instance (properly injected)
                    if self.migration_service:
                        # 🔒 SECURITY FIX: Use record_player_transaction which handles balance update internally to prevent double crediting
                        # Record game using NEW schema
                        if not DISABLE_POSTGRESQL_GAME_HISTORY:
                            try:
                                # ✅ Получаем game_id текущего раунда
                                game_id_str = await self.redis.cache_get("current_game_id")
                                game_id = int(game_id_str) if game_id_str else None
                                
                                if game_id:
                                    # 🔒 FIXED: Single transaction approach to prevent double statistics
                                    # Get user to update balance manually
                                    user = await DatabaseService.get_user_by_telegram_id(session, user_id)
                                    if not user:
                                        raise ValueError(f"User {user_id} not found")
                                    
                                    # 1. Update user balance directly (no transaction created yet)
                                    user.balance = Decimal(str(user.balance)) + Decimal(str(total_payout))
                                    
                                    # 2. Record single transaction with total_payout for correct statistics
                                    await DatabaseService.record_player_win(
                                        session, user.id, game_id, Decimal(str(total_payout)), 
                                        Decimal(str(coef)), user.balance  # pass updated balance
                                    )
                                    await session.commit()  # Commit both balance and transaction
                                    
                                    # 3. Sync with Redis
                                    if self.database.redis_service:
                                        await self.database.redis_service.set_user_balance(user_id, str(user.balance))
                                    
                                else:
                                    logger.warning(f"💰⚠️ No game_id found for player {user_id} cashout")
                                    # Fallback: Direct balance update without transaction
                                    user = await DatabaseService.get_user_by_telegram_id(session, user_id)
                                    if user:
                                        user.balance = Decimal(str(user.balance)) + Decimal(str(total_payout))
                                        await session.commit()
                                        if self.database.redis_service:
                                            await self.database.redis_service.set_user_balance(user_id, str(user.balance))
                                    # Fallback payout credited
                            except Exception as e:
                                logger.error(f"⚠️ Failed to record game in PostgreSQL: {e}")
                                if "no partition of relation" in str(e):
                                    logger.error("💡 Hint: PostgreSQL table 'game_history' needs partition for current date")
                                # Emergency fallback: Direct balance update without transaction
                                try:
                                    user = await DatabaseService.get_user_by_telegram_id(session, user_id)
                                    if user:
                                        user.balance = Decimal(str(user.balance)) + Decimal(str(total_payout))
                                        await session.commit()
                                        if self.database.redis_service:
                                            await self.database.redis_service.set_user_balance(user_id, str(user.balance))
                                        # Emergency fallback payout credited
                                except Exception as fallback_error:
                                    logger.error(f"❌ Emergency fallback failed: {fallback_error}")
                                    # Last resort: Redis only update
                                    if self.database.redis_service:
                                        current_balance = await self.database.redis_service.get_user_balance(user_id)
                                        new_balance = Decimal(str(current_balance)) + Decimal(str(total_payout))
                                        await self.database.redis_service.set_user_balance(user_id, str(new_balance))
                                        # Redis-only fallback completed
                        else:
                            logger.warning(f"=💰 Player {user_id} cashed out at {coef}x, profit {win_amount} - PostgreSQL recording DISABLED")
                            # When PostgreSQL is disabled: Direct balance update + Redis sync
                            user = await DatabaseService.get_user_by_telegram_id(session, user_id)
                            if user:
                                user.balance = Decimal(str(user.balance)) + Decimal(str(total_payout))
                                await session.commit()
                                if self.database.redis_service:
                                    await self.database.redis_service.set_user_balance(user_id, str(user.balance))
                            # PostgreSQL disabled: payout credited
                        
                        # 🔒 FIXED: Single transaction approach prevents double statistics
                        # Balance is updated manually + single Transaction record with win_amount
                        # This prevents PostgreSQL trigger from adding both total_payout AND win_amount to total_won
                        logger.debug(f"💰 Balance update completed for user {user_id}")
                    else:
                        logger.error(f"❌ CRITICAL: migration_service is None - WIN NOT RECORDED for user {user_id}!")
                        logger.error(f"🔍 This means dependency injection failed in main.py")
                        # Still allow cashout but without recording to DB
            except Exception as e:
                logger.error(f"❌ Error recording cashout for player {user_id}: {e}")
                logger.warning(f"=💰 Player {user_id} cashed out at {coef}x (stats not recorded)")
            
            return {
                "coefficient": coef,
                "bet_amount": bet_amount,
                "win_amount": win_amount
            }
            
        except Exception as e:
            logger.error(f"Cashout error for user {user_id}: {e}", exc_info=True)
            return None
    
    # Status methods
    async def get_current_status(self) -> Dict[str, Any]:
        """Get current game status - ported from /current-state endpoint"""
        try:
            state = await self.redis.get_game_state()
            if not state:
                await self._start_waiting_period()
                state = await self.redis.get_game_state()
            
            now = time.time()
            elapsed_ms = (now - state["start_time"]) * 1000
            
            # Check crash flag
            game_just_crashed = await self.redis.cache_get("game_just_crashed") or False
            
            # 🔒 FIX: Don't immediately transition from crashed to waiting in get_current_status
            # This was causing rapid state changes and visual glitches when called from WebSocket broadcast
            # The transition should only happen in the main game loop after _handle_crash completes
            # if state["status"] == "crashed":
            #     await self._start_waiting_period()
            #     state = await self.redis.get_game_state()
            
            if state["status"] == "waiting":
                last_crash_coef = await self.redis.cache_get("last_crash_coefficient") or Decimal('1.0')
                
                waiting_time_ms = self.config["waiting_time"] * 1000
                countdown_ms = max(0, waiting_time_ms - elapsed_ms)
                countdown_seconds = max(0, int(countdown_ms / 1000))
                
                return {
                    "coefficient": "1.0",
                    "crashed": False,
                    "crash_point": "0.0",
                    "last_crash_coefficient": str(last_crash_coef),
                    "status": "waiting",
                    "time_since_start": elapsed_ms,
                    "countdown_seconds": countdown_seconds,
                    "game_just_crashed": bool(game_just_crashed)
                }
            
            # Playing status
            ticks = elapsed_ms / self.config["tick_ms"]
            max_coef = Decimal(str(self.config["max_coefficient"]))
            
            try:
                growth_rate = Decimal(str(self.config["growth_rate"]))
                coef = (growth_rate ** Decimal(str(ticks))).quantize(Decimal('0.01'))
                if coef > max_coef:
                    coef = max_coef
            except (OverflowError, Exception):
                coef = max_coef
            
            crashed = coef >= Decimal(str(state["crash_point"]))
            last_crash_coef = await self.redis.cache_get("last_crash_coefficient") or Decimal('1.0')
            
            # 🔒 SECURITY: Only send crash_point after game ends, never during playing
            crash_point_safe = None
            if crashed:  # Only after crash, not during playing
                crash_point_safe = state["crash_point"]
            
            result = {
                "coefficient": str(coef) if not crashed else str(min(coef, Decimal(str(state["crash_point"])))),
                "crashed": crashed,
                "crash_point": crash_point_safe,  # 🔒 SECURITY: null during playing
                "last_crash_coefficient": str(last_crash_coef),
                "status": "playing" if not crashed else "crashed",
                "time_since_start": elapsed_ms,
                "game_just_crashed": bool(game_just_crashed)
            }
            
            if crashed:
                result["countdown_seconds"] = 1
            
            return result
            
        except Exception as e:
            logger.error(f"Get status error: {e}", exc_info=True)
            return {
                "coefficient": "1.0",
                "crashed": False,
                "crash_point": "0.0",
                "last_crash_coefficient": "1.0",
                "status": "waiting",
                "time_since_start": 0,
                "countdown_seconds": 10,
                "game_just_crashed": False
            }
    
    def get_config(self) -> Dict[str, Any]:
        """Get game configuration"""
        return self.config.copy()
    
    def get_last_player_limit_error(self) -> Optional[int]:
        """Return the player limit if last join failure was due to player limit"""
        return self.last_player_limit_error
    
    async def get_engine_stats(self) -> Dict[str, Any]:
        """Get engine statistics"""
        redis_stats = await self.redis.get_stats()
        return {
            "running": self.running,
            "config": self.config,
            "redis_stats": redis_stats
        }