import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool
from models import Base

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://crash_stars_user:crash_stars_password@localhost:5432/crash_stars_db")

# Create async engine - use AsyncAdaptedQueuePool for async compatibility with PgBouncer
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL debugging
    poolclass=AsyncAdaptedQueuePool,
    # Pool settings optimized for PgBouncer transaction pooling
    pool_size=10,        # Persistent connections (must be < PgBouncer default_pool_size=20)
    max_overflow=0,      # No additional connections beyond pool_size
    pool_pre_ping=True,  # Test connections before use
    pool_recycle=3600,   # Recycle connections every hour to prevent stale connections
    pool_timeout=30,     # Wait up to 30s for available connection
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def init_db():
    """Initialize database tables with retry logic"""
    import asyncio
    import logging
    
    logger = logging.getLogger(__name__)
    max_retries = 30  # Wait up to 30 seconds for database
    retry_delay = 1   # 1 second between retries
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting database connection (attempt {attempt + 1}/{max_retries})")
            async with engine.begin() as conn:
                # Note: In production, use Alembic migrations instead
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Database initialized successfully")
                return
        except Exception as e:
            if "database system is starting up" in str(e).lower() or "cannot connect now" in str(e).lower():
                logger.warning(f"Database starting up, waiting {retry_delay}s... (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(retry_delay)
                continue
            else:
                # For other errors, re-raise immediately
                logger.error(f"Database connection failed: {e}")
                raise
    
    # If we get here, all retries failed
    raise Exception(f"Failed to connect to database after {max_retries} attempts")

async def get_db():
    """Dependency to get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# Connection health check
async def check_db_health():
    """Check if database connection is healthy"""
    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            return True
    except Exception:
        return False