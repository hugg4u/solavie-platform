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
    compressed = await gateway.compress_history("d3b07384-d113-4ec2-a5d8-7e30d1774e1d", messages, keep_recent=5)
    assert len(compressed) == 6  # 1 summary message + 5 recent messages
    assert compressed[0]["role"] == "system"
    assert "Background summary" in compressed[0]["content"]
    assert compressed[1]["content"] == "hi 3"

@pytest.mark.asyncio
async def test_context_optimization():
    gateway = LLMGateway()
    long_content = "a" * 5000
    messages = [
        {"role": "context", "content": long_content},
        {"role": "user", "content": "hi"}
    ]
    optimized = gateway.optimize_context(messages, max_context_chars=1000)
    assert len(optimized) == 2
    assert "[TRUNCATED FOR TOKEN OPTIMIZATION]" in optimized[0]["content"]
    assert len(optimized[0]["content"]) < 2000

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
                        assert "Background summary" in compressed1[0]["content"]
                        
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
    assert "google" in gateway._cheapest_models_cache
    
    # 2. Test cache hit path (must return immediately from cache dict)
    gateway._cheapest_models_cache["google"] = "mocked-cheapest-gemini"
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
    
    # Check if 5 routes were automatically created
    async with SessionLocal() as db:
        res = await db.execute(
            select(LLMRouteConfig).where(LLMRouteConfig.tenant_id == uuid.UUID(tenant_id))
        )
        routes = res.scalars().all()
        assert len(routes) == 5
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
        assert len(routes) == 5
        
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



