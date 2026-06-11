import pytest
import struct
import hashlib
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from gateway.semantic_cache import SemanticCacheManager

@pytest.mark.asyncio
async def test_create_index_already_exists():
    cache_mgr = SemanticCacheManager()
    
    mock_ft = MagicMock()
    mock_ft.info = AsyncMock(return_value={"index_name": "idx:semantic_cache"})
    mock_ft.create_index = AsyncMock()
    cache_mgr.redis_client = MagicMock()
    cache_mgr.redis_client.ft.return_value = mock_ft
    
    await cache_mgr.create_index()
    
    mock_ft.info.assert_called_once()
    mock_ft.create_index.assert_not_called()

@pytest.mark.asyncio
async def test_create_index_new():
    cache_mgr = SemanticCacheManager()
    
    mock_ft = MagicMock()
    mock_ft.info = AsyncMock(side_effect=Exception("Index not found"))
    mock_ft.create_index = AsyncMock()
    cache_mgr.redis_client = MagicMock()
    cache_mgr.redis_client.ft.return_value = mock_ft
    
    await cache_mgr.create_index()
    
    mock_ft.info.assert_called_once()
    mock_ft.create_index.assert_called_once()

@pytest.mark.asyncio
async def test_lookup_hit():
    cache_mgr = SemanticCacheManager()
    
    mock_ft = MagicMock()
    mock_res = MagicMock()
    mock_doc = MagicMock()
    mock_doc.vector_score = "0.05"
    mock_doc.response = b"Cached response contents"
    mock_res.docs = [mock_doc]
    
    mock_ft.search = AsyncMock(return_value=mock_res)
    cache_mgr.redis_client = MagicMock()
    cache_mgr.redis_client.ft.return_value = mock_ft
    
    with patch.object(cache_mgr, "_embed", return_value=[0.1] * 384):
        response, similarity = await cache_mgr.lookup(
            tenant_id="tenant-123-uuid", 
            use_case="chatbot", 
            question="What is solar?"
        )
    
    assert response == "Cached response contents"
    assert similarity == 0.95
    mock_ft.search.assert_called_once()
    
    call_args = mock_ft.search.call_args[0][0]
    assert "tenant\\-123\\-uuid" in call_args.query_string()

@pytest.mark.asyncio
async def test_lookup_miss_below_threshold():
    cache_mgr = SemanticCacheManager()
    
    mock_ft = MagicMock()
    mock_res = MagicMock()
    mock_doc = MagicMock()
    mock_doc.vector_score = "0.15"
    mock_doc.response = b"Low similarity response"
    mock_res.docs = [mock_doc]
    
    mock_ft.search = AsyncMock(return_value=mock_res)
    cache_mgr.redis_client = MagicMock()
    cache_mgr.redis_client.ft.return_value = mock_ft
    
    with patch.object(cache_mgr, "_embed", return_value=[0.1] * 384):
        response, similarity = await cache_mgr.lookup(
            tenant_id="tenant-123", 
            use_case="chatbot", 
            question="What is solar?"
        )
    
    assert response is None
    assert similarity == 0.0
    mock_ft.search.assert_called_once()

@pytest.mark.asyncio
async def test_lookup_miss_empty():
    cache_mgr = SemanticCacheManager()
    
    mock_ft = MagicMock()
    mock_res = MagicMock()
    mock_res.docs = []
    
    mock_ft.search = AsyncMock(return_value=mock_res)
    cache_mgr.redis_client = MagicMock()
    cache_mgr.redis_client.ft.return_value = mock_ft
    
    with patch.object(cache_mgr, "_embed", return_value=[0.1] * 384):
        response, similarity = await cache_mgr.lookup(
            tenant_id="tenant-123", 
            use_case="chatbot", 
            question="What is solar?"
        )
    
    assert response is None
    assert similarity == 0.0

