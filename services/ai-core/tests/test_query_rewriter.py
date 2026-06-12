import pytest
import hashlib
from unittest.mock import AsyncMock, MagicMock
from gateway.query_rewriter import QueryRewriter

@pytest.mark.asyncio
async def test_first_message_bypass():
    """Bypass rewriting if history is empty (messages count < 2)."""
    redis_mock = AsyncMock()
    gateway_mock = AsyncMock()
    
    rewriter = QueryRewriter(redis_mock, gateway_mock)
    messages = [{"role": "user", "content": "Xin chào, tôi muốn mua pin."}]
    
    result = await rewriter.rewrite("tenant-1", messages)
    
    assert result == "Xin chào, tôi muốn mua pin."
    gateway_mock.complete.assert_not_called()
    redis_mock.get.assert_not_called()

@pytest.mark.asyncio
async def test_rewrite_coreference_vi():
    """Verify contextual query is successfully rewritten into a standalone query."""
    redis_mock = AsyncMock()
    # Mock cache miss
    redis_mock.get.return_value = None
    
    gateway_mock = AsyncMock()
    gateway_mock.complete.return_value = {
        "content": "Giá pin lithium Solavie là bao nhiêu?",
        "model_used": "gpt-4o-mini"
    }
    
    rewriter = QueryRewriter(redis_mock, gateway_mock)
    messages = [
        {"role": "user", "content": "Pin lithium Solavie dùng tốt không?"},
        {"role": "assistant", "content": "Dạ rất tốt ạ, bảo hành 25 năm."},
        {"role": "user", "content": "Loại đó giá bao nhiêu?"}
    ]
    
    result = await rewriter.rewrite("tenant-1", messages)
    
    assert result == "Giá pin lithium Solavie là bao nhiêu?"
    gateway_mock.complete.assert_called_once()
    redis_mock.get.assert_called_once()
    redis_mock.setex.assert_called_once()

@pytest.mark.asyncio
async def test_standalone_query_bypass():
    """Verify if rewritten query is identical to original if it's already standalone."""
    redis_mock = AsyncMock()
    redis_mock.get.return_value = None
    
    gateway_mock = AsyncMock()
    gateway_mock.complete.return_value = {
        "content": "Thời gian sạc pin iPhone là bao nhiêu?",
        "model_used": "gpt-4o-mini"
    }
    
    rewriter = QueryRewriter(redis_mock, gateway_mock)
    messages = [
        {"role": "user", "content": "Pin lithium Solavie dùng tốt không?"},
        {"role": "assistant", "content": "Dạ tốt ạ."},
        {"role": "user", "content": "Thời gian sạc pin iPhone là bao nhiêu?"}
    ]
    
    result = await rewriter.rewrite("tenant-1", messages)
    assert result == "Thời gian sạc pin iPhone là bao nhiêu?"

@pytest.mark.asyncio
async def test_redis_cache_hit():
    """If Redis cache hits, return cached query directly without calling LLM."""
    redis_mock = AsyncMock()
    redis_mock.get.return_value = b"Cached standalone query"
    
    gateway_mock = AsyncMock()
    
    rewriter = QueryRewriter(redis_mock, gateway_mock)
    messages = [
        {"role": "user", "content": "Hỏi về pin?"},
        {"role": "user", "content": "Loại đó tốt không?"}
    ]
    
    result = await rewriter.rewrite("tenant-1", messages)
    
    assert result == "Cached standalone query"
    gateway_mock.complete.assert_not_called()
    redis_mock.get.assert_called_once()

@pytest.mark.asyncio
async def test_llm_error_fallback():
    """If LLM call fails, fallback to the original query and log warning."""
    redis_mock = AsyncMock()
    redis_mock.get.return_value = None
    
    gateway_mock = AsyncMock()
    gateway_mock.complete.side_effect = Exception("LLM Timeout Connection error")
    
    rewriter = QueryRewriter(redis_mock, gateway_mock)
    messages = [
        {"role": "user", "content": "Pin Solavie?"},
        {"role": "user", "content": "Giá của nó?"}
    ]
    
    result = await rewriter.rewrite("tenant-1", messages)
    
    # Fallback to original query
    assert result == "Giá của nó?"
    redis_mock.setex.assert_not_called()

@pytest.mark.asyncio
async def test_cache_key_tenant_isolated():
    """Verify cache keys are tenant isolated even with identical queries."""
    redis_mock = AsyncMock()
    redis_mock.get.return_value = None
    
    gateway_mock = AsyncMock()
    gateway_mock.complete.return_value = {
        "content": "Giá pin lithium Solavie là bao nhiêu?",
        "model_used": "gpt-4o-mini"
    }
    
    rewriter = QueryRewriter(redis_mock, gateway_mock)
    messages = [
        {"role": "user", "content": "Pin Solavie?"},
        {"role": "user", "content": "Giá?"}
    ]
    
    await rewriter.rewrite("tenant-A", messages)
    await rewriter.rewrite("tenant-B", messages)
    
    assert redis_mock.get.call_count == 2
    
    # Extract keys checked
    calls = redis_mock.get.call_args_list
    key_A = calls[0][0][0]
    key_B = calls[1][0][0]
    
    assert key_A != key_B
    assert "tenant-A" in key_A
    assert "tenant-B" in key_B

@pytest.mark.asyncio
async def test_cache_ttl():
    """Verify Redis cache setex uses exactly 3600s TTL."""
    redis_mock = AsyncMock()
    redis_mock.get.return_value = None
    
    gateway_mock = AsyncMock()
    gateway_mock.complete.return_value = {
        "content": "Giá pin lithium Solavie là bao nhiêu?",
        "model_used": "gpt-4o-mini"
    }
    
    rewriter = QueryRewriter(redis_mock, gateway_mock)
    messages = [
        {"role": "user", "content": "Pin Solavie?"},
        {"role": "user", "content": "Giá?"}
    ]
    
    await rewriter.rewrite("tenant-1", messages)
    
    redis_mock.setex.assert_called_once()
    args, kwargs = redis_mock.setex.call_args
    # args: (key, ttl, value)
    assert args[1] == 3600
    assert args[2] == "Giá pin lithium Solavie là bao nhiêu?"
