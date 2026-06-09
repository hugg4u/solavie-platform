import logging
import redis.asyncio as aioredis
from core.config import settings

logger = logging.getLogger(__name__)

# Create async Redis client
try:
    # Redis Cluster does not support database index, strip it if present in URL
    # e.g. redis://redis:6379/1 -> redis://redis:6379
    url = settings.REDIS_URL
    if "/" in url.replace("://", ""):
        parts = url.rsplit("/", 1)
        if parts[1].isdigit():
            url = parts[0]
            
    from redis.asyncio.cluster import RedisCluster
    redis_client = RedisCluster.from_url(url, decode_responses=True)
except Exception as e:
    logger.warning(f"Failed to initialize Redis Cluster: {e}. Falling back to Standalone Redis client.")
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

# Create a standalone Redis client dedicated for PubSub, as async RedisCluster lacks pubsub support
redis_pubsub_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

async def check_redis_connection() -> bool:
    """Helper to verify connection to Redis on startup."""
    try:
        await redis_client.ping()
        await redis_pubsub_client.ping()
        logger.info("Successfully connected to Redis.")
        return True
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return False
