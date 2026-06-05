import pytest
import asyncio
import os
import uuid
import json
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select
from gateway.router import LLMGateway, format_litellm_model
from tools.registry import ToolPermissionManager
from tools.executor import ToolExecutor
from agent.orchestrator import AgentOrchestrator

# --- Router Tests ---
@pytest.mark.asyncio
async def test_history_compression():
    gateway = LLMGateway()
    messages = [
        {"role": "user", "content": "hello 1" + "a" * 800},
        {"role": "assistant", "content": "hi 1" + "b" * 800},
        {"role": "user", "content": "hello 2"},
        {"role": "assistant", "content": "hi 2"},
        {"role": "user", "content": "hello 3"},
        {"role": "assistant", "content": "hi 3"},
        {"role": "user", "content": "hello 4"},
        {"role": "assistant", "content": "hi 4"},
        {"role": "user", "content": "hello 5"},
        {"role": "assistant", "content": "hi 5"}
    ]
    
    # We keep recent 5 messages. Older messages = messages[:-5] (indexes 0 to 4).
    # Total messages is 10 > keep_recent + 4. Length of older messages > 1600 > 1500 chars.
    with patch("gateway.router.redis_client.get", return_value=None):
        compressed = await gateway.compress_history("d3b07384-d113-4ec2-a5d8-7e30d1774e1d", messages, keep_recent=5)
        assert len(compressed) == 6  # 1 summary message + 5 recent messages
        assert compressed[0]["role"] == "system"
        assert "Background summary" in compressed[0]["content"]
        assert compressed[1]["content"] == "hi 3"

@pytest.mark.asyncio
async def test_history_compression_with_tool_messages():
    gateway = LLMGateway()
    messages = [
        {"role": "user", "content": "hello 1" + "a" * 800},
        {"role": "assistant", "content": "hi 1" + "b" * 800},
        {"role": "user", "content": "hello 2"},
        {"role": "assistant", "content": "hi 2"},
        {"role": "assistant", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "web_search", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_1", "name": "web_search", "content": "search result"},
        {"role": "assistant", "content": "final answer"},
        {"role": "user", "content": "thanks"},
        {"role": "assistant", "content": "welcome"},
        {"role": "user", "content": "bye"}
    ]
    
    # Natural split_index=5 would land on the orphaned 'tool' message at [5].
    # PASS 1 pulls it back to index=4 (the assistant+tool_calls at [4]).
    # PASS 2 (FIX-1A) then also sees that recent[0] is assistant+tool_calls and pulls
    # split_index back further to index=3 (the plain 'assistant' at [3]).
    # So older=[0..2], recent=[3..9] = 7 messages, plus 1 summary = 8 total.
    with patch("gateway.router.redis_client.get", return_value=None):
        compressed = await gateway.compress_history("d3b07384-d113-4ec2-a5d8-7e30d1774e1d", messages, keep_recent=5)
        
        # After both passes: 1 summary + 7 recent messages
        assert len(compressed) == 8
        assert compressed[0]["role"] == "system"
        # CRITICAL: first non-system message must NOT be assistant+tool_calls
        first_non_system = next(m for m in compressed if m["role"] != "system")
        assert not (first_non_system.get("role") == "assistant" and bool(first_non_system.get("tool_calls"))), (
            "FIX-1A: first non-system must not be assistant+tool_calls"
        )
        # The assistant+tool_calls is present in the recent slice (not orphaned)
        has_tool_call_in_recent = any(
            m.get("role") == "assistant" and m.get("tool_calls") for m in compressed
        )
        assert has_tool_call_in_recent
        # The matching tool message is also present
        has_tool_result = any(m.get("role") == "tool" for m in compressed)
        assert has_tool_result


@pytest.mark.asyncio
async def test_context_optimization():
    gateway = LLMGateway()
    long_content = "a" * 5000
    messages = [
        {"role": "context", "content": long_content, "metadata": {"source": "doc1"}},
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "checking...",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "kb_search", "arguments": "{}"}}]
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "name": "kb_search",
            "content": "doc result"
        }
    ]
    optimized = gateway.optimize_context(messages, max_context_chars=1000)
    assert len(optimized) == 4
    assert "[TRUNCATED FOR TOKEN OPTIMIZATION]" in optimized[0]["content"]
    assert len(optimized[0]["content"]) < 2000
    assert optimized[0]["metadata"] == {"source": "doc1"}
    
    # Assert other roles are preserved untouched
    assert optimized[1] == messages[1]
    assert optimized[2] == messages[2]
    assert optimized[3] == messages[3]

# --- Permission Manager Tests ---
def test_tool_permissions():
    pm = ToolPermissionManager()
    
    # Chatbot allowed tools
    chatbot_tools = pm.get_tools_for_use_case("chatbot")
    tool_names = [t["function"]["name"] for t in chatbot_tools]
    assert "knowledge_base_search" in tool_names
    assert "send_message" in tool_names
    assert "web_search" not in tool_names
    
    # Verification matrix
    assert pm.is_tool_allowed("chatbot", "knowledge_base_search") is True
    assert pm.is_tool_allowed("chatbot", "web_search") is False
    
    # Content generation allowed tools
    content_tools = pm.get_tools_for_use_case("content_generation")
    content_names = [t["function"]["name"] for t in content_tools]
    assert "web_search" in content_names

# --- Tool Executor Tests ---
@pytest.mark.asyncio
async def test_tool_executor_tavily_mock():
    executor = ToolExecutor()
    # Mocking external HTTP request to Tavily search and patching API key to non-empty
    from core.config import settings
    with patch.object(settings, 'TAVILY_API_KEY', 'test-key'):
        with patch.object(executor.client, 'post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "answer": "Test answer about solar panels",
                "results": []
            }
            mock_post.return_value = mock_response
            
            result = await executor._execute_web_search("solar panels")
            assert "Test answer" in result

# --- ReAct Orchestrator Tests ---
@pytest.mark.asyncio
async def test_react_agent_loop_limit():
    orchestrator = AgentOrchestrator()
    
    # Mock LLM gateway to always return a tool call to simulate infinite loop
    mock_tool_call = {
        "id": "call-123",
        "type": "function",
        "function": {
            "name": "send_message",
            "arguments": '{"conversation_id": "conv-123", "message": "infinite loop test"}'
        }
    }
    
    mock_complete = AsyncMock(return_value={
        "content": "Thinking...",
        "tool_calls": [mock_tool_call],
        "model_used": "gpt-4o-mini",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "cost_usd": 0.0001
    })
    
    with patch.object(orchestrator.gateway, 'complete', mock_complete):
        # Patch registry to always allow tool call and mock executor
        with patch.object(orchestrator.permission_manager, 'is_tool_allowed', return_value=True):
            with patch.object(orchestrator.permission_manager, 'is_user_authorized', return_value=True):
                with patch.object(orchestrator.permission_manager, 'check_rate_limit', return_value=True):
                    with patch.object(orchestrator.executor, 'execute', return_value="Here is knowledge base info"):
                        # Run the agent with admin role to bypass RBAC
                        result = await orchestrator.run(
                            tenant_id="test-tenant",
                            use_case="chatbot",
                            messages=[{"role": "user", "content": "infinite loop check"}],
                            user_role="admin"
                        )
                        
                        # Verify loop protection: iterations must be limited to 5
                        assert result["iterations"] == 5
                        assert len(result["tools_called"]) == 5

@pytest.mark.asyncio
async def test_model_formatting_and_breakers():
    gateway = LLMGateway()
    # Normalize model names
    assert format_litellm_model("Gemini 2.5 Flash Lite", "google") == "gemini/gemini-2.5-flash-lite"
    assert format_litellm_model("deepseek-chat", "deepseek") == "deepseek/deepseek-chat"
    assert format_litellm_model("gpt-4o-mini", "openai") == "gpt-4o-mini"
    
    # Assert formatting for new UI providers and alias resolution
    assert format_litellm_model("gpt-4o", "azure") == "azure/gpt-4o"
    assert format_litellm_model("grok-2", "xai") == "xai/grok-2"
    assert format_litellm_model("Llama-3-70b", "together") == "together_ai/llama-3-70b"
    assert format_litellm_model("gemini-2.5-flash", "gemini") == "gemini/gemini-2.5-flash"
    
    # Exclude client errors in pybreaker
    import litellm.exceptions
    from gateway.router import PROVIDER_BREAKERS
    breaker = PROVIDER_BREAKERS.get("google")
    assert breaker is not None
    
    # Test exclusions
    assert breaker.is_system_error(litellm.exceptions.AuthenticationError("msg", 401, "msg")) is False
    assert breaker.is_system_error(litellm.exceptions.BadRequestError("msg", 400, "msg")) is False
    assert breaker.is_system_error(litellm.exceptions.RateLimitError("msg", 429, "msg")) is False
    
    # Test system errors (should be True)
    assert breaker.is_system_error(Exception("Generic system error")) is True

@pytest.mark.asyncio
async def test_history_compression_redis():
    gateway = LLMGateway()
    messages = [
        {"role": "user", "content": "chào bạn 1" + "a" * 800},
        {"role": "assistant", "content": "hi 1" + "b" * 800},
        {"role": "user", "content": "hello 2"},
        {"role": "assistant", "content": "hi 2"},
        {"role": "user", "content": "hello 3"},
        {"role": "assistant", "content": "hi 3"},
        {"role": "user", "content": "hello 4"},
        {"role": "assistant", "content": "hi 4"},
        {"role": "user", "content": "hello 5"},
        {"role": "assistant", "content": "hi 5"}
    ]
    
    tenant_id = "test-tenant-id"
    
    # Mock Redis database
    mock_redis_db = {}
    
    async def mock_redis_get(key):
        return mock_redis_db.get(key)
        
    async def mock_redis_setex(key, ttl, value):
        mock_redis_db[key] = value
        return True
        
    # Mock LLM complete call to return a high quality summary
    mock_response = {
        "content": "Đây là tóm tắt chất lượng cao từ LLM",
        "model_used": "gemini-2.5-flash",
        "provider": "google",
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "cost_usd": 0.0001,
        "latency_ms": 150
    }
    
    with patch("gateway.router.redis_client.get", side_effect=mock_redis_get):
        with patch("gateway.router.redis_client.setex", side_effect=mock_redis_setex):
            with patch.object(gateway, "complete", return_value=mock_response) as mock_complete:
                with patch.object(gateway, "get_provider_credentials", return_value={"api_key": "mock-key"}):
                    with patch.object(gateway, "_get_cheapest_available_provider", return_value=("google", "gemini-2.5-flash")) as mock_cheapest:
                        # Cache is empty, first call should return baseline and schedule background task
                        compressed1 = await gateway.compress_history(tenant_id, messages, keep_recent=5)
                        
                        assert len(compressed1) == 6
                        assert "Tóm tắt lịch sử" in compressed1[0]["content"]
                        
                        # Wait briefly for background task to execute
                        await asyncio.sleep(0.1)
                        
                        # Verify background task selected cheapest and completed
                        mock_cheapest.assert_called_once_with(tenant_id)
                        mock_complete.assert_called_once()
                        assert len(mock_redis_db) > 0  # Summary should be cached
                        
                        # Next call should hit Redis cache and return the high-quality summary
                        compressed2 = await gateway.compress_history(tenant_id, messages, keep_recent=5)
                        assert len(compressed2) == 6
                        assert compressed2[0]["content"] == "Tóm tắt cuộc hội thoại trước đó:\nĐây là tóm tắt chất lượng cao từ LLM"

@pytest.mark.asyncio
async def test_history_compression_skipped():
    gateway = LLMGateway()
    
    # Threshold 1: messages length <= 9 (keep_recent=5 + 4) -> should be skipped
    messages1 = [
        {"role": "user", "content": "short"},
        {"role": "assistant", "content": "short"},
        {"role": "user", "content": "hello 3"},
        {"role": "assistant", "content": "hi 3"},
        {"role": "user", "content": "hello 4"},
        {"role": "assistant", "content": "hi 4"},
        {"role": "user", "content": "hello 5"},
        {"role": "assistant", "content": "hi 5"}
    ]
    compressed1 = await gateway.compress_history("d3b07384-d113-4ec2-a5d8-7e30d1774e1d", messages1, keep_recent=5)
    assert len(compressed1) == 8
    assert compressed1[0]["content"] == "short"

    # Threshold 2: messages length > 9, but older messages character length <= 1500 chars -> should be skipped
    messages2 = messages1 + [
        {"role": "user", "content": "hello 6"},
        {"role": "assistant", "content": "hi 6"}
    ]
    compressed2 = await gateway.compress_history("d3b07384-d113-4ec2-a5d8-7e30d1774e1d", messages2, keep_recent=5)
    assert len(compressed2) == 10
    assert compressed2[0]["content"] == "short"


@pytest.mark.asyncio
async def test_dynamic_cheapest_model_resolution():
    gateway = LLMGateway()
    gateway._cheapest_models_cache = {}
    
    # 1. Test LiteLLM registry parsing and dynamic caching for google
    model_google = gateway._get_cheapest_model_from_registry("google")
    assert model_google is not None
    assert "google:chat" in gateway._cheapest_models_cache
    
    # 2. Test cache hit path (must return immediately from cache dict)
    gateway._cheapest_models_cache["google:chat"] = "mocked-cheapest-gemini"
    model_cached = gateway._get_cheapest_model_from_registry("google")
    assert model_cached == "mocked-cheapest-gemini"
    
    # 3. Test _get_cheapest_available_provider fallback lookup
    tenant_id = "d3b07384-d113-4ec2-a5d8-7e30d1774e1d"
    provider, model = await gateway._get_cheapest_available_provider(tenant_id)
    assert provider is not None
    assert model is not None


@pytest.mark.asyncio
async def test_system_default_route_configs_seeding_and_fallback():
    from sqlalchemy import select
    from db.database import SessionLocal
    from db.models import SystemDefaultRouteConfig, APIKeyConfig, LLMRouteConfig
    from core.dynamic_cost import sync_system_default_configs
    
    tenant_id = str(uuid.uuid4())
    tenant_uuid = uuid.UUID(tenant_id)
    
    async with SessionLocal() as db:
        # Seed system defaults
        await sync_system_default_configs(db)
        
        # Verify DB system default configs created
        stmt = select(SystemDefaultRouteConfig).where(SystemDefaultRouteConfig.provider == "anthropic")
        res = await db.execute(stmt)
        defaults = res.scalars().all()
        assert len(defaults) > 0
        
        # Add API Key for anthropic only
        key_config = APIKeyConfig(
            tenant_id=tenant_uuid,
            provider="anthropic",
            api_key_encrypted="mock-encrypted",
            is_active=True
        )
        db.add(key_config)
        await db.commit()

    gateway = LLMGateway()
    # Resolve routing - should fall back to anthropic system defaults
    route = await gateway.get_routing(tenant_id, "chatbot")
    assert route["provider"] == "anthropic"
    assert "claude" in route["primary_model"].lower()
    
    # Cleanup
    async with SessionLocal() as db:
        await db.execute(APIKeyConfig.__table__.delete().where(APIKeyConfig.tenant_id == tenant_uuid))
        await db.commit()


@pytest.mark.asyncio
async def test_active_verification_and_deprecation_fallback():
    from core.metrics import ai_core_model_deprecation_fallbacks_total
    
    gateway = LLMGateway()
    tenant_id = "d3b07384-d113-4ec2-a5d8-7e30d1774e1d"
    
    # gpt-deprecated-model is NOT in litellm registry
    resolved = gateway.resolve_active_default_model(tenant_id, "openai", "gpt-deprecated-model")
    
    # Should resolve to cheapest active openai model dynamically
    assert resolved == gateway._get_cheapest_model_from_registry("openai")
    
    # Check that model is verified active when it exists
    resolved_active = gateway.resolve_active_default_model(tenant_id, "openai", "gpt-4o")
    assert resolved_active == "gpt-4o"


@pytest.mark.asyncio
async def test_dynamic_cost_registry_sync():
    from core.dynamic_cost import sync_dynamic_cost_registry, CACHE_FILE_PATH
    import shutil
    
    # Remove existing cache if exists
    if os.path.exists(CACHE_FILE_PATH):
        os.remove(CACHE_FILE_PATH)
        
    # Execute sync
    await sync_dynamic_cost_registry()
    
    # Verify cache file created
    assert os.path.exists(CACHE_FILE_PATH)
    
    with open(CACHE_FILE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "gpt-4o-mini" in data


# --- Task 18 Tests ---
@pytest.mark.asyncio
async def test_auto_create_routes_on_first_api_key():
    from httpx import AsyncClient, ASGITransport
    from main import app
    from db.database import SessionLocal
    from db.models import APIKeyConfig, LLMRouteConfig, SystemDefaultRouteConfig
    from core.dynamic_cost import sync_system_default_configs
    
    tenant_id = str(uuid.uuid4())
    
    async with SessionLocal() as db:
        # Seed system default configs first
        await sync_system_default_configs(db)
        
        # Clean existing keys/routes for this tenant
        await db.execute(APIKeyConfig.__table__.delete().where(APIKeyConfig.tenant_id == uuid.UUID(tenant_id)))
        await db.execute(LLMRouteConfig.__table__.delete().where(LLMRouteConfig.tenant_id == uuid.UUID(tenant_id)))
        await db.commit()
        
    # POST key payload
    payload = {
        "provider": "openai",
        "api_key": "sk-test-openai-key-first-key",
        "api_base": "https://api.openai.com/v1",
        "is_active": True
    }
    
    headers = {"X-Tenant-ID": tenant_id}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/configs/keys", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Check if 7 routes were automatically created
    async with SessionLocal() as db:
        res = await db.execute(
            select(LLMRouteConfig).where(LLMRouteConfig.tenant_id == uuid.UUID(tenant_id))
        )
        routes = res.scalars().all()
        assert len(routes) == 7
        use_cases = [r.use_case for r in routes]
        assert "chatbot" in use_cases
        assert "content_generation" in use_cases
        
        # Cleanup
        await db.execute(APIKeyConfig.__table__.delete().where(APIKeyConfig.tenant_id == uuid.UUID(tenant_id)))
        await db.execute(LLMRouteConfig.__table__.delete().where(LLMRouteConfig.tenant_id == uuid.UUID(tenant_id)))
        await db.commit()

@pytest.mark.asyncio
async def test_auto_create_routes_on_first_api_key_sync():
    from core.sync_listener import fetch_and_sync_config
    from db.database import SessionLocal
    from db.models import APIKeyConfig, LLMRouteConfig, SystemDefaultRouteConfig
    from core.dynamic_cost import sync_system_default_configs
    
    tenant_id = str(uuid.uuid4())
    tenant_uuid = uuid.UUID(tenant_id)
    
    async with SessionLocal() as db:
        # Seed system defaults
        await sync_system_default_configs(db)
        # Clean existing keys/routes
        await db.execute(APIKeyConfig.__table__.delete().where(APIKeyConfig.tenant_id == tenant_uuid))
        await db.execute(LLMRouteConfig.__table__.delete().where(LLMRouteConfig.tenant_id == tenant_uuid))
        await db.commit()
        
    # Mock Tenant Config Service response with an API key
    mock_config = {
        "api_keys": {
            "openai": {
                "api_key_encrypted": "encrypted-mock-key",
                "is_active": True,
                "api_base": "https://api.openai.com/v1"
            }
        },
        "llm_model_routing": {}  # Empty routing configuration to trigger default routes
    }
    
    with patch("core.sync_listener.httpx.AsyncClient") as mock_client_class:
        mock_client = mock_client_class.return_value.__aenter__.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_config
        mock_client.get.return_value = mock_response
        
        # Execute sync listener
        await fetch_and_sync_config(tenant_id)
        
    # Verify routes were automatically created in DB
    async with SessionLocal() as db:
        res = await db.execute(
            select(LLMRouteConfig).where(LLMRouteConfig.tenant_id == tenant_uuid)
        )
        routes = res.scalars().all()
        assert len(routes) == 7
        
        # Cleanup
        await db.execute(APIKeyConfig.__table__.delete().where(APIKeyConfig.tenant_id == tenant_uuid))
        await db.execute(LLMRouteConfig.__table__.delete().where(LLMRouteConfig.tenant_id == tenant_uuid))
        await db.commit()

@pytest.mark.asyncio
async def test_dynamic_models_endpoint():
    from httpx import AsyncClient, ASGITransport
    from main import app
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    models = data["models"]
    assert len(models) > 0
    
    # Verify models have required structure
    for m in models:
        assert "id" in m
        assert "provider" in m
        
    # Verify local defaults are included
    model_ids = [m["id"] for m in models]
    assert "qwen2.5-coder" in model_ids
    assert "llama3" in model_ids


# ===========================================================================
# NEW TESTS — Covering FIX-1A, FIX-1B, FIX-2, FIX-6
# ===========================================================================

@pytest.mark.asyncio
async def test_compress_history_gemini_fix_leading_tool_call():
    """
    FIX-1A (CRITICAL): Verifies that after compression, the first non-system message
    is NEVER 'assistant+tool_calls'. This prevents Gemini INVALID_ARGUMENT 400.

    History (10 messages, keep_recent=5):
      [0] user: long
      [1] assistant: long
      [2] user
      [3] assistant
      [4] user: "invoke tool please"       <- PASS 2 must include this
      [5] assistant: tool_calls=[call_X]   <- natural split_index=5 -> INVALID
      [6] tool: result
      [7] assistant: final answer
      [8] user
      [9] assistant
    """
    gateway = LLMGateway()
    messages = [
        {"role": "user", "content": "question A" + "a" * 800},
        {"role": "assistant", "content": "answer A" + "b" * 800},
        {"role": "user", "content": "question B"},
        {"role": "assistant", "content": "answer B"},
        {"role": "user", "content": "invoke tool please"},
        {
            "role": "assistant",
            "tool_calls": [{"id": "call_X", "type": "function", "function": {"name": "kb_search", "arguments": "{}"}}],
            "content": None,
        },
        {"role": "tool", "tool_call_id": "call_X", "name": "kb_search", "content": "search result content"},
        {"role": "assistant", "content": "Based on the results, here is the answer."},
        {"role": "user", "content": "follow up question"},
        {"role": "assistant", "content": "Sure, follow-up answer."},
    ]

    with patch("gateway.router.redis_client.get", return_value=None):
        compressed = await gateway.compress_history(
            "d3b07384-d113-4ec2-a5d8-7e30d1774e1d", messages, keep_recent=5
        )

    assert compressed[0]["role"] == "system", "First message must be system summary"
    first_non_system = next(m for m in compressed if m["role"] != "system")
    is_invalid_assistant_toolcall = (
        first_non_system.get("role") == "assistant" and bool(first_non_system.get("tool_calls"))
    )
    assert not is_invalid_assistant_toolcall, (
        f"FIX-1A FAILED: first non-system = assistant+tool_calls. "
        f"Would cause Gemini 400 INVALID_ARGUMENT. msg={first_non_system}"
    )
    assert first_non_system["role"] == "user"
    assert first_non_system["content"] == "invoke tool please"


@pytest.mark.asyncio
async def test_compress_history_gemini_fix_no_tool_calls_regression():
    """
    FIX-1A regression: When history has NO tool_calls in assistant messages,
    PASS 2 is a no-op. Compression still works: 1 summary + 5 recent messages.
    Note: A plain 'assistant' message (without tool_calls) at the start of 'recent'
    is perfectly valid for Gemini — only 'assistant+tool_calls' is the problem.
    """
    gateway = LLMGateway()
    messages = [
        {"role": "user", "content": "hello " + "a" * 800},
        {"role": "assistant", "content": "hi " + "b" * 800},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "q3"},
        {"role": "assistant", "content": "a3"},
        {"role": "user", "content": "q4"},
        {"role": "assistant", "content": "a4"},
        {"role": "user", "content": "q5"},
        {"role": "assistant", "content": "a5"},
    ]
    with patch("gateway.router.redis_client.get", return_value=None):
        compressed = await gateway.compress_history(
            "d3b07384-d113-4ec2-a5d8-7e30d1774e1d", messages, keep_recent=5
        )
    assert len(compressed) == 6
    assert compressed[0]["role"] == "system"
    # First chat message after summary: plain 'assistant' is valid for Gemini (no tool_calls)
    first_non_system = next(m for m in compressed if m["role"] != "system")
    assert not (first_non_system.get("role") == "assistant" and bool(first_non_system.get("tool_calls"))), (
        "PASS 2 should NOT block a plain assistant message (without tool_calls)"
    )


