import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from core.crypto import encrypt_key, decrypt_key
from tools.registry import ToolPermissionManager
from tools.executor import ToolExecutor

# --- Crypto Tests ---
def test_encryption_decryption_roundtrip():
    api_key = "sk-proj-1234567890abcdef"
    encrypted = encrypt_key(api_key)
    assert encrypted != api_key
    assert len(encrypted) > 0
    
    decrypted = decrypt_key(encrypted)
    assert decrypted == api_key

def test_encryption_empty_values():
    assert encrypt_key("") == ""
    assert decrypt_key("") == ""

# --- Redis Rate Limit Tests ---
# Note: check_rate_limit now uses atomic Lua eval (LUA_INCR_EXPIRE) instead of incr/expire
@pytest.mark.asyncio
async def test_redis_rate_limiter():
    pm = ToolPermissionManager()

    with patch("tools.registry.redis_client") as mock_redis:
        # Default tier: standard (get returns None for tier key)
        mock_redis.get = AsyncMock(return_value=None)

        # Simulate under limit (Lua eval returns count=1, limit=50 for standard)
        mock_redis.eval = AsyncMock(return_value=1)
        allowed = await pm.check_rate_limit("test-tenant", "web_search")
        assert allowed is True
        mock_redis.eval.assert_called_once()

        # Simulate over standard limit (count=60 > limit=50)
        mock_redis.eval = AsyncMock(return_value=60)
        allowed = await pm.check_rate_limit("test-tenant", "web_search")
        assert allowed is False

        # Free tier: web_search limit=20, count=25 → blocked
        mock_redis.get = AsyncMock(return_value=b"free")
        mock_redis.eval = AsyncMock(return_value=25)
        allowed = await pm.check_rate_limit("test-tenant", "web_search")
        assert allowed is False  # 25 > 20 free tier limit

        # Enterprise tier: web_search limit=200, count=150 → allowed
        mock_redis.get = AsyncMock(return_value=b"enterprise")
        mock_redis.eval = AsyncMock(return_value=150)
        allowed = await pm.check_rate_limit("test-tenant", "web_search")
        assert allowed is True  # 150 <= 200 enterprise limit

# --- Tool Executor Timeouts and URL Fetching ---
@pytest.mark.asyncio
async def test_tool_executor_jina_reader_mock():
    executor = ToolExecutor()
    with patch.object(executor.client, 'get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "# Jina Reader Markdown Content"
        mock_get.return_value = mock_response
        
        result = await executor._execute_fetch_url("https://example.com")
        assert "# Jina Reader Markdown" in result

@pytest.mark.asyncio
async def test_tool_executor_dynamic_timeouts():
    executor = ToolExecutor()
    
    # knowledge_base_search is interactive, so timeout should be 2.0s
    with patch.object(executor, '_route_and_execute', AsyncMock(return_value="result")):
        # Should not raise exception
        result = await executor.execute("knowledge_base_search", {"query": "test"}, "tenant-id")
        assert result == "result"
        
        # Test timeout failure on kb search (simulate a hanging call)
        async def slow_call(*args, **kwargs):
            await asyncio.sleep(3.0)
            return "too slow"
            
        with patch.object(executor, '_route_and_execute', slow_call):
            result = await executor.execute("knowledge_base_search", {"query": "test"}, "tenant-id")
            assert "timed out after 2.0 seconds" in result
