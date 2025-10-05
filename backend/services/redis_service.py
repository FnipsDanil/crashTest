"""
Redis service for crash game backend
Handles all Redis operations with connection pooling and performance optimizations
"""

import json
import time
import asyncio
import logging
import hashlib
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
import redis.asyncio as redis
from redis.asyncio import ConnectionPool

# Setup logging
logger = logging.getLogger(__name__)

def _serialize_decimals(data):
    """Convert Decimal objects to strings for JSON serialization"""
    if isinstance(data, dict):
        return {k: _serialize_decimals(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_serialize_decimals(item) for item in data]
    elif isinstance(data, Decimal):
        return str(data)
    else:
        return data

def _deserialize_decimals(data, decimal_fields=None):
    """Convert string values back to Decimal for specified fields"""
    if not isinstance(data, dict) or not decimal_fields:
        return data
    
    result = data.copy()
    for field in decimal_fields:
        if field in result and result[field] is not None:
            try:
                result[field] = Decimal(str(result[field]))
            except (ValueError, TypeError):
                # Keep original value if conversion fails
                pass
    return result

# Redis keys (same as original main.py)
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

# Performance config
PERFORMANCE_CONFIG = {
    "redis_pool_size": 20,
    "cache_ttl": 300
}

class RedisService:
    """High-performance Redis service with connection pooling"""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.pool: Optional[ConnectionPool] = None
        self.client: Optional[redis.Redis] = None
        self.connected = False
        
        # Redis keys for easy access
        self.keys = REDIS_KEYS
        
    async def connect(self) -> redis.Redis:
        """Initialize Redis connection with pooling"""
        try:
            # Create connection pool
            self.pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=PERFORMANCE_CONFIG["redis_pool_size"],
                retry_on_timeout=True,
                socket_keepalive=True,
                decode_responses=True
            )
            
            # Create Redis client
            self.client = redis.Redis(connection_pool=self.pool)
            
            # Test connection
            await self.client.ping()
            self.connected = True
            
            logger.info(f"✅ Redis connected with pool size {PERFORMANCE_CONFIG['redis_pool_size']}")
            return self.client
            
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            self.connected = False
            raise
    
    async def disconnect(self):
        """Close Redis connection"""
        try:
            if self.client:
                await self.client.close()
            if self.pool:
                await self.pool.disconnect()
            self.connected = False
            logger.info("🛑 Redis disconnected")
        except Exception as e:
            logger.warning(f"⚠️ Redis disconnect error: {e}")
    
    async def ping(self) -> bool:
        """Check Redis connection health"""
        try:
            if not self.client:
                return False
            await self.client.ping()
            return True
        except Exception:
            return False
    
    def get_client(self) -> redis.Redis:
        """Get Redis client instance (sync version - DEPRECATED)"""
        if not self.connected or not self.client:
            raise RuntimeError("Redis not connected")
        return self.client
    
    async def get_async_client(self) -> redis.Redis:
        """Get async Redis client instance (PREFERRED)"""
        if not self.connected or not self.client:
            raise RuntimeError("Redis not connected")
        return self.client
    
    # Game state operations
    async def get_game_state(self) -> Optional[Dict]:
        """Get current game state with integrity validation"""
        try:
            state_raw = await self.client.get(self.keys["CRASH_GAME"])
            if not state_raw:
                return None
                
            state_with_meta = json.loads(state_raw)
            
            # 🔒 SECURITY: Validate state integrity if checksum exists
            if "_checksum" in state_with_meta:
                stored_checksum = state_with_meta.pop("_checksum")
                stored_timestamp = state_with_meta.pop("_timestamp", 0)
                
                # Calculate checksum for current state
                calculated_checksum = self._calculate_state_checksum(state_with_meta)
                
                if stored_checksum != calculated_checksum:
                    logger.error(f"🚨 State corruption detected! Expected checksum: {calculated_checksum}, got: {stored_checksum}")
                    
                    # 🔒 SECURITY: Log Redis state corruption
                    try:
                        import asyncio
                        from security_monitor import get_security_monitor
                        security_monitor = get_security_monitor(self.client)
                        # Run async function in background
                        asyncio.create_task(security_monitor.log_redis_state_corruption(
                            "game_state_checksum_mismatch",
                            calculated_checksum,
                            stored_checksum
                        ))
                    except Exception as e:
                        logger.error(f"Failed to log security event: {e}")
                    
                    # Return None to force state recreation
                    return None
                
                # Check if state is too old (more than 5 minutes)
                if time.time() - stored_timestamp > 300:
                    logger.warning(f"⚠️ State is old ({time.time() - stored_timestamp:.1f}s), might be stale")
            
            return state_with_meta
        except Exception as e:
            logger.error(f"❌ Error getting game state: {e}")
            return None
    
    def _calculate_state_checksum(self, state: Dict) -> str:
        """Calculate SHA-256 checksum for state validation"""
        # Create deterministic JSON string for hashing
        state_str = json.dumps(state, sort_keys=True, default=str)
        return hashlib.sha256(state_str.encode()).hexdigest()
    
    async def set_game_state(self, state: Dict) -> bool:
        """Set game state with integrity validation"""
        try:
            # 🔒 SECURITY: Add checksum for state validation
            state_with_checksum = state.copy()
            state_with_checksum["_checksum"] = self._calculate_state_checksum(state)
            state_with_checksum["_timestamp"] = time.time()
            
            await self.client.set(self.keys["CRASH_GAME"], json.dumps(state_with_checksum, default=str))
            return True
        except Exception as e:
            logger.error(f"❌ Error setting game state: {e}")
            return False
    
    async def get_all_players(self) -> Dict[str, Dict]:
        """Get all current game players"""
        try:
            players_raw = await self.client.hgetall(self.keys["GAME_PLAYERS"])
            return {
                user_id: json.loads(data) 
                for user_id, data in players_raw.items()
            } if players_raw else {}
        except Exception as e:
            logger.error(f"❌ Error getting players: {e}")
            return {}
    
    async def get_player_data(self, user_id: Union[str, int]) -> Optional[Dict]:
        """Get specific player data with integrity validation"""
        try:
            player_raw = await self.client.hget(self.keys["GAME_PLAYERS"], str(user_id))
            if not player_raw:
                return None
                
            data_with_meta = json.loads(player_raw)
            
            # 🔒 SECURITY: Validate player data integrity if checksum exists
            if "_checksum" in data_with_meta:
                stored_checksum = data_with_meta.pop("_checksum")
                stored_timestamp = data_with_meta.pop("_updated_at", 0)
                
                # Calculate checksum for current data
                calculated_checksum = self._calculate_state_checksum(data_with_meta)
                
                if stored_checksum != calculated_checksum:
                    logger.error(f"🚨 Player data corruption detected for user {user_id}! Expected: {calculated_checksum}, got: {stored_checksum}")
                    # Remove corrupted data
                    await self.remove_player(user_id)
                    return None
                
                # Check if data is too old (more than 10 minutes for player data)
                if time.time() - stored_timestamp > 600:
                    logger.warning(f"⚠️ Player {user_id} data is old ({time.time() - stored_timestamp:.1f}s)")
            
            # Convert string values back to Decimal for money fields
            decimal_fields = ['bet_amount', 'win_amount', 'cashout_coef']
            return _deserialize_decimals(data_with_meta, decimal_fields)
        except Exception as e:
            logger.error(f"❌ Error getting player {user_id}: {e}")
            return None
    
    async def set_player_data(self, user_id: Union[str, int], data: Dict) -> bool:
        """Set player data with integrity validation"""
        try:
            # Convert Decimal objects to strings for JSON serialization
            serialized_data = _serialize_decimals(data)
            
            # 🔒 SECURITY: Add checksum for player data validation
            data_with_checksum = serialized_data.copy()
            data_with_checksum["_checksum"] = self._calculate_state_checksum(serialized_data)
            data_with_checksum["_updated_at"] = time.time()
            
            await self.client.hset(self.keys["GAME_PLAYERS"], str(user_id), json.dumps(data_with_checksum))
            return True
        except Exception as e:
            logger.error(f"❌ Error setting player {user_id}: {e}")
            return False
    
    async def remove_player(self, user_id: Union[str, int]) -> bool:
        """Remove player from current game"""
        try:
            await self.client.hdel(self.keys["GAME_PLAYERS"], str(user_id))
            return True
        except Exception as e:
            logger.error(f"❌ Error removing player {user_id}: {e}")
            return False
    
    async def clear_all_players(self) -> bool:
        """Clear all current players"""
        try:
            await self.client.delete(self.keys["GAME_PLAYERS"])
            return True
        except Exception as e:
            logger.error(f"❌ Error clearing players: {e}")
            return False
    
    # Last round operations
    async def save_last_round_players(self, players_data: Dict[str, Dict]) -> bool:
        """Save players from last round"""
        try:
            # Clear previous data
            await self.client.delete(self.keys["LAST_GAME_PLAYERS"])
            
            if players_data:
                # Add timestamp to each player
                for user_id, data in players_data.items():
                    data["saved_at"] = time.time()
                    data["round_ended"] = True
                    # Convert Decimal objects to strings for JSON serialization
                    serialized_data = _serialize_decimals(data)
                    await self.client.hset(
                        self.keys["LAST_GAME_PLAYERS"], 
                        user_id, 
                        json.dumps(serialized_data)
                    )
                logger.info(f"✅ Saved {len(players_data)} players from last round")
            else:
                # Set empty round flag
                await self.client.setex(
                    self.keys["EMPTY_ROUND_FLAG"], 
                    600, 
                    json.dumps({"empty_round": True, "round_ended_at": time.time()})
                )
                logger.info("✅ Set empty round flag")
            
            return True
        except Exception as e:
            logger.error(f"❌ Error saving last round players: {e}")
            return False
    
    async def get_last_round_player(self, user_id: Union[str, int]) -> Optional[Dict]:
        """Get player data from last round"""
        try:
            player_raw = await self.client.hget(self.keys["LAST_GAME_PLAYERS"], str(user_id))
            if player_raw:
                data = json.loads(player_raw)
                # Convert string values back to Decimal for money fields
                decimal_fields = ['bet_amount', 'win_amount', 'cashout_coef']
                return _deserialize_decimals(data, decimal_fields)
            return None
        except Exception as e:
            logger.error(f"❌ Error getting last round player {user_id}: {e}")
            return None
    
    async def was_empty_round(self) -> bool:
        """Check if last round was empty"""
        try:
            empty_data = await self.client.get(self.keys["EMPTY_ROUND_FLAG"])
            if empty_data:
                data = json.loads(empty_data)
                return data.get("empty_round", False)
            return False
        except Exception as e:
            logger.error(f"❌ Error checking empty round: {e}")
            return False
    
    # Balance operations
    async def get_user_balance(self, user_id: Union[str, int]):
        """Get user balance from Redis"""
        try:
            balance_raw = await self.client.hget(self.keys["USER_BALANCES"], str(user_id))
            return Decimal(str(balance_raw)) if balance_raw else Decimal('0.00')  # Default balance
        except Exception as e:
            logger.error(f"❌ Error getting balance for {user_id}: {e}")
            return Decimal('0.00')
    
    async def set_user_balance(self, user_id: Union[str, int], balance) -> bool:
        """Set user balance in Redis"""
        try:
            await self.client.hset(self.keys["USER_BALANCES"], str(user_id), str(balance))
            return True
        except Exception as e:
            logger.error(f"❌ Error setting balance for {user_id}: {e}")
            return False
    
    # 🔒 LUA SCRIPT: Атомарное обновление баланса с проверками
    _UPDATE_BALANCE_LUA_SCRIPT = """
    local balance_key = KEYS[1]
    local user_id = ARGV[1]
    local amount = tonumber(ARGV[2])
    local min_balance = tonumber(ARGV[3] or "0")
    local max_balance = tonumber(ARGV[4] or "999999999.99")
    
    -- Получаем текущий баланс
    local current_raw = redis.call('HGET', balance_key, user_id)
    local current_balance = current_raw and tonumber(current_raw) or 0.00
    
    -- Вычисляем новый баланс с проверками лимитов
    local new_balance = current_balance + amount
    
    -- Проверяем минимальный баланс (защита от овердрафта)
    if new_balance < min_balance then
        return {tostring(current_balance), "INSUFFICIENT_BALANCE", tostring(new_balance)}
    end
    
    -- Проверяем максимальный баланс (защита от переполнения)
    if new_balance > max_balance then
        new_balance = max_balance
    end
    
    -- Атомарно устанавливаем новый баланс
    redis.call('HSET', balance_key, user_id, tostring(new_balance))
    
    return {tostring(current_balance), "SUCCESS", tostring(new_balance)}
    """

    async def update_user_balance(self, user_id: Union[str, int], amount):
        """Update user balance atomically with enhanced safety checks"""
        try:
            # Используем улучшенный Lua скрипт
            result = await self.client.eval(
                self._UPDATE_BALANCE_LUA_SCRIPT,
                1,  # количество KEYS
                self.keys["USER_BALANCES"],
                str(user_id),
                str(amount),
                "0",  # min_balance
                "999999999.99"  # max_balance
            )
            
            old_balance, status, new_balance = result[0], result[1], result[2]
            
            if status == "INSUFFICIENT_BALANCE":
                logger.warning(f"💰 Insufficient balance for user {user_id}: {old_balance} + {amount} = {new_balance}")
                return None  # Indicates failure
            elif status == "SUCCESS":
                logger.info(f"💰 Atomic balance update for user {user_id}: {old_balance} → {new_balance} (Δ{amount})")
                return Decimal(str(new_balance))
            else:
                logger.error(f"💰 Unknown status from Lua script: {status}")
                return None
        except Exception as e:
            logger.error(f"❌ Error updating balance for {user_id}: {e}")
            # Fallback to non-atomic operation
            current = await self.get_user_balance(user_id)
            new_balance = max(Decimal('0.00'), current + Decimal(str(amount)))
            await self.set_user_balance(user_id, new_balance)
            return new_balance
    
    # Cache operations
    async def cache_set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Set cache with optional TTL"""
        try:
            ttl = ttl or PERFORMANCE_CONFIG["cache_ttl"]
            # Convert Decimal objects to strings for JSON serialization
            serialized_value = _serialize_decimals(value)
            await self.client.setex(key, ttl, json.dumps(serialized_value))
            return True
        except Exception as e:
            logger.error(f"❌ Error setting cache {key}: {e}")
            return False
    
    async def cache_get(self, key: str) -> Optional[Any]:
        """Get from cache"""
        try:
            value = await self.client.get(key)
            return json.loads(value) if value else None
        except Exception as e:
            logger.error(f"❌ Error getting cache {key}: {e}")
            return None
    
    async def delete_cache(self, key: str) -> bool:
        """Delete from cache"""
        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"❌ Error deleting cache {key}: {e}")
            return False
    
    # 🔒 IDEMPOTENCY: Invoice caching methods
    async def get_pending_invoice(self, user_id: int, amount: int) -> Optional[Dict]:
        """Get existing pending invoice for user_id + amount combination"""
        cache_key = f"invoice_pending:{user_id}:{amount}"
        try:
            cached_data = await self.cache_get(cache_key)
            if cached_data:
                return cached_data
            return None
        except Exception as e:
            logger.error(f"❌ Error getting pending invoice for user {user_id}, amount {amount}: {e}")
            return None

    async def set_pending_invoice(self, user_id: int, amount: int, invoice_data: Dict, ttl: int = 3600) -> bool:
        """Cache pending invoice with TTL for idempotency protection"""
        cache_key = f"invoice_pending:{user_id}:{amount}"
        try:
            await self.cache_set(cache_key, invoice_data, ttl)
            logger.info(f"🔒 Cached pending invoice for user {user_id}, amount {amount} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"❌ Error caching pending invoice for user {user_id}, amount {amount}: {e}")
            return False
    
    async def cache_delete(self, key: str) -> bool:
        """Delete from cache"""
        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"❌ Error deleting cache {key}: {e}")
            return False
    
    # Batch operations as required by architecture
    async def update_multiple_balances(self, updates: Dict[int, Any]) -> bool:
        """Update multiple user balances atomically using pipeline"""
        try:
            pipe = self.client.pipeline()
            for user_id, amount in updates.items():
                # Получаем текущий баланс и прибавляем amount как Decimal
                current_raw = await self.client.hget(self.keys["USER_BALANCES"], str(user_id))
                current = Decimal(str(current_raw)) if current_raw else Decimal('0.00')
                new_balance = current + Decimal(str(amount))
                pipe.hset(self.keys["USER_BALANCES"], str(user_id), str(new_balance))
            await pipe.execute()
            logger.info(f"✅ Updated {len(updates)} balances in batch")
            return True
        except Exception as e:
            logger.error(f"❌ Error updating multiple balances: {e}")
            return False
    
    async def batch_set_player_stats(self, stats_updates: Dict[int, Dict[str, Any]]) -> bool:
        """Batch update player statistics using pipeline"""
        try:
            pipe = self.client.pipeline()
            for user_id, stats in stats_updates.items():
                for stat_key, value in stats.items():
                    pipe.hset(f"user_stats:{user_id}", stat_key, value)
            await pipe.execute()
            logger.info(f"✅ Updated stats for {len(stats_updates)} users in batch")
            return True
        except Exception as e:
            logger.error(f"❌ Error batch updating stats: {e}")
            return False

    # Utility operations  
    async def delete_key(self, key: str) -> bool:
        """Delete a cache key"""
        try:
            result = await self.client.delete(key)
            return bool(result)
        except Exception as e:
            logger.error(f"❌ Error deleting cache key {key}: {e}")
            return False
    
    # 🔒 DISTRIBUTED LOCKING OPERATIONS
    async def acquire_lock(self, key: str, timeout: int = 30, retry_times: int = 0, retry_delay: float = 0.1) -> bool:
        """
        🔒 PRODUCTION-GRADE: Acquire distributed lock with Redis SET NX EX
        
        Args:
            key: Lock key (should be unique per resource)
            timeout: Lock expiration timeout in seconds (prevents deadlocks)
            retry_times: Number of retry attempts (0 = no retries) 
            retry_delay: Delay between retries in seconds
            
        Returns:
            bool: True if lock acquired successfully, False otherwise
            
        Example:
            lock_key = f"operation_lock:{user_id}:{resource_id}"
            if await redis.acquire_lock(lock_key, timeout=30):
                try:
                    # Critical section
                    pass
                finally:
                    await redis.release_lock(lock_key)
        """
        if not self.connected:
            logger.error(f"❌ Cannot acquire lock {key}: Redis not connected")
            return False
            
        attempt = 0
        while attempt <= retry_times:
            try:
                # SET key value NX EX - Atomic operation
                # NX: Only set if key doesn't exist
                # EX: Set expiration time in seconds
                result = await self.client.set(key, "locked", nx=True, ex=timeout)
                
                if result is True:
                    logger.debug(f"🔒 Lock acquired: {key} (timeout: {timeout}s)")
                    return True
                    
                # Lock not acquired
                if attempt < retry_times:
                    logger.debug(f"🔄 Lock busy, retrying {attempt + 1}/{retry_times}: {key}")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.debug(f"⏳ Lock busy, no retries: {key}")
                    
            except Exception as e:
                logger.error(f"❌ Error acquiring lock {key} (attempt {attempt + 1}): {e}")
                if attempt >= retry_times:
                    return False
                await asyncio.sleep(retry_delay)
                
            attempt += 1
            
        return False
    
    async def release_lock(self, key: str) -> bool:
        """
        🔓 PRODUCTION-GRADE: Release distributed lock safely
        
        Args:
            key: Lock key to release
            
        Returns:
            bool: True if lock was released, False if lock didn't exist or error
            
        Note: 
            - Uses DEL command (simple and atomic)
            - Does not verify lock ownership (for simplicity)
            - For ownership verification, use Lua script with unique lock values
        """
        if not self.connected:
            logger.error(f"❌ Cannot release lock {key}: Redis not connected")
            return False
            
        try:
            result = await self.client.delete(key)
            if result > 0:
                logger.debug(f"🔓 Lock released: {key}")
                return True
            else:
                logger.debug(f"🔓 Lock not found (already expired?): {key}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error releasing lock {key}: {e}")
            return False
    
    async def is_locked(self, key: str) -> bool:
        """
        🔍 Check if lock exists (non-blocking)
        
        Args:
            key: Lock key to check
            
        Returns:
            bool: True if lock exists, False otherwise
        """
        if not self.connected:
            return False
            
        try:
            result = await self.client.exists(key)
            return bool(result)
        except Exception as e:
            logger.error(f"❌ Error checking lock {key}: {e}")
            return False
    
    async def get_lock_ttl(self, key: str) -> Optional[int]:
        """
        ⏰ Get remaining TTL of lock in seconds
        
        Args:
            key: Lock key
            
        Returns:
            int: Remaining seconds, None if lock doesn't exist, -1 if no expiration
        """
        if not self.connected:
            return None
            
        try:
            ttl = await self.client.ttl(key)
            if ttl == -2:  # Key doesn't exist
                return None
            return ttl if ttl >= 0 else -1
        except Exception as e:
            logger.error(f"❌ Error getting lock TTL {key}: {e}")
            return None

    async def atomic_cache_cleanup(self, keys_to_delete: List[str], pattern_keys: List[str] = None) -> bool:
        """🔒 ATOMIC cache cleanup with rollback capability"""
        try:
            pipe = self.client.pipeline()
            deleted_keys = []
            
            # Start transaction
            pipe.multi()
            
            # Delete specific keys
            for key in keys_to_delete:
                pipe.delete(key)
                deleted_keys.append(key)
            
            # Delete pattern-based keys
            if pattern_keys:
                for pattern in pattern_keys:
                    # Find keys matching pattern
                    matching_keys = []
                    async for key in self.client.scan_iter(match=pattern):
                        matching_keys.append(key)
                        pipe.delete(key)
                    deleted_keys.extend(matching_keys)
            
            # Execute atomic cleanup
            result = await pipe.execute()
            
            if result:
                return True
            else:
                logger.error("🚨 Atomic cleanup failed - transaction aborted")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error in atomic cache cleanup: {e}")
            return False
    
    async def cleanup_expired_data(self):
        """Clean up expired data"""
        try:
            # Clean up old game flags
            await self.client.delete(self.keys["GAME_CRASHED_FLAG"])
            await self.client.delete(self.keys["EMPTY_ROUND_FLAG"])
            logger.info("🧹 Cleaned up expired game flags")
        except Exception as e:
            logger.error(f"❌ Error cleaning up: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get Redis service statistics"""
        try:
            info = await self.client.info()
            return {
                "connected": self.connected,
                "pool_size": PERFORMANCE_CONFIG["redis_pool_size"],
                "memory_usage": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0)
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}