@pytest.mark.asyncio
async def test_compress_history_summary_excludes_tool_and_system_roles():
    """
    FIX-2: The baseline summary text must only include user/assistant messages.
    Tool messages (raw JSON) and system messages must be excluded.
    """
    gateway = LLMGateway()
    tool_json = '{"results": [{"url": "http://solar.com", "content": "' + "x" * 500 + '"}]}'
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "search for solar panels" + "a" * 800},
        {
            "role": "assistant",
            "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "web_search", "arguments": "{}"}}],
            "content": None,
        },
        {"role": "tool", "tool_call_id": "tc1", "name": "web_search", "content": tool_json},
        {"role": "assistant", "content": "Here is what I found."},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "q3"},
        {"role": "assistant", "content": "a3"},
        {"role": "user", "content": "q4"},
        {"role": "assistant", "content": "a4"},
        {"role": "user", "content": "q5"},
        {"role": "assistant", "content": "a5"},
    ]
    with patch("gateway.router.redis_client.get", return_value=None):
        compressed = await gateway.compress_history(
            "d3b07384-d113-4ec2-a5d8-7e30d1774e1d", messages, keep_recent=5
        )

    # Find the summary system message (different from the original system prompt)
    summary_msgs = [m for m in compressed if m["role"] == "system" and (
        "summary" in m["content"].lower() or "tóm tắt" in m["content"].lower()
    )]
    # If compression occurred, there should be a summary message
    if summary_msgs:
        summary_content = summary_msgs[0]["content"]
        assert '{"results"' not in summary_content, "FIX-2 FAILED: raw tool JSON found in summary"
        assert "- tool:" not in summary_content, "FIX-2 FAILED: 'tool' role found in summary"


