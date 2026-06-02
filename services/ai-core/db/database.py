from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from core.config import settings

# Create async engine
engine = create_async_engine(
    settings.AI_CORE_DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True
)

# Async session maker
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Declarative Base for models
Base = declarative_base()

async def get_db():
    """Dependency for getting DB session"""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
