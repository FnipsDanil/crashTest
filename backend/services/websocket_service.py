"""
WebSocket Service for real-time game updates
Replaces high-frequency polling with efficient WebSocket connections
"""

import asyncio
import json
import logging
import time
import secrets
import hashlib
import struct
import base64
from decimal import Decimal
from typing import Dict, Set, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
from services.auth_service import AuthService

# 🔒 SECURITY: Import secure time management
try:
    from security.time_security import get_secure_time
    SECURE_TIME_AVAILABLE = True
except ImportError:
    SECURE_TIME_AVAILABLE = False
    def get_secure_time():
        return time.time()

logger = logging.getLogger(__name__)

def _apply_simple_timing_protection(coefficient: str, status: str = "playing", tick_ms: int = 150) -> tuple[str, float]:
    """
    🔒 SIMPLE TIMING PROTECTION: Fixed delay synchronized with cashout
    Returns: (protected_coefficient, delay_seconds)
    """
    try:
        coef = Decimal(str(coefficient))
        
        # 🔒 CRITICAL: Ensure coefficient is never below 1.0 for crash game logic
        coef = max(coef, Decimal('1.0'))
        
        # Simple fixed delay = tick_ms * 2 (same as cashout delay)
        delay_ms = tick_ms * 2 if status == "playing" else 0
        
        # Format coefficient
        protected_coef_str = str(coef.quantize(Decimal('0.01')))
        delay_seconds = delay_ms / 1000.0
        
        return protected_coef_str, delay_seconds
        
    except (ValueError, TypeError) as e:
        logger.warning(f"⚠️ Simple timing protection error: {e}")
        return coefficient, 0.0

class WebSocketManager:
    """Manages WebSocket connections and broadcasts"""
    
    def __init__(self, game_engine=None, auth_service=None):
        # Active connections by user_id
        self.active_connections: Dict[int, WebSocket] = {}
        # Connection metadata
        self.connection_info: Dict[int, Dict[str, Any]] = {}
        # Background task
        self._broadcast_task: Optional[asyncio.Task] = None
        self._running = False
        # Game engine reference for real-time data
        self.game_engine = game_engine
        # Auth service for validation
        self.auth_service = auth_service or AuthService()
        
        # PERFORMANCE: State change detection to avoid unnecessary broadcasts
        self.last_broadcast_state: Optional[Dict[str, Any]] = None
        self.last_crash_history: Optional[list] = None
        
        # 🔒 SECURITY: User behavior tracking for adaptive timing protection
        self.user_behavior_scores: Dict[int, float] = {}  # user_id -> suspicion_score (0.0-1.0)
        self.user_request_history: Dict[int, list] = {}   # user_id -> [timestamp, ...]
        self.user_update_offsets: Dict[int, float] = {}   # user_id -> personal_delay_offset
        
        # 🔒 CRITICAL: Track delayed tasks to cancel them during state transitions
        self.pending_delayed_tasks: list = []
        
    async def connect(self, websocket: WebSocket, user_id: int, init_data: str = ""):
        """Accept WebSocket connection and authenticate user"""
        await websocket.accept()
        
        # 🔒 SECURITY: Validate user authentication - ALWAYS REQUIRED
        if not init_data:
            await websocket.close(code=4001, reason="Authentication required")
            return False
            
        # 🔒 CRITICAL: Remove development bypass - always validate auth
        is_valid, parsed_data = self.auth_service.validate_telegram_init_data(init_data)
        if not is_valid:
            await websocket.close(code=4001, reason="Invalid authentication")
            return False
        
        # 🔒 SECURITY: Validate user_id matches token
        user_data = parsed_data.get("user", {})
        if not user_data or user_data.get("id") != user_id:
            logger.warning(f"🚨 WebSocket user ID mismatch: URL={user_id}, token={user_data.get('id') if user_data else 'None'}")
            await websocket.close(code=4002, reason="User ID mismatch")
            return False
        
        # Store connection
        self.active_connections[user_id] = websocket
        self.connection_info[user_id] = {
            "connected_at": get_secure_time(),  # 🔒 Use secure time for connection tracking
            "last_ping": get_secure_time(),
            "subscriptions": set()
        }
        
        # 🔒 SECURITY: Initialize user behavior tracking
        self.user_behavior_scores[user_id] = 0.0
        self.user_request_history[user_id] = []
        self.user_update_offsets[user_id] = secrets.randbelow(50) / 1000.0  # 0-50ms personal offset
        
        
        # Start broadcast task if not running
        if not self._running:
            await self.start_broadcast_task()
        else:
            pass
        
        return True
    
    async def disconnect(self, user_id: int, reason: str = "Client disconnect"):
        """Remove user connection"""
        if user_id in self.active_connections:
            try:
                websocket = self.active_connections[user_id]
                await websocket.close()
            except Exception as e:
                # Ignore normal close errors when user closes app
                if "Unexpected ASGI message" not in str(e) and "close message has been sent" not in str(e):
                    logger.warning(f"Error closing WebSocket for user {user_id}: {e}")
            
            self.active_connections.pop(user_id, None)  # 🔒 RACE CONDITION FIX: Safe removal
            
        # Also remove from connection_info if exists (safe removal)
        self.connection_info.pop(user_id, None)
            
        # 🔒 SECURITY: Clean up behavior tracking data
        self.user_behavior_scores.pop(user_id, None)
        self.user_request_history.pop(user_id, None)
        self.user_update_offsets.pop(user_id, None)
            
        
        # Stop broadcast task if no connections
        if not self.active_connections and self._running:
            await self.stop_broadcast_task()
    
    async def subscribe(self, user_id: int, event_type: str):
        """Subscribe user to specific event type"""
        if user_id in self.connection_info:
            # Check if already subscribed to avoid duplicate logging
            if event_type not in self.connection_info[user_id]["subscriptions"]:
                self.connection_info[user_id]["subscriptions"].add(event_type)
                
                # 🚀 INSTANT DATA: Send immediate data for new subscribers
                if event_type == "crash_history":
                    await self._send_crash_history_to_user(user_id)
                elif event_type == "balance_update":
                    await self._send_balance_to_user(user_id)
            else:
                pass
        else:
            pass
    
    async def unsubscribe(self, user_id: int, event_type: str):
        """Unsubscribe user from event type"""
        if user_id in self.connection_info:
            self.connection_info[user_id]["subscriptions"].discard(event_type)
            logger.debug(f"📡 User {user_id} unsubscribed from {event_type}")
    
    def _update_user_behavior_score(self, user_id: int, request_type: str = "message"):
        """🔒 SECURITY: Update user behavior suspicion score based on activity patterns"""
        try:
            current_time = get_secure_time()
            
            # Initialize if not exists
            if user_id not in self.user_request_history:
                self.user_request_history[user_id] = []
                self.user_behavior_scores[user_id] = 0.0
            
            # Add current request
            self.user_request_history[user_id].append(current_time)
            
            # Keep only last 100 requests (sliding window)
            self.user_request_history[user_id] = self.user_request_history[user_id][-100:]
            
            # Analyze patterns in last 10 seconds
            recent_requests = [
                t for t in self.user_request_history[user_id] 
                if current_time - t <= 10.0
            ]
            
            suspicion_factors = []
            
            # Factor 1: Request frequency (more than 200 requests/10s is suspicious - normal game sends ~67/10s)
            if len(recent_requests) > 200:
                frequency_score = min(1.0, (len(recent_requests) - 200) / 200.0)
                suspicion_factors.append(("high_frequency", frequency_score))
            
            # Factor 2: Regularity pattern (too regular timing is bot-like)
            if len(recent_requests) >= 5:
                intervals = [
                    recent_requests[i] - recent_requests[i-1] 
                    for i in range(1, len(recent_requests))
                ]
                if intervals:
                    avg_interval = sum(intervals) / len(intervals)
                    variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
                    # Low variance = regular pattern = suspicious
                    if variance < 0.001:  # Very regular
                        regularity_score = 0.8
                        suspicion_factors.append(("regular_pattern", regularity_score))
                    elif variance < 0.01:  # Somewhat regular
                        regularity_score = 0.4
                        suspicion_factors.append(("regular_pattern", regularity_score))
            
            # Factor 3: Burst detection (many requests in very short time)
            recent_1s = [
                t for t in self.user_request_history[user_id] 
                if current_time - t <= 1.0
            ]
            if len(recent_1s) > 10:
                burst_score = min(1.0, (len(recent_1s) - 10) / 20.0)
                suspicion_factors.append(("burst_activity", burst_score))
            
            # Calculate weighted suspicion score
            if suspicion_factors:
                total_weight = sum(score for _, score in suspicion_factors)
                weighted_score = total_weight / len(suspicion_factors)
                
                # Exponential decay: new_score = 0.7 * old_score + 0.3 * current_score
                old_score = self.user_behavior_scores.get(user_id, 0.0)
                self.user_behavior_scores[user_id] = 0.7 * old_score + 0.3 * weighted_score
                
                # Log high suspicion users
                if self.user_behavior_scores[user_id] > 0.5:
                    factors_str = ", ".join(f"{name}:{score:.2f}" for name, score in suspicion_factors)
                    logger.warning(f"🚨 Suspicious user activity: user_id={user_id}, score={self.user_behavior_scores[user_id]:.2f}, factors=[{factors_str}]")
            else:
                # Gradual decay if no suspicious activity
                self.user_behavior_scores[user_id] *= 0.95
                
        except Exception as e:
            logger.error(f"❌ Error updating behavior score for user {user_id}: {e}")
    
    async def _send_delayed_message(self, user_id: int, game_data: Dict[str, Any], delay_seconds: float):
        """🔒 SECURITY: Send message with timing protection delay"""
        current_task = asyncio.current_task()
        try:
            # Apply the timing protection delay
            await asyncio.sleep(delay_seconds)
            
            # Check if user is still connected
            if user_id in self.active_connections:
                message = {
                    "type": "game_state",
                    "timestamp": time.time(),
                    "data": game_data
                }
                
                await self.send_to_user(user_id, message)
                
        except asyncio.CancelledError:
            # Task was cancelled - this is expected during crash events
            logger.debug(f"🔒 Delayed message task cancelled for user {user_id} (crash event)")
            raise
        except Exception as e:
            logger.error(f"❌ Error in delayed message send to user {user_id}: {e}")
        finally:
            # 🔒 CLEANUP: Remove this task from pending list when done
            if current_task and current_task in self.pending_delayed_tasks:
                self.pending_delayed_tasks.remove(current_task)
    
    def _encode_binary_game_state(self, data: Dict[str, Any]) -> str:
        """🚀 УЛЬТРА-КРИТИЧНО: Бинарное сжатие game_state - самое частое сообщение (150ms = 6.67/сек)"""
        try:
            # Преобразуем coefficient в int (умножаем на 100 для 2 знаков)
            coef_raw = float(data.get("coefficient", "1.0"))
            coef_int = min(int(coef_raw * 100), 65535)  # Max uint16
            
            # Status как 1 байт: 0=waiting, 1=playing, 2=crashed
            status_map = {"waiting": 0, "playing": 1, "crashed": 2}
            status_byte = status_map.get(data.get("status", "waiting"), 0)
            
            # Countdown как uint8 (max 255)
            countdown = min(int(data.get("countdown", 0)), 255)
            
            # Flags в 1 байте: bit0=crashed, bit1=game_just_crashed, bit2=has_countdown
            flags = 0
            if data.get("crashed", False):
                flags |= 1  # bit 0
            if data.get("game_just_crashed", False):
                flags |= 2  # bit 1
            if countdown > 0:
                flags |= 4  # bit 2 - has countdown
            
            # Last crash coefficient тоже в int
            last_coef_raw = float(data.get("last_crash_coefficient", "1.0"))
            last_coef_int = min(int(last_coef_raw * 100), 65535)
            
            # Упаковываем в бинарный формат: 7-8 байт
            # Format: B=uint8, H=uint16
            binary_data = struct.pack('!BBBHH', 
                1,  # Тип сообщения: 1 = game_state (1 байт)
                status_byte,  # Status (1 байт)
                flags,  # Flags (1 байт)  
                coef_int,  # Coefficient * 100 (2 байта)
                last_coef_int  # Last coefficient * 100 (2 байта)
            )
            # countdown добавляем только если есть (для экономии байтов)
            if countdown > 0:
                binary_data += struct.pack('!B', countdown)
            
            # Кодируем в base64 для передачи по WebSocket
            return base64.b64encode(binary_data).decode('ascii')
            
        except Exception as e:
            logger.error(f"❌ Binary encoding failed: {e}")
            # Fallback к JSON
            return None

    def _encode_binary_crash_history(self, history: list) -> str:
        """🚀 КРИТИЧНО: Бинарное сжатие crash_history - экономия ~60% трафика"""
        try:
            if not history:
                return None
                
            # Преобразуем все коэффициенты в uint16 (умножаем на 100)
            binary_data = struct.pack('!B', 2)  # Тип сообщения: 2 = crash_history
            
            for coeff_str in history:
                coeff_float = float(str(coeff_str))
                coeff_int = min(int(coeff_float * 100), 65535)  # Max uint16
                binary_data += struct.pack('!H', coeff_int)  # 2 байта на коэффициент
            
            # Результат: 20 коэффициентов = 1 + 20*2 = 41 байт вместо ~200 байт JSON
            return base64.b64encode(binary_data).decode('ascii')
            
        except Exception as e:
            logger.error(f"❌ Binary crash history encoding failed: {e}")
            return None

    def _compress_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """🚀 КРИТИЧНО: Максимальное сжатие сообщений для экономии трафика (100 Мбит канал!)"""
        msg_type = message.get("type")
        
        if msg_type == "game_state" and "data" in message:
            data = message["data"]
            
            # 🚀 УЛЬТРА-КРИТИЧНО: Пробуем бинарное сжатие для game_state
            binary_encoded = self._encode_binary_game_state(data)
            if binary_encoded:
                return {
                    "b": binary_encoded  # Всего 8-12 байт вместо 200+!
                }
            
            # Fallback к обычному JSON сжатию
            compressed = {
                "t": "gs",  # type: game_state -> gs (экономия 8 байт)
                "ts": int(message["timestamp"]),  # timestamp как int (экономия 4-8 байт)
                "d": {
                    "c": data.get("coefficient", "1.0"),  # coefficient -> c
                    "s": data.get("status", "waiting")[:1],  # status -> s, только первая буква (w/p/c)
                    "cd": data.get("countdown", 0),  # countdown -> cd
                    "cr": 1 if data.get("crashed", False) else 0,  # crashed -> cr (boolean -> int)
                    "cp": data.get("crash_point"),  # crash_point -> cp
                    "lc": data.get("last_crash_coefficient", "1.0"),  # last_crash_coefficient -> lc
                    "jc": 1 if data.get("game_just_crashed", False) else 0  # game_just_crashed -> jc
                }
            }
            # Удаляем только пустые строки, но сохраняем null для критических полей
            compressed["d"] = {k: v for k, v in compressed["d"].items() if v is not None or k == "cp"}
            return compressed
            
        elif msg_type == "player_status" and "data" in message:
            # Сжимаем player_status
            data = message["data"]
            compressed = {
                "t": "ps",  # player_status -> ps
                "ts": int(message["timestamp"]),
                "d": {
                    "ig": 1 if data.get("in_game", False) else 0,  # in_game -> ig
                    "co": 1 if data.get("cashed_out", False) else 0,  # cashed_out -> co  
                    "sw": 1 if data.get("show_win_message", False) else 0,  # show_win_message -> sw
                    "sc": 1 if data.get("show_crash_message", False) else 0,  # show_crash_message -> sc
                    "wa": data.get("win_amount", "0"),  # win_amount -> wa
                    "wm": data.get("win_multiplier", "0")  # win_multiplier -> wm
                }
            }
            # Удаляем нулевые значения и null
            compressed["d"] = {k: v for k, v in compressed["d"].items() if v and v != "0" and v != 0}
            return compressed
            
        elif msg_type == "balance_update" and "data" in message:
            # Сжимаем balance_update
            data = message["data"]
            return {
                "t": "bu",  # balance_update -> bu
                "ts": int(message["timestamp"]),
                "d": {
                    "u": data.get("user_id", 0),  # КРИТИЧНО: user_id -> u
                    "b": data.get("balance", "0"),  # balance -> b
                    "r": data.get("reason", "")[:2]  # reason -> r, только 2 символа
                }
            }
            
        elif msg_type == "crash_history" and "data" in message:
            # 🚀 УЛЬТРА-КРИТИЧНО: Бинарное сжатие crash_history - массив float
            data = message["data"]
            history = data.get("history", [])
            
            # Если история большая - используем бинарное сжатие
            if len(history) > 10:
                try:
                    binary_history = self._encode_binary_crash_history(history)
                    if binary_history:
                        return {
                            "t": "chb",  # crash_history_binary
                            "ts": int(message["timestamp"]),
                            "d": binary_history
                        }
                except Exception as e:
                    logger.error(f"Binary crash history encoding failed: {e}")
            
            # Fallback к обычному сжатию
            return {
                "t": "ch",  # crash_history -> ch
                "ts": int(message["timestamp"]),
                "d": history  # убираем обертку "history"
            }
            
        # Для других сообщений минимальное сжатие
        return {
            "t": msg_type[:2] if len(msg_type) > 2 else msg_type,
            "ts": int(message.get("timestamp", time.time())),
            "d": message.get("data", {})
        }

    async def send_to_user(self, user_id: int, message: Dict[str, Any]):
        """Send message to specific user with compression"""
        if user_id in self.active_connections:
            try:
                websocket = self.active_connections[user_id]
                
                # 🚀 КРИТИЧНО: Сжимаем сообщение для экономии трафика
                compressed_message = self._compress_message(message)
                
                await websocket.send_text(json.dumps(compressed_message))
                
                # Update ping time
                self.connection_info[user_id]["last_ping"] = get_secure_time()  # 🔒 Secure ping timing
                
                # 🔒 SECURITY: Update user behavior tracking
                self._update_user_behavior_score(user_id, "websocket_message")
                
                return True
            except Exception as e:
                # Ignore normal disconnect errors when user closes app
                error_str = str(e).lower()
                error_type = type(e).__name__.lower()
                
                ignore_errors = [
                    "close message has been sent",
                    "1001",
                    "connection closed",
                    "websocket connection is closed", 
                    "broken pipe",
                    "connection reset",
                    "connectionclosed",
                    "websocketdisconnect",
                    "client disconnected"
                ]
                
                ignore_types = [
                    "connectionclosederror",
                    "websocketdisconnect", 
                    "connectionresetserror"
                ]
                
                # Check both error message and error type
                should_ignore = (
                    any(ignore_error in error_str for ignore_error in ignore_errors) or
                    any(ignore_type in error_type for ignore_type in ignore_types)
                )
                
                if not should_ignore:
                    logger.error(f"❌ Failed to send message to user {user_id}: {e}")
                await self.disconnect(user_id, f"Send failed: {e}")
                return False
        return False
    
    async def broadcast_to_subscribed(self, event_type: str, data: Dict[str, Any]):
        """Broadcast message to all users subscribed to event type"""
        if not self.active_connections:
            return 0
        
        message = {
            "type": event_type,
            "timestamp": time.time(),
            "data": data
        }
        
        sent_count = 0
        failed_users = []
        subscribers_debug = []
        
        for user_id, info in self.connection_info.items():
            subscribers_debug.append(f"user_{user_id}:{list(info['subscriptions'])}")
            if event_type in info["subscriptions"]:
                success = await self.send_to_user(user_id, message)
                if success:
                    sent_count += 1
                else:
                    failed_users.append(user_id)
        
        # No logging for missing subscribers - subscriptions can arrive with delay
        
        # Clean up failed connections
        for user_id in failed_users:
            await self.disconnect(user_id, "Broadcast failed")
        
        if sent_count > 0:
            logger.debug(f"📡 Broadcasted {event_type} to {sent_count} users")
        
        return sent_count
    
    async def broadcast_to_all(self, message: Dict[str, Any]):
        """Broadcast message to all connected users"""
        if not self.active_connections:
            return 0
        
        sent_count = 0
        failed_users = []
        
        for user_id in list(self.active_connections.keys()):
            success = await self.send_to_user(user_id, message)
            if success:
                sent_count += 1
            else:
                failed_users.append(user_id)
        
        # Clean up failed connections
        for user_id in failed_users:
            await self.disconnect(user_id, "Broadcast failed")
        
        if sent_count > 0:
            logger.debug(f"📡 Broadcasted message to {sent_count} users")
        
        return sent_count
    
    async def ping_connections(self):
        """Send ping to detect stale connections"""
        if not self.active_connections:
            return
        
        ping_message = {"type": "ping", "timestamp": time.time()}
        stale_users = []
        current_time = time.time()
        
        for user_id, info in self.connection_info.items():
            # Check for stale connections (no activity for 60 seconds)
            if current_time - info["last_ping"] > 60:
                stale_users.append(user_id)
            else:
                await self.send_to_user(user_id, ping_message)
        
        # Remove stale connections
        for user_id in stale_users:
            await self.disconnect(user_id, "Stale connection")
    
    async def start_broadcast_task(self):
        """Start background task for periodic updates"""
        if self._running:
            return
        
        self._running = True
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
    
    async def stop_broadcast_task(self):
        """Stop background task"""
        self._running = False
        if self._broadcast_task and not self._broadcast_task.done():
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
    
    async def _broadcast_loop(self):
        """Main broadcast loop - sends periodic updates"""
        try:
            iteration_count = 0
            while self._running and self.active_connections:
                try:
                    iteration_count += 1
                    # Removed broadcast loop iteration logging for production
                    
                    # 🔒 SECURITY: Synchronized timing with game engine tick_ms for consistency
                    await self._broadcast_game_state()
                    
                    # 🔒 ANTI-TIMING ATTACK: Use config tick_ms but maintain sync for cashout
                    # Protection is applied in coefficient values and delays, not in timing
                    if self.game_engine and hasattr(self.game_engine, 'config'):
                        tick_ms = self.game_engine.config.get("tick_ms", 150)  # From config
                        broadcast_interval = tick_ms / 1000.0  # Convert to seconds, exact timing
                        await asyncio.sleep(broadcast_interval)
                        
                        # Track broadcast count for less frequent operations
                        self.broadcast_count = getattr(self, 'broadcast_count', 0) + 1
                        
                        # Send player status updates every ~500ms (8-9 ticks at 60ms)
                        if self.broadcast_count % 8 == 0:  # Every 8 ticks = ~480ms
                            await self._broadcast_player_status()
                        
                        # Send crash history updates every ~2s (33 ticks at 60ms)
                        if self.broadcast_count % 33 == 0:  # Every 33 ticks = ~1980ms
                            await self._broadcast_crash_history()
                        
                        # Send balance updates every ~5s (adaptive to tick_ms)
                        balance_interval_ticks = max(1, int(5000 / tick_ms))  # 5 seconds in ticks
                        if self.broadcast_count % balance_interval_ticks == 0:
                            await self._broadcast_all_user_balances()
                            
                    else:
                        # Fallback timing if game engine not available
                        await asyncio.sleep(0.06)  # 60ms fallback
                    
                    # Ping connections every 30s
                    if int(time.time()) % 30 == 0 and int(time.time() * 1000) % 1000 < 150:
                        await self.ping_connections()
                
                except Exception as e:
                    logger.error(f"❌ Error in broadcast loop: {e}")
                    await asyncio.sleep(1)  # Prevent rapid error loops
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"❌ Fatal error in broadcast loop: {e}")
        finally:
            self._running = False
    
    async def _broadcast_game_state(self):
        """Broadcast current game state (replaces /current-state) - OPTIMIZED with state change detection"""
        try:
            if not self.game_engine:
                logger.warning("❌ No game_engine available for broadcast")
                return
            
            # Get game state directly from GameEngine
            current_state = await self.game_engine.get_current_status()
            if not current_state:
                logger.warning("❌ No current_state from game_engine")
                return
            
            # Convert Decimal values to str for JSON serialization (NO float for money!)
            # 🔒 SECURITY FIX: Remove crash_point and time_since_start to prevent timing attacks
            status = current_state.get("status", "waiting")
            raw_coef_value = max(Decimal(str(current_state.get("coefficient", "1.0"))), Decimal('1.0'))
            raw_coefficient = str(raw_coef_value)
            
            # 🔒 ANTI-TIMING ATTACK: Apply advanced multi-layered protection per user
            tick_ms = self.game_engine.config.get("tick_ms", 150) if self.game_engine else 150
            
            # 🔒 SECURITY: Only show crash_point AFTER crash, never during game
            crash_point_safe = None
            if status != "playing":  # After crash or during waiting - safe to show
                crash_point_safe = str(current_state.get("crash_point", "0.0"))
            
            # Base game data (without coefficient protection yet)
            base_game_data = {
                "status": status,
                "countdown": int(current_state.get("countdown_seconds", 0)),
                "crashed": current_state.get("crashed", False),
                "crash_point": crash_point_safe,  # 🔒 Only show after crash for graph display
                "last_crash_coefficient": str(current_state.get("last_crash_coefficient", "1.0")),
                "game_just_crashed": current_state.get("game_just_crashed", False)
            }
            
            # PERFORMANCE: Check if important fields changed (excluding coefficient)
            if self.last_broadcast_state and base_game_data.get("status") != "playing":
                important_fields = ["status", "countdown", "crashed", "game_just_crashed", "crash_point"]
                state_changed = any(
                    base_game_data.get(field) != self.last_broadcast_state.get(field) 
                    for field in important_fields
                )
                if not state_changed:
                    return  # Skip broadcast if nothing important changed
            
            # 🔒 SECURITY: Apply coefficient protection but keep smooth broadcasting
            # We'll use delayed tasks for timing protection without blocking main loop
            
            sent_count = 0
            failed_users = []
            protection_tasks = []
            
            for user_id, info in self.connection_info.items():
                if "game_state" in info["subscriptions"]:
                    try:
                        # Get user's behavior score
                        behavior_score = self.user_behavior_scores.get(user_id, 0.0)
                        
                        # 🔒 SECURITY: Apply simple timing protection during gameplay
                        if status == "playing" and not base_game_data.get("crashed", False):
                            # Apply simple fixed delay during gameplay (synchronized with cashout)
                            protected_coef, user_delay = _apply_simple_timing_protection(
                                raw_coefficient, status, tick_ms
                            )
                            
                            # Create personalized game data
                            user_game_data = base_game_data.copy()
                            user_game_data["coefficient"] = protected_coef
                            
                            # Apply simple fixed delay
                            total_delay = user_delay  # Simple synchronized delay
                        else:
                            # 🔒 CRITICAL: No delays for state changes (crashed, waiting) to prevent UI glitches
                            # This is safe because cashout is impossible during these states
                            user_game_data = base_game_data.copy()
                            user_game_data["coefficient"] = raw_coefficient  # Use original coefficient
                            total_delay = 0  # Immediate delivery for state changes
                        
                        # Send message (with appropriate delay)
                        if total_delay > 0:
                            # Apply timing protection delay during gameplay
                            task = asyncio.create_task(
                                self._send_delayed_message(user_id, user_game_data, total_delay)
                            )
                            protection_tasks.append(task)
                            # 🔒 CRITICAL: Track delayed tasks for potential cancellation
                            self.pending_delayed_tasks.append(task)
                        else:
                            # Send immediately for state changes and most gameplay
                            message = {
                                "type": "game_state",
                                "timestamp": time.time(),
                                "data": user_game_data
                            }
                            
                            success = await self.send_to_user(user_id, message)
                            if success:
                                sent_count += 1
                            else:
                                failed_users.append(user_id)
                            
                    except Exception as e:
                        logger.error(f"❌ Error preparing protected update for user {user_id}: {e}")
                        failed_users.append(user_id)
            
            # Count delayed sends too
            sent_count += len(protection_tasks)
            
            # Clean up failed connections
            for user_id in failed_users:
                await self.disconnect(user_id, "Protected broadcast failed")
            
            # Store base state for next comparison (without user-specific data)
            self.last_broadcast_state = base_game_data.copy()
            self.last_broadcast_state["coefficient"] = raw_coefficient  # Store original for comparison
            
            # Only log occasionally to avoid spam - reduce noise completely
            if sent_count > 0 and int(time.time()) % 30 == 0:  # Log only successes every 30 seconds
                logger.debug(f"📡 Sent protected game_state to {sent_count} users: raw_coef={raw_coefficient}, status={status}")
            # Remove the "no subscribers" spam entirely
            
        except Exception as e:
            logger.error(f"❌ Error broadcasting game state: {e}", exc_info=True)
    
    async def _broadcast_player_status(self):
        """Broadcast player status updates (replaces /player-status polling)"""
        try:
            if not self.game_engine:
                return
            
            # Broadcast player status to each subscribed user
            for user_id in list(self.connection_info.keys()):
                if "player_status" in self.connection_info[user_id]["subscriptions"]:
                    try:
                        # Get player status using same logic as /player-status endpoint
                        player_status = await self._get_player_status(user_id)
                        if player_status:
                            await self.send_to_user(user_id, {
                                "type": "player_status",
                                "timestamp": time.time(),
                                "data": player_status
                            })
                    except Exception as e:
                        logger.error(f"❌ Error getting player status for {user_id}: {e}")
            
        except Exception as e:
            logger.error(f"❌ Error broadcasting player status: {e}")
    
    async def cancel_all_delayed_tasks(self):
        """🔒 CRITICAL: Cancel all pending delayed tasks to prevent conflicting messages"""
        try:
            cancelled_count = 0
            for task in self.pending_delayed_tasks:
                if not task.done():
                    task.cancel()
                    cancelled_count += 1
            
            # Clear the list
            self.pending_delayed_tasks.clear()
            
            if cancelled_count > 0:
                pass
                
        except Exception as e:
            logger.error(f"❌ Error cancelling delayed tasks: {e}")

    async def broadcast_immediate_player_status(self):
        """🔒 IMMEDIATE: Broadcast player status immediately (for crash/critical events)"""
        try:
            
            # 🔒 CRITICAL: Cancel all delayed tasks first to prevent conflicts
            await self.cancel_all_delayed_tasks()
            
            # Send immediate player status
            await self._broadcast_player_status()
            
            # 🔒 ALSO send immediate game state to ensure consistency
            await self._broadcast_game_state()
            
        except Exception as e:
            logger.error(f"❌ Error in immediate player status broadcast: {e}")
    
    async def _get_player_status(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get player status for specific user (same logic as /player-status endpoint)"""
        try:
            if not self.game_engine:
                return None
                
            # Get current game status
            state = await self.game_engine.get_current_status() if self.game_engine else {}
            game_status = state.get("status", "unknown")
            game_just_crashed = state.get("game_just_crashed", False)
            
            # Check current round first
            player_data = await self.game_engine.redis.get_player_data(user_id)
            if player_data:
                return {
                    "in_game": True,
                    "joined_at": player_data.get("joined_at"),
                    "bet_amount": str(player_data.get("bet_amount", "0")),
                    "cashed_out": player_data.get("cashed_out", False),
                    "did_cashout_this_round": player_data.get("cashed_out", False),
                    "cashout_coef": str(player_data.get("cashout_coef", "0")) if player_data.get("cashout_coef") else None,
                    "from_last_round": False,
                    "game_status": game_status,
                    "show_win_message": False,
                    "show_crash_message": False,
                    "win_amount": "0",
                    "win_multiplier": "0"
                }
            
            # Check last round data if in waiting status
            if game_status == "waiting":
                try:
                    last_player_data = await self.game_engine.redis.cache_get(f"last_player_{user_id}")
                    if last_player_data:
                        import json
                        if isinstance(last_player_data, str):
                            last_player_data = json.loads(last_player_data)
                        
                        # ИГРОК ИГРАЛ в прошлом раунде
                        if last_player_data.get("bet_amount"):
                            from decimal import Decimal
                            
                            if last_player_data.get("cashed_out") and last_player_data.get("cashout_coef"):
                                # Player won - cashed out
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
                                    "win_multiplier": str(cashout_coef)
                                }
                            else:
                                # Player lost - didn't cash out
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
                                    "win_amount": "0",
                                    "win_multiplier": "0"
                                }
                except Exception as e:
                    logger.error(f"⚠️ Error checking last player data: {e}")
                
                # Show info crash if game just crashed and player didn't play
                if game_just_crashed:
                    return {
                        "in_game": False,
                        "did_cashout_this_round": False,
                        "from_last_round": False,
                        "game_status": game_status,
                        "show_win_message": False,
                        "show_crash_message": True,
                        "win_amount": "0",
                        "win_multiplier": "0"
                    }
            
            # Default: no messages
            return {
                "in_game": False,
                "did_cashout_this_round": False,
                "from_last_round": False,
                "game_status": game_status,
                "show_win_message": False,
                "show_crash_message": False,
                "win_amount": "0",
                "win_multiplier": "0"
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting player status for {user_id}: {e}")
            return None
    
    async def _get_crash_history_data(self) -> list:
        """Get crash history from Redis with PostgreSQL fallback"""
        try:
            if not self.game_engine:
                return []
            
            # Try Redis first
            redis_client = await self.game_engine.redis.get_client()
            history_raw = await redis_client.lrange("crash_history", 0, 19)
            
            if history_raw:
                # Convert to str (NO float for money values!)
                return [str(coeff) for coeff in history_raw if coeff]
            
            # 🚀 FALLBACK: If Redis is empty, get from PostgreSQL
            logger.info("📊 Redis crash history empty, falling back to PostgreSQL")
            try:
                from config.settings import DISABLE_POSTGRESQL_GAME_HISTORY
                if not DISABLE_POSTGRESQL_GAME_HISTORY and self.game_engine.migration_service:
                    from database import AsyncSessionLocal
                    
                    # Get last 20 games from PostgreSQL
                    from sqlalchemy import text
                    query = text("""
                        SELECT crash_point 
                        FROM game_history 
                        WHERE is_completed = true 
                        ORDER BY played_at DESC 
                        LIMIT 20
                    """)
                    
                    async with AsyncSessionLocal() as session:
                        result = await session.execute(query)
                        rows = result.fetchall()
                        
                        if rows:
                            history = [str(row[0]) for row in rows]
                            logger.info(f"📊 Loaded {len(history)} crash history items from PostgreSQL")
                            
                            # Cache in Redis for future requests
                            for coeff in reversed(history):  # Reverse to maintain chronological order
                                await redis_client.lpush("crash_history", str(coeff))
                            await redis_client.ltrim("crash_history", 0, 49)  # Keep last 50
                            
                            return history
                        
            except Exception as e:
                logger.error(f"❌ PostgreSQL fallback failed: {e}")
            
            return []
            
        except Exception as e:
            logger.error(f"❌ Error getting crash history data: {e}")
            return []
    
    async def _send_crash_history_to_user(self, user_id: int):
        """Send crash history to a specific user (for new subscribers)"""
        try:
            history = await self._get_crash_history_data()
            if history:
                await self.send_to_user(user_id, {
                    "type": "crash_history",
                    "timestamp": time.time(),
                    "data": {"history": history}
                })
            else:
                logger.warning(f"📈 No crash history available for user {user_id}")
                
        except Exception as e:
            logger.error(f"❌ Error sending crash history to user {user_id}: {e}")
    
    async def _send_balance_to_user(self, user_id: int):
        """Send current balance to a specific user (for new balance_update subscribers)"""
        try:
            if not self.game_engine:
                logger.warning(f"💰 No game engine available for balance lookup")
                return
                
            # Get current balance from database service
            balance = await self.game_engine.database.get_user_balance(user_id)
            if balance is not None:
                await self.send_to_user(user_id, {
                    "type": "balance_update",
                    "timestamp": time.time(),
                    "data": {
                        "user_id": user_id,
                        "balance": str(balance),  # Always string for money values
                        "reason": "subscription",
                        "timestamp": time.time()
                    }
                })
            else:
                logger.warning(f"💰 No balance available for user {user_id}")
                
        except Exception as e:
            logger.error(f"❌ Error sending balance to user {user_id}: {e}")
    
    async def _broadcast_crash_history(self):
        """Broadcast crash history updates (replaces /crash-history polling) - OPTIMIZED with change detection"""
        try:
            history = await self._get_crash_history_data()
            if not history:
                return
            
            # PERFORMANCE: Only broadcast if history changed
            if self.last_crash_history and history == self.last_crash_history:
                return  # Skip broadcast if history unchanged
            
            await self.broadcast_to_subscribed("crash_history", {"history": history})
            self.last_crash_history = history.copy()
            
        except Exception as e:
            logger.error(f"❌ Error broadcasting crash history: {e}")
    
    async def broadcast_balance_update(self, user_id: int, new_balance: str, reason: str = "game_action"):
        """Broadcast balance update to specific user via WebSocket - REPLACES HTTP polling"""
        try:
            balance_data = {
                "user_id": user_id,
                "balance": str(new_balance),  # Always string for money values
                "reason": reason,
                "timestamp": time.time()
            }
            
            # Send to specific user if they're connected
            success = await self.send_to_user(user_id, {
                "type": "balance_update",
                "timestamp": time.time(),
                "data": balance_data
            })
            
            if success:
                pass
            else:
                logger.debug(f"💰 User {user_id} not connected - balance update skipped")
                
        except Exception as e:
            logger.error(f"❌ Error broadcasting balance update: {e}")
    
    async def broadcast_balance_updates_batch(self, balance_updates: list):
        """Broadcast multiple balance updates efficiently"""
        try:
            if not balance_updates:
                return
                
            sent_count = 0
            for update in balance_updates:
                user_id = update.get("user_id")
                balance = update.get("balance")
                reason = update.get("reason", "batch_update")
                
                if user_id and balance is not None:
                    success = await self.broadcast_balance_update(user_id, balance, reason)
                    if success:
                        sent_count += 1
            
            if sent_count > 0:
                logger.info(f"💰 Batch balance updates sent: {sent_count}/{len(balance_updates)} users")
                
        except Exception as e:
            logger.error(f"❌ Error broadcasting batch balance updates: {e}")
    
    async def _broadcast_all_user_balances(self):
        """Broadcast current balance to all subscribed users every ~5 seconds"""
        try:
            if not self.game_engine:
                return
                
            sent_count = 0
            
            for user_id, info in self.connection_info.items():
                if "balance_update" in info["subscriptions"]:
                    try:
                        balance = await self.game_engine.database.get_user_balance(user_id)
                        if balance is not None:
                            await self.send_to_user(user_id, {
                                "type": "balance_update",
                                "timestamp": time.time(),
                                "data": {
                                    "user_id": user_id,
                                    "balance": str(balance),
                                    "reason": "periodic_sync",
                                    "timestamp": time.time()
                                }
                            })
                            sent_count += 1
                    except Exception as e:
                        logger.error(f"❌ Error broadcasting balance to user {user_id}: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Error in periodic balance broadcast: {e}")
    
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        return {
            "active_connections": len(self.active_connections),
            "running": self._running,
            "subscriptions": {
                user_id: list(info["subscriptions"]) 
                for user_id, info in self.connection_info.items()
            }
        }

# Global WebSocket manager instance
websocket_manager = WebSocketManager()