@pytest.mark.asyncio
async def test_chatbot_complete_injects_repetition_penalties():
    """
    FIX-6: complete(use_case='chatbot') must pass frequency_penalty=0.3
    and presence_penalty=0.1 to litellm.acompletion. Other use cases must not.
    """
    gateway = LLMGateway()
    captured = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "OK"
        resp.choices[0].message.tool_calls = None
        resp.usage.prompt_tokens = 10
        resp.usage.completion_tokens = 5
        resp.cache_hit = False
        return resp

    msgs = [{"role": "user", "content": "Hello"}]

    with patch("gateway.router.acompletion", side_effect=fake_acompletion):
        with patch.object(gateway, "get_routing", return_value={
            "primary_model": "gpt-4o-mini", "fallback_model": "gpt-4o-mini",
            "provider": "openai", "fallback_provider": "openai",
            "temperature": 0.7, "max_tokens": 500,
        }):
            with patch.object(gateway, "compress_history", return_value=msgs):
                with patch.object(gateway, "get_provider_credentials", return_value={"api_key": "sk-x"}):
                    with patch.object(gateway, "resolve_active_default_model", side_effect=lambda t, p, m: m):
                        await gateway.complete("tenant", "chatbot", msgs)

    assert captured.get("frequency_penalty") == 0.3, "FIX-6: frequency_penalty must be 0.3 for chatbot"
    assert captured.get("presence_penalty") == 0.1, "FIX-6: presence_penalty must be 0.1 for chatbot"


@pytest.mark.asyncio
async def test_non_chatbot_complete_no_repetition_penalties():
    """FIX-6 negative: summarization/content_generation must NOT have repetition penalties."""
    gateway = LLMGateway()
    captured = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "Done"
        resp.choices[0].message.tool_calls = None
        resp.usage.prompt_tokens = 10
        resp.usage.completion_tokens = 5
        resp.cache_hit = False
        return resp

    msgs = [{"role": "user", "content": "Summarize this."}]

    with patch("gateway.router.acompletion", side_effect=fake_acompletion):
        with patch.object(gateway, "get_routing", return_value={
            "primary_model": "gpt-4o-mini", "fallback_model": "gpt-4o-mini",
            "provider": "openai", "fallback_provider": "openai",
            "temperature": 0.3, "max_tokens": 300,
        }):
            with patch.object(gateway, "get_provider_credentials", return_value={"api_key": "sk-x"}):
                with patch.object(gateway, "resolve_active_default_model", side_effect=lambda t, p, m: m):
                    await gateway.complete("tenant", "summarization", msgs)

    assert "frequency_penalty" not in captured, "Non-chatbot must NOT have frequency_penalty"
    assert "presence_penalty" not in captured, "Non-chatbot must NOT have presence_penalty"


def test_modify_params_enabled_on_init():
    """
    FIX-1B: LLMGateway.__init__ must set litellm.modify_params = True.
    This enables LiteLLM auto-sanitization of invalid message sequences.
    """
    import litellm as _litellm
    _litellm.modify_params = False  # reset first
    _ = LLMGateway()
    assert _litellm.modify_params is True, (
        "FIX-1B FAILED: litellm.modify_params must be True after LLMGateway()"
    )


@pytest.mark.asyncio
async def test_compress_history_only_system_messages():
    """Edge case: All messages are system -> no chat_messages -> return as-is."""
    gateway = LLMGateway()
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "system", "content": "Focus on solar energy topics."},
    ]
    compressed = await gateway.compress_history("test-tenant", messages, keep_recent=5)
    assert len(compressed) == 2
    assert all(m["role"] == "system" for m in compressed)


