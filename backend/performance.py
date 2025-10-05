"""
Production-ready performance optimizations for crash game backend
Connection pooling, caching, async batching, and monitoring
"""

import asyncio
import time
from typing import Dict, Any, Optional, List
from functools import wraps, lru_cache
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import json

import os

# Configuration from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost/crash_game")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Performance configuration
PERFORMANCE_CONFIG = {
    "redis_pool_size": 20,
    "db_pool_size": 10,
    "db_max_overflow": 20,
    "cache_ttl": 300,
    "batch_size": 100,
    "batch_flush_interval": 1.0
}

class PerformanceOptimizer:
    """Central performance optimization manager"""
    
    def __init__(self):
        self.db_engine = None
        self.db_session_maker = None
        self.redis_pool = None
        self.batch_operations = []
        self.last_batch_flush = time.time()
        
        # Performance metrics
        self.metrics = {
            "database_queries": 0,
            "redis_operations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "batch_operations": 0
        }
    
    async def init_database_pool(self):
        """Initialize optimized database connection pool"""
        self.db_engine = create_async_engine(
            DATABASE_URL,
            # Don't specify poolclass for async engines - it will use the default async pool
            pool_size=PERFORMANCE_CONFIG["db_pool_size"],
            max_overflow=PERFORMANCE_CONFIG["db_max_overflow"],
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,  # Disable SQL logging for performance
            # Additional optimizations
            connect_args={
                "server_settings": {
                    "application_name": "crash_stars_optimized",
                    "jit": "off"  # Disable JIT for predictable performance
                }
            }
        )
        
        self.db_session_maker = async_sessionmaker(
            bind=self.db_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        print(f"Database pool initialized: {PERFORMANCE_CONFIG['db_pool_size']} base + {PERFORMANCE_CONFIG['db_max_overflow']} overflow")
    
    async def init_redis_pool(self):
        """Initialize optimized Redis connection pool"""
        self.redis_pool = redis.ConnectionPool.from_url(
            REDIS_URL,
            max_connections=PERFORMANCE_CONFIG["redis_pool_size"],
            retry_on_timeout=True,
            socket_keepalive=True,
            socket_keepalive_options={},
            decode_responses=True
        )
        
        print(f"Redis pool initialized: {PERFORMANCE_CONFIG['redis_pool_size']} connections")
    
    def get_db_session(self) -> AsyncSession:
        """Get database session from pool"""
        return self.db_session_maker()
    
    def get_redis_client(self) -> redis.Redis:
        """Get Redis client from pool"""
        return redis.Redis(connection_pool=self.redis_pool)
    
    async def batch_operation(self, operation_type: str, data: Dict[str, Any]):
        """Add operation to batch for processing"""
        self.batch_operations.append({
            "type": operation_type,
            "data": data,
            "timestamp": time.time()
        })
        
        # Auto-flush if batch is full or time interval exceeded
        if (len(self.batch_operations) >= PERFORMANCE_CONFIG["batch_size"] or
            time.time() - self.last_batch_flush >= PERFORMANCE_CONFIG["batch_flush_interval"]):
            await self.flush_batch()
    
    async def flush_batch(self):
        """Process all pending batch operations"""
        if not self.batch_operations:
            return
        
        operations = self.batch_operations.copy()
        self.batch_operations.clear()
        self.last_batch_flush = time.time()
        
        # Group by operation type
        grouped = {}
        for op in operations:
            op_type = op["type"]
            if op_type not in grouped:
                grouped[op_type] = []
            grouped[op_type].append(op["data"])
        
        # Process each group
        for op_type, ops in grouped.items():
            try:
                await self._process_batch_group(op_type, ops)
                self.metrics["batch_operations"] += len(ops)
            except Exception as e:
                print(f"Batch processing error for {op_type}: {e}")
    
    async def _process_batch_group(self, op_type: str, operations: List[Dict]):
        """Process a specific type of batch operations"""
        if op_type == "balance_update":
            await self._batch_balance_updates(operations)
        elif op_type == "stats_update":
            await self._batch_stats_updates(operations)
        elif op_type == "redis_set":
            await self._batch_redis_operations(operations)
    
    async def _batch_balance_updates(self, operations: List[Dict]):
        """Batch process balance updates to reduce database load"""
        if not operations:
            return
        
        async with self.get_db_session() as session:
            # Group by user_id to consolidate multiple updates
            user_updates = {}
            for op in operations:
                user_id = op["user_id"]
                amount = op["amount"]
                if user_id not in user_updates:
                    user_updates[user_id] = 0
                user_updates[user_id] += amount
            
            # Apply consolidated updates
            for user_id, total_amount in user_updates.items():
                if total_amount != 0:  # Only update if there's a net change
                    # Use raw SQL for performance
                    from sqlalchemy import text
                    await session.execute(
                        text("UPDATE users SET balance = GREATEST(balance + :amount, 0) WHERE telegram_id = :user_id"),
                        {"amount": total_amount, "user_id": user_id}
                    )
            
            await session.commit()
            self.metrics["database_queries"] += 1
    
    async def _batch_redis_operations(self, operations: List[Dict]):
        """Batch Redis operations using pipeline"""
        if not operations:
            return
        
        client = self.get_redis_client()
        pipe = client.pipeline()
        
        for op in operations:
            if op["operation"] == "set":
                pipe.set(op["key"], op["value"])
            elif op["operation"] == "hset":
                pipe.hset(op["key"], op["field"], op["value"])
            elif op["operation"] == "setex":
                pipe.setex(op["key"], op["ttl"], op["value"])
        
        await pipe.execute()
        self.metrics["redis_operations"] += len(operations)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get current performance statistics"""
        return {
            "metrics": self.metrics.copy(),
            "batch_queue_size": len(self.batch_operations),
            "time_since_last_flush": time.time() - self.last_batch_flush,
            "config": PERFORMANCE_CONFIG
        }

# Global instance
performance_optimizer = PerformanceOptimizer()

async def init_performance():
    """Initialize all performance optimizations"""
    await performance_optimizer.init_database_pool()
    await performance_optimizer.init_redis_pool()
    
    # Start background batch flushing
    asyncio.create_task(_background_batch_flush())
    
    print("Performance optimizations initialized")

async def _background_batch_flush():
    """Background task to flush batches periodically"""
    while True:
        try:
            await asyncio.sleep(PERFORMANCE_CONFIG["batch_flush_interval"])
            await performance_optimizer.flush_batch()
        except Exception as e:
            print(f"Background batch flush error: {e}")
            await asyncio.sleep(1)

def performance_monitor(func):
    """Decorator to monitor function performance"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            # Log slow operations
            if execution_time > 1.0:  # More than 1 second
                print(f"Slow operation detected: {func.__name__} took {execution_time:.2f}s")
            
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            print(f"Function {func.__name__} failed after {execution_time:.2f}s: {e}")
            raise
    return wrapper

class RedisCache:
    """High-performance Redis caching layer"""
    
    def __init__(self):
        self.local_cache = {}
        self.cache_stats = {"hits": 0, "misses": 0}
    
    async def get(self, key: str, default=None):
        """Get from cache with local + Redis layers"""
        # Try local cache first (fastest)
        if key in self.local_cache:
            entry = self.local_cache[key]
            if time.time() < entry["expires"]:
                self.cache_stats["hits"] += 1
                performance_optimizer.metrics["cache_hits"] += 1
                return entry["data"]
            else:
                del self.local_cache[key]
        
        # Try Redis
        try:
            client = performance_optimizer.get_redis_client()
            value = await client.get(key)
            if value:
                self.cache_stats["hits"] += 1
                performance_optimizer.metrics["cache_hits"] += 1
                data = json.loads(value) if value.startswith('{') or value.startswith('[') else value
                
                # Store in local cache
                self.local_cache[key] = {
                    "data": data,
                    "expires": time.time() + 30  # 30 second local cache
                }
                return data
        except Exception as e:
            print(f"Cache get error: {e}")
        
        self.cache_stats["misses"] += 1
        performance_optimizer.metrics["cache_misses"] += 1
        return default
    
    async def set(self, key: str, value: Any, ttl: int = None):
        """Set in cache with batching"""
        ttl = ttl or PERFORMANCE_CONFIG["cache_ttl"]
        
        # Add to batch for Redis
        await performance_optimizer.batch_operation("redis_set", {
            "operation": "setex",
            "key": key,
            "value": json.dumps(value) if isinstance(value, (dict, list)) else str(value),
            "ttl": ttl
        })
        
        # Store in local cache immediately
        self.local_cache[key] = {
            "data": value,
            "expires": time.time() + min(ttl, 60)
        }

# Global cache instance
cache = RedisCache()

@lru_cache(maxsize=1000)
def cached_calculation(input_data: str) -> Any:
    """LRU cached calculations for frequently computed values"""
    # This would contain expensive calculations that can be cached
    # For example: coefficient calculations, probability distributions, etc.
    import json
    data = json.loads(input_data)
    # Perform calculation...
    return data

def get_performance_optimizer() -> PerformanceOptimizer:
    """Get global performance optimizer instance"""
    return performance_optimizer

def get_cache() -> RedisCache:
    """Get global cache instance"""
    return cache