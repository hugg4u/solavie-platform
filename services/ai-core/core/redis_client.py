import logging
import redis.asyncio as aioredis
from core.config import settings

logger = logging.getLogger(__name__)

# Create async Redis client
redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

async def check_redis_connection() -> bool:
    """Helper to verify connection to Redis on startup."""
    try:
        await redis_client.ping()
        logger.info("Successfully connected to Redis.")
        return True
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return False
