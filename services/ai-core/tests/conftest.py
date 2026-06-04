import pytest
import asyncio
from db.database import engine
from core.redis_client import redis_client

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
            loop.create_task(redis_client.aclose())
        else:
            loop.run_until_complete(engine.dispose())
            loop.run_until_complete(redis_client.aclose())
    except Exception:
        pass

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()