@pytest.mark.asyncio
async def test_compress_history_combined_passes_no_orphans():
    """
    FIX-1A + PASS 1 combined: Multiple tool rounds at boundary.
    After compression, recent slice must have: no leading assistant+tool_calls,
    and no orphaned tool results.
    """
    gateway = LLMGateway()
    messages = [
        {"role": "user", "content": "A" * 400},           # [0]
        {"role": "assistant", "content": "B" * 400},       # [1]
        {"role": "user", "content": "round 2"},            # [2]
        {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "s", "arguments": "{}"}}], "content": None},  # [3]
        {"role": "tool", "tool_call_id": "c1", "name": "s", "content": "r1"},  # [4]
        {"role": "assistant", "content": "ans2"},          # [5]
        {"role": "user", "content": "round 3"},            # [6]
        {"role": "assistant", "tool_calls": [{"id": "c2", "type": "function", "function": {"name": "k", "arguments": "{}"}}], "content": None},  # [7]
        {"role": "tool", "tool_call_id": "c2", "name": "k", "content": "r2"},  # [8]
        {"role": "assistant", "content": "ans3"},          # [9]
        {"role": "user", "content": "q10"},                # [10]
        {"role": "assistant", "content": "a10"},           # [11]
        {"role": "user", "content": "q11"},                # [12]
        {"role": "assistant", "content": "a11"},           # [13]
    ]
    with patch("gateway.router.redis_client.get", return_value=None):
        compressed = await gateway.compress_history("test-tenant", messages, keep_recent=6)

    first_non_system = next(m for m in compressed if m["role"] != "system")
    assert not (first_non_system.get("role") == "assistant" and bool(first_non_system.get("tool_calls"))), (
        f"Combined test FAILED: first non-system is assistant+tool_calls: {first_non_system}"
    )

    # No orphaned tool results
    tc_ids_in_slice = set()
    for m in compressed:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                tc_ids_in_slice.add(tc.get("id"))
    for m in compressed:
        if m.get("role") == "tool":
            assert m.get("tool_call_id") in tc_ids_in_slice, (
                f"Orphaned tool message found: tool_call_id={m.get('tool_call_id')}"
            )


@pytest.mark.asyncio
async def test_active_verification_allows_new_and_custom_models():
    gateway = LLMGateway()
    tenant_id = "d3b07384-d113-4ec2-a5d8-7e30d1774e1d"
    
    # 1. Cohere new model with year suffix
    resolved_cohere = gateway.resolve_active_default_model(tenant_id, "cohere", "command-a-plus-05-2026")
    assert resolved_cohere == "command-a-plus-05-2026"
    
    # 2. OpenAI fine-tuned model
    resolved_ft = gateway.resolve_active_default_model(tenant_id, "openai", "ft:gpt-4o-mini:solavie-v1")
    assert resolved_ft == "ft:gpt-4o-mini:solavie-v1"


@pytest.mark.asyncio
async def test_cohere_cheapest_model_resolution():
    gateway = LLMGateway()
    gateway._cheapest_models_cache = {}
    
    cheapest = gateway._get_cheapest_model_from_registry("cohere")
    assert cheapest is not None
    assert cheapest != "cohere-default"
    assert "command-r" in cheapest or "command-light" in cheapest or "command-a" in cheapest


def test_provider_adapters_basic_sanitization():
    from gateway.providers.factory import ProviderFactory

    # 1. Cohere Adapter should remove 'name' field
    cohere_adapter = ProviderFactory.get_adapter("cohere")
    payload = {
        "messages": [
            {"role": "user", "content": "hello", "name": "user1"},
            {"role": "tool", "tool_call_id": "123", "name": "search", "content": "result"}
        ],
        "temperature": 0.5
    }
    sanitized = cohere_adapter.sanitize_payload(payload)
    for m in sanitized["messages"]:
        assert "name" not in m
    # Original payload must remain untouched (deep copy verification)
    assert "name" in payload["messages"][0]

    # 2. Perplexity Adapter should remove 'tools'
    perp_adapter = ProviderFactory.get_adapter("perplexity")
    payload_perp = {
        "messages": [{"role": "user", "content": "hello"}],
        "tools": [{"type": "function"}]
    }
    sanitized_perp = perp_adapter.sanitize_payload(payload_perp)
    assert "tools" not in sanitized_perp
    assert "tools" in payload_perp

    # 3. Mistral Adapter should clean None values in tools
    mistral_adapter = ProviderFactory.get_adapter("mistral")
    payload_mistral = {
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "test",
                    "description": None,
                    "parameters": {
                        "type": "object",
                        "properties": {"arg": {"type": "string", "description": None}}
                    }
                }
            }
        ]
    }
    sanitized_mistral = mistral_adapter.sanitize_payload(payload_mistral)
    assert "description" not in sanitized_mistral["tools"][0]["function"]
    assert "description" not in sanitized_mistral["tools"][0]["function"]["parameters"]["properties"]["arg"]
