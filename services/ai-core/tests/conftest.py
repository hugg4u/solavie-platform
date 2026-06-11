import pytest
import asyncio
from unittest.mock import AsyncMock

# Globally mock redis clients to prevent network requests during tests
import core.redis_client
core.redis_client.redis_client = AsyncMock()
core.redis_client.redis_pubsub_client = AsyncMock()

from db.database import engine

@pytest.fixture(scope="function", autouse=True)
def cleanup_connections():
    yield
    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            loop.create_task(engine.dispose())
        else:
            loop.run_until_complete(engine.dispose())
    except Exception:
        pass

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()