@pytest.mark.asyncio
async def test_write_async():
    cache_mgr = SemanticCacheManager()
    
    cache_mgr.redis_client = MagicMock()
    cache_mgr.redis_client.hset = AsyncMock(return_value=1)
    cache_mgr.redis_client.expire = AsyncMock(return_value=True)
    
    tenant_id = "tenant-abc"
    use_case = "chatbot"
    question = "How are you?"
    response_text = "I am a helpful assistant."
    
    with patch.object(cache_mgr, "_embed", return_value=[0.1] * 384):
        await cache_mgr.write_async(tenant_id, use_case, question, response_text)
    
    expected_hash = hashlib.md5(question.encode('utf-8')).hexdigest()
    expected_key = f"semantic_cache:{tenant_id}:{expected_hash}"
    
    cache_mgr.redis_client.hset.assert_called_once()
    actual_key = cache_mgr.redis_client.hset.call_args[1]["key"] if "key" in cache_mgr.redis_client.hset.call_args[1] else cache_mgr.redis_client.hset.call_args[0][0]
    assert actual_key == expected_key
    
    actual_mapping = cache_mgr.redis_client.hset.call_args[1].get("mapping") or cache_mgr.redis_client.hset.call_args[0][1]
    assert actual_mapping["tenant_id"] == tenant_id
    assert actual_mapping["use_case"] == use_case
    assert actual_mapping["question"] == question
    assert actual_mapping["response"] == response_text
    
    expected_vector = struct.pack("384f", *([0.1] * 384))
    assert actual_mapping["vector"] == expected_vector
    
    cache_mgr.redis_client.expire.assert_called_once()

@pytest.mark.asyncio
async def test_complete_semantic_cache_integration():
    from gateway.router import LLMGateway
    gateway = LLMGateway()
    
    tenant_id = "test-tenant-123"
    use_case = "chatbot"
    question = "Is solar power good?"
    response_content = "Yes, solar power is clean and renewable."
    
    # Mock LLM complete call dependencies
    mock_llm_response = MagicMock()
    mock_llm_response.cache_hit = False
    mock_llm_response.choices = [MagicMock()]
    mock_llm_response.choices[0].message.content = response_content
    mock_llm_response.choices[0].message.tool_calls = None
    mock_llm_response.usage.prompt_tokens = 10
    mock_llm_response.usage.completion_tokens = 20
    
    # We patch acompletion, credentials, and routing
    with patch("gateway.router.acompletion", AsyncMock(return_value=mock_llm_response)) as mock_acompletion, \
         patch.object(gateway, "get_routing", AsyncMock(return_value={
             "primary_model": "gpt-4o-mini", "fallback_model": "gpt-4o-mini",
             "provider": "openai", "fallback_provider": "openai",
             "temperature": 0.7, "max_tokens": 500,
         })), \
         patch.object(gateway, "get_provider_credentials", AsyncMock(return_value={"api_key": "sk-mock"})), \
         patch.object(gateway, "resolve_active_default_model", side_effect=lambda t, p, m: m):
         
        # Mock semantic_cache lookup and write_async
        # First call: cache miss (returns None, 0.0)
        gateway.semantic_cache.lookup = AsyncMock(return_value=(None, 0.0))
        gateway.semantic_cache.write_async = AsyncMock()
        
        messages = [{"role": "user", "content": question}]
        dummy_tools = [{"type": "function", "function": {"name": "test_tool", "description": "dummy"}}]
        
        # 1. First completion call (cache miss)
        res1 = await gateway.complete(tenant_id, use_case, messages, tools=dummy_tools)
        assert res1["content"] == response_content
        assert res1.get("cache_hit") is False
        
        # Verify LLM was called
        mock_acompletion.assert_called_once()
        
        # Verify write_async was triggered (wait briefly for async task to spawn)
        await asyncio.sleep(0.05)
        gateway.semantic_cache.write_async.assert_called_once_with(
            tenant_id, use_case, question, response_content
        )
        
        # 2. Second completion call (cache hit)
        # Mock cache hit (returns response, similarity 0.95)
        gateway.semantic_cache.lookup = AsyncMock(return_value=(response_content, 0.95))
        mock_acompletion.reset_mock()
        
        res2 = await gateway.complete(tenant_id, use_case, messages, tools=dummy_tools)
        assert res2["content"] == response_content
        assert res2.get("cache_hit") is True
        assert res2["model_used"] == "semantic-cache"
        assert res2["provider"] == "redis-stack"
        
        # Verify LLM was NOT called on cache hit
        mock_acompletion.assert_not_called()
