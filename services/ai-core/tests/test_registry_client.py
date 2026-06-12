import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from core.registry_client import ServiceRegistryClient

@pytest.mark.asyncio
async def test_get_internal_ip():
    client = ServiceRegistryClient(service_name="test-service", port=1234)
    ip = client._get_internal_ip()
    assert ip is not None
    assert isinstance(ip, str)
    assert len(ip) > 0

@pytest.mark.asyncio
async def test_register_success():
    client = ServiceRegistryClient(service_name="test-service", port=1234)
    
    with patch("core.registry_client.redis_client") as mock_redis:
        mock_redis.sadd = AsyncMock(return_value=1)
        mock_redis.setex = AsyncMock(return_value=True)
        
        # We also mock the heartbeat loop to prevent it from running forever
        with patch.object(client, "_heartbeat_loop", AsyncMock()) as mock_heartbeat:
            success = await client.register()
            
            assert success is True
            assert client._running is True
            mock_redis.sadd.assert_called_once_with("registry:service:test-service", f"{client.ip}:1234")
            mock_redis.setex.assert_called_once_with(
                f"registry:service:test-service:node:{client.ip}:1234", 15, "alive"
            )
            client._heartbeat_task.cancel()

@pytest.mark.asyncio
async def test_register_failure():
    client = ServiceRegistryClient(service_name="test-service", port=1234)
    
    with patch("core.registry_client.redis_client") as mock_redis:
        mock_redis.sadd = AsyncMock(side_effect=Exception("Redis connection error"))
        
        success = await client.register()
        assert success is False
        assert client._running is True  # Fail-safe keeps the client running for self-healing
        
        # Cleanup heartbeat task to prevent warnings
        client._heartbeat_task.cancel()
        try:
            await client._heartbeat_task
        except asyncio.CancelledError:
            pass

@pytest.mark.asyncio
async def test_deregister():
    client = ServiceRegistryClient(service_name="test-service", port=1234)
    client._running = True
    
    # Create a real asyncio future so it is natively awaitable
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    future.set_result(None)
    future.cancel = MagicMock()
    client._heartbeat_task = future
    
    with patch("core.registry_client.redis_client") as mock_redis:
        mock_redis.srem = AsyncMock(return_value=1)
        mock_redis.delete = AsyncMock(return_value=1)
        
        success = await client.deregister()
        
        assert success is True
        assert client._running is False
        future.cancel.assert_called_once()
        mock_redis.srem.assert_called_once_with("registry:service:test-service", f"{client.ip}:1234")
        mock_redis.delete.assert_called_once_with(f"registry:service:test-service:node:{client.ip}:1234")
