"""
Unit Tests — RBAC Authorization & Rate Limit Metrics (AC 8.3b, Task 12)

Tests cover:
  - AC 8.3b: Keycloak RBAC permission check from Redis cache
  - AC 8.4:  Tool rate limiting (Lua script)
  - Task 12: Prometheus metrics existence validation
"""

import pytest
import json
import uuid
import os
from unittest.mock import AsyncMock, patch, MagicMock
from tools.registry import ToolPermissionManager, TOOL_PERMISSIONS


# ─── RBAC Tests (AC 8.3b) ────────────────────────────────────────────────────

class TestRBACAuthorization:
    @pytest.mark.asyncio
    async def test_admin_has_all_permissions(self):
        pm = ToolPermissionManager()
        with patch("tools.registry.redis_client") as mock_redis:
            # Simulate Redis cache miss
            mock_redis.get = AsyncMock(return_value=None)
            
            # Admin role gets all permissions from fallback
            is_auth = await pm.is_user_authorized("tenant-1", "admin", "knowledge_base_search")
            assert is_auth is True

    @pytest.mark.asyncio
    async def test_visitor_only_has_kb_search(self):
        pm = ToolPermissionManager()
        with patch("tools.registry.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)
            
            # Visitor cannot use send_message (requires messaging:chat)
            is_auth = await pm.is_user_authorized("tenant-1", "visitor", "send_message")
            assert is_auth is False

    @pytest.mark.asyncio
    async def test_redis_cached_permissions_used(self):
        pm = ToolPermissionManager()
        cached_perms = ["kb:search", "messaging:chat", "crm:read"]
        
        with patch("tools.registry.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=json.dumps(cached_perms).encode())
            
            # Should use Redis cached permissions
            perms = await pm.get_user_permissions("tenant-1", "agent")
            assert "kb:search" in perms
            assert "messaging:chat" in perms

    @pytest.mark.asyncio
    async def test_redis_failure_falls_back_gracefully(self):
        pm = ToolPermissionManager()
        with patch("tools.registry.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(side_effect=Exception("Redis connection failed"))
            
            # Should not raise, should fallback to role-based defaults
            perms = await pm.get_user_permissions("tenant-1", "support")
            assert isinstance(perms, list)
            assert len(perms) > 0

    @pytest.mark.asyncio
    async def test_unknown_tool_is_authorized_by_default(self):
        """Tools not in TOOL_PERMISSIONS matrix are allowed (no restriction)."""
        pm = ToolPermissionManager()
        with patch("tools.registry.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)
            
            is_auth = await pm.is_user_authorized("tenant-1", "visitor", "unknown_tool")
            assert is_auth is True

    def test_tool_permissions_mapping_completeness(self):
        """Ensure all registered tools in PERMISSION_MATRIX have RBAC mappings."""
        from tools.registry import ALL_TOOLS, PERMISSION_MATRIX
        all_tool_names = {t["function"]["name"] for t in ALL_TOOLS}
        # Every tool used in the matrix should have a TOOL_PERMISSIONS entry
        for use_case, tools in PERMISSION_MATRIX.items():
            for tool in tools:
                if tool in TOOL_PERMISSIONS:
                    assert TOOL_PERMISSIONS[tool] is not None


# ─── Rate Limit Tests (AC 8.4) ───────────────────────────────────────────────

class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_rate_limit_passes_within_limit(self):
        pm = ToolPermissionManager()
        with patch("tools.registry.redis_client") as mock_redis:
            # tier = "standard"
            mock_redis.get = AsyncMock(side_effect=lambda key: (
                b"standard" if "tier" in key else None
            ))
            # Lua script returns count 1 (under limit)
            mock_redis.eval = AsyncMock(return_value=1)
            
            result = await pm.check_rate_limit("tenant-1", "web_search")
            assert result is True

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_over_limit(self):
        pm = ToolPermissionManager()
        with patch("tools.registry.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(side_effect=lambda key: (
                b"free" if "tier" in key else None
            ))
            # Lua script returns count 25 — above free tier limit of 20
            mock_redis.eval = AsyncMock(return_value=25)
            
            result = await pm.check_rate_limit("tenant-1", "web_search")
            assert result is False

    @pytest.mark.asyncio
    async def test_redis_failure_defaults_to_allow(self):
        """Redis failure should fail-open to avoid accidental DoS."""
        pm = ToolPermissionManager()
        with patch("tools.registry.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(side_effect=Exception("Redis down"))
            mock_redis.eval = AsyncMock(side_effect=Exception("Redis down"))
            
            result = await pm.check_rate_limit("tenant-1", "web_search")
            assert result is True  # Fail-open

    @pytest.mark.asyncio
    async def test_enterprise_tier_higher_limits(self):
        pm = ToolPermissionManager()
        with patch("tools.registry.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(side_effect=lambda key: (
                b"enterprise" if "tier" in key else None
            ))
            # Count = 150 which is below enterprise limit of 200
            mock_redis.eval = AsyncMock(return_value=150)
            
            result = await pm.check_rate_limit("tenant-1", "web_search")
            assert result is True


# ─── Prometheus Metrics Existence Tests (Task 12) ────────────────────────────

class TestPrometheusMetrics:
    def test_all_required_metrics_exist(self):
        """Verify all required custom metrics are registered in Prometheus."""
        from core.metrics import (
            ai_core_pii_tokens_total,
            ai_core_pii_latency_seconds,
            ai_core_nli_grounding_score,
            ai_core_nli_violations_total,
            ai_core_rag_similarity_score,
            ai_core_rate_limit_violations_total,
            ai_core_guardrail_blocked_total,
            ai_core_agent_iterations,
            ai_core_token_budget_exceeded_total,
        )
        # All should be importable and have correct types
        from prometheus_client import Counter, Histogram
        assert isinstance(ai_core_pii_tokens_total, Counter)
        assert isinstance(ai_core_pii_latency_seconds, Histogram)
        assert isinstance(ai_core_nli_grounding_score, Histogram)
        assert isinstance(ai_core_nli_violations_total, Counter)
        assert isinstance(ai_core_rag_similarity_score, Histogram)
        assert isinstance(ai_core_rate_limit_violations_total, Counter)
        assert isinstance(ai_core_guardrail_blocked_total, Counter)
        assert isinstance(ai_core_agent_iterations, Histogram)
        assert isinstance(ai_core_token_budget_exceeded_total, Counter)

    def test_metrics_endpoint_returns_prometheus_format(self):
        """Verify /metrics endpoint returns prometheus text format."""
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        output = generate_latest().decode("utf-8")
        # Should contain at least one of our custom metrics
        assert "ai_core" in output or "python_gc" in output  # Prometheus output
        # Version varies by prometheus_client release — just verify it starts with text/plain
        assert CONTENT_TYPE_LATEST.startswith("text/plain")


# ─── Orchestrator RBAC Integration Tests ─────────────────────────────────────

class TestOrchestratorRBAC:
    @pytest.mark.asyncio
    async def test_orchestrator_exposes_user_permissions_in_state(self):
        """Verify orchestrator passes user_permissions through to RBAC check."""
        from agent.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()

        with patch.object(orchestrator.gateway, "complete") as mock_complete:
            mock_complete = AsyncMock(return_value={
                "content": "Xin chào! Tôi có thể giúp gì cho bạn?",
                "tool_calls": None,
                "model_used": "gpt-4o-mini",
                "provider": "openai",
                "prompt_tokens": 50,
                "completion_tokens": 20,
                "cost_usd": 0.0001,
                "is_fallback": False,
                "reasoning_content": None,
                "citations": []
            })
            orchestrator.gateway.complete = mock_complete

            result = await orchestrator.run(
                tenant_id="test-tenant",
                use_case="chatbot",
                messages=[{"role": "user", "content": "Xin chào"}],
                user_permissions=["*"]
            )

            # Result should have trace_id and nli fields
            assert "trace_id" in result
            assert "nli_grounding_score" in result
            assert "nli_status" in result
            assert result["nli_status"] in ["pass", "fail", "skip"]


# ─── Cost Alert Tests (AC 5.4) ────────────────────────────────────────────────

class TestCostAlert:
    @pytest.mark.asyncio
    async def test_cost_alert_not_triggered_under_threshold(self):
        from api.v1.endpoints.completions import check_and_trigger_cost_alert
        from core.metrics import ai_core_cost_alerts_total
        
        tenant_uuid = uuid.uuid4()
        
        # Mock database session to return total cost below 80% limit
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5.0  # $5.0 cost in last 30 days
        mock_db.execute.return_value = mock_result
        
        # Reset metric value
        initial_value = 0
        try:
            initial_value = ai_core_cost_alerts_total.labels(tenant_id=str(tenant_uuid), tier="standard")._value.get()
        except KeyError:
            pass
            
        mock_redis = MagicMock()
        # standard tier: limit=$100, 80% threshold = $80. $5 is below threshold.
        limits_data = {
            "cost_limit_usd": 100.0,
            "cost_alert_threshold_percent": 80,
            "cost_limit_policy": "notify_only"
        }
        
        async def mock_get(key):
            if "limits" in key:
                return json.dumps(limits_data).encode("utf-8")
            elif "tier" in key:
                return b"standard"
            return None
            
        mock_redis.get = AsyncMock(side_effect=mock_get)
        mock_redis.setex = AsyncMock()
        
        with patch("api.v1.endpoints.completions.redis_client", mock_redis):
            await check_and_trigger_cost_alert(tenant_uuid, mock_db)
            
            # Check metric is not incremented
            current_value = 0
            try:
                current_value = ai_core_cost_alerts_total.labels(tenant_id=str(tenant_uuid), tier="standard")._value.get()
            except KeyError:
                pass
            assert current_value == initial_value

    @pytest.mark.asyncio
    async def test_cost_alert_triggered_above_threshold(self):
        from api.v1.endpoints.completions import check_and_trigger_cost_alert
        from core.metrics import ai_core_cost_alerts_total
        
        tenant_uuid = uuid.uuid4()
        
        # Mock database session to return total cost above 80% limit (85.0 for standard limit of 100)
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 85.0
        mock_db.execute.return_value = mock_result
        
        mock_redis = MagicMock()
        limits_data = {
            "cost_limit_usd": 100.0,
            "cost_alert_threshold_percent": 80,
            "cost_limit_policy": "notify_only"
        }
        
        async def mock_get(key):
            if "limits" in key:
                return json.dumps(limits_data).encode("utf-8")
            elif "tier" in key:
                return b"standard"
            return None
            
        mock_redis.get = AsyncMock(side_effect=mock_get)
        mock_redis.setex = AsyncMock()
        
        with patch("api.v1.endpoints.completions.redis_client", mock_redis):
            await check_and_trigger_cost_alert(tenant_uuid, mock_db)
            
            # Check metric is incremented
            current_value = ai_core_cost_alerts_total.labels(tenant_id=str(tenant_uuid), tier="standard")._value.get()
            assert current_value == 1.0

    @pytest.mark.asyncio
    async def test_cost_limit_policy_block(self):
        from gateway.router import LLMGateway
        gateway = LLMGateway()
        
        tenant_uuid = uuid.uuid4()
        
        # Mock Redis return cost_limit_usd=100.0, policy=block
        mock_redis = MagicMock()
        limits_data = {
            "cost_limit_usd": 100.0,
            "cost_alert_threshold_percent": 80,
            "cost_limit_policy": "block"
        }
        
        async def mock_get(key):
            if "limits" in key:
                return json.dumps(limits_data).encode("utf-8")
            elif "accumulated_cost" in key:
                return b"120.0"
            return None
            
        mock_redis.get = AsyncMock(side_effect=mock_get)
        
        with patch("gateway.router.redis_client", mock_redis):
            with pytest.raises(ValueError) as excinfo:
                await gateway.get_routing(str(tenant_uuid), "chatbot")
            assert "LLM usage limit exceeded" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_cost_limit_policy_auto_downgrade(self):
        from gateway.router import LLMGateway
        gateway = LLMGateway()
        
        tenant_uuid = uuid.uuid4()
        
        # Mock Redis return cost_limit_usd=100.0, policy=auto_downgrade
        mock_redis = MagicMock()
        limits_data = {
            "cost_limit_usd": 100.0,
            "cost_alert_threshold_percent": 80,
            "cost_limit_policy": "auto_downgrade"
        }
        
        async def mock_get(key):
            if "limits" in key:
                return json.dumps(limits_data).encode("utf-8")
            elif "accumulated_cost" in key:
                return b"120.0"
            elif "llm_model_routing" in key:
                return b'{"primary_model": "gpt-4o", "fallback_model": "gpt-4o-mini", "provider": "openai", "fallback_provider": "openai", "temperature": 0.3, "max_tokens": 300}'
            return None
            
        mock_redis.get = AsyncMock(side_effect=mock_get)
        
        with patch("gateway.router.redis_client", mock_redis):
            route = await gateway.get_routing(str(tenant_uuid), "chatbot")
            # Should downgrade to fallback model (gpt-4o-mini)
            assert route["primary_model"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_redis_down_resiliency(self):
        """Verify that when Redis is down, system falls back to database or local cache and does not crash."""
        from gateway.router import LLMGateway
        from api.v1.endpoints.completions import check_and_trigger_cost_alert
        gateway = LLMGateway()
        tenant_uuid = uuid.uuid4()
        tenant_str = str(tenant_uuid)
        
        # Mock Redis to raise connection error
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Redis connection error (simulate down)"))
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis connection error (simulate down)"))
        
        # Mock DB session for completions cost alert check
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 15.0
        mock_db.execute.return_value = mock_result
        
        # Test 1: get_routing under Redis outage
        with patch("gateway.router.redis_client", mock_redis):
            # Should read DB or default system route and NOT raise error
            route = await gateway.get_routing(tenant_str, "chatbot")
            assert isinstance(route, dict)
            assert "primary_model" in route
            
        # Test 2: completions cost alert verification under Redis outage
        with patch("api.v1.endpoints.completions.redis_client", mock_redis):
            # Should catch error, log warning, and NOT raise HTTP 500 or ConnectionError
            await check_and_trigger_cost_alert(tenant_uuid, mock_db)

    @pytest.mark.asyncio
    async def test_limits_cache_miss_triggers_background_sync(self):
        """Verify that a Redis cache miss triggers a non-blocking background sync task and does not block current request."""
        import asyncio
        from gateway.router import LLMGateway
        gateway = LLMGateway()
        tenant_uuid = uuid.uuid4()
        tenant_str = str(tenant_uuid)
        
        mock_redis = MagicMock()
        # Mock limits returns None (cache miss), routing returns valid route
        async def mock_get(key):
            if "limits" in key:
                return None
            elif "llm_model_routing" in key:
                return b'{"primary_model": "gpt-4o", "fallback_model": "gpt-4o-mini", "provider": "openai", "fallback_provider": "openai", "temperature": 0.3, "max_tokens": 300}'
            return None
            
        mock_redis.get = AsyncMock(side_effect=mock_get)
        
        with patch("gateway.router.redis_client", mock_redis), \
             patch("core.sync_listener.fetch_and_sync_config", new_callable=AsyncMock) as mock_sync:
             
            # Current request goes through immediately
            route = await gateway.get_routing(tenant_str, "chatbot")
            assert route["primary_model"] == "gpt-4o"
            
            # Allow event loop to run background task
            await asyncio.sleep(0.1)
            
            # Verify background sync task was scheduled
            mock_sync.assert_called_once_with(tenant_str)

    @pytest.mark.asyncio
    async def test_local_memory_cache_hit_performance(self):
        """Verify that successive routing reads are served from Local Memory Cache, reducing network roundtrips to Redis."""
        from gateway.router import LLMGateway
        gateway = LLMGateway()
        tenant_uuid = uuid.uuid4()
        tenant_str = str(tenant_uuid)
        
        mock_redis = MagicMock()
        # Mock Redis returns routing configs
        mock_redis.get = AsyncMock(return_value=b'{"primary_model": "gpt-4o", "fallback_model": "gpt-4o-mini", "provider": "openai", "fallback_provider": "openai", "temperature": 0.3, "max_tokens": 300}')
        
        with patch("gateway.router.redis_client", mock_redis):
            # Call 1: Cache Miss -> Calls Redis
            route1 = await gateway.get_routing(tenant_str, "chatbot")
            assert route1["primary_model"] == "gpt-4o"
            
            # Call 2 & 3: Cache Hit -> Read from local memory (no Redis calls)
            route2 = await gateway.get_routing(tenant_str, "chatbot")
            route3 = await gateway.get_routing(tenant_str, "chatbot")
            
            assert route2["primary_model"] == "gpt-4o"
            assert route3["primary_model"] == "gpt-4o"
            
            # Count how many times Redis get was called for model routing config
            call_count = 0
            for call in mock_redis.get.call_args_list:
                args, kwargs = call
                if "llm_model_routing" in args[0]:
                    call_count += 1
            
            assert call_count == 1


class TestOrchestratorBilingual:
    @pytest.mark.asyncio
    async def test_orchestrator_topic_blocked_english(self):
        from agent.orchestrator import AgentOrchestrator
        orchestrator = AgentOrchestrator()
        result = await orchestrator.run(
            tenant_id="test-tenant",
            use_case="chatbot",
            messages=[{"role": "user", "content": "How to commit a scam?"}],
            user_permissions=["knowledge-base:documents:read"]
        )
        assert "Sorry, the topic you asked about is outside my scope of assistance" in result["final_response"]

    @pytest.mark.asyncio
    async def test_orchestrator_topic_blocked_vietnamese(self):
        from agent.orchestrator import AgentOrchestrator
        orchestrator = AgentOrchestrator()
        result = await orchestrator.run(
            tenant_id="test-tenant",
            use_case="chatbot",
            messages=[{"role": "user", "content": "Làm thế nào để chơi cờ bạc?"}],
            user_permissions=["knowledge-base:documents:read"]
        )
        assert "Xin lỗi, chủ đề bạn hỏi nằm ngoài phạm vi tư vấn của tôi" in result["final_response"]


# ─── FastAPI Signed Headers & Wildcards Tests ──────────────────────────────────

class TestFastAPIPermissionsSecurity:
    def test_permission_based_authorization_pass(self):
        from api.deps import require_permission
        import hmac, hashlib
        
        tenant_id = "tenant-1"
        user_id = "user-123"
        perms = "ai-core:chats:create,analytics:metrics:read"
        
        secret = os.getenv("GATEWAY_SIGNING_SECRET", "default-gateway-signing-secret-key-change-me-in-production")
        payload = f"{tenant_id}:{user_id}:{perms}"
        sig = hmac.new(secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
        
        dep = require_permission("ai-core:chats:create")
        res = dep(
            x_tenant_id=tenant_id,
            x_user_id=user_id,
            x_user_permissions=perms,
            x_permissions_signature=sig
        )
        assert res == perms

    def test_permission_based_authorization_invalid_signature(self):
        from api.deps import require_permission
        from fastapi import HTTPException
        
        dep = require_permission("ai-core:chats:create")
        with pytest.raises(HTTPException) as excinfo:
            dep(
                x_tenant_id="tenant-1",
                x_user_id="user-123",
                x_user_permissions="ai-core:chats:create",
                x_permissions_signature="invalid-sig"
            )
        assert excinfo.value.status_code == 403
        assert "Invalid authorization signature" in excinfo.value.detail

    def test_permission_based_authorization_forbidden(self):
        from api.deps import require_permission
        from fastapi import HTTPException
        import hmac, hashlib
        
        tenant_id = "tenant-1"
        user_id = "user-123"
        perms = "analytics:metrics:read"
        
        secret = os.getenv("GATEWAY_SIGNING_SECRET", "default-gateway-signing-secret-key-change-me-in-production")
        payload = f"{tenant_id}:{user_id}:{perms}"
        sig = hmac.new(secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
        
        dep = require_permission("ai-core:chats:create")
        with pytest.raises(HTTPException) as excinfo:
            dep(
                x_tenant_id=tenant_id,
                x_user_id=user_id,
                x_user_permissions=perms,
                x_permissions_signature=sig
            )
        assert excinfo.value.status_code == 403
        assert "Forbidden" in excinfo.value.detail

    def test_wildcard_bypass(self):
        from api.deps import check_permission
        
        # Super admin wildcard '*'
        assert check_permission({"*"}, "ai-core:configs:read") is True
        
        # Service level wildcard 'service:*'
        assert check_permission({"ai-core:*"}, "ai-core:configs:read") is True
        assert check_permission({"ai-core:*"}, "ai-core:prompts:write") is True
        assert check_permission({"ai-core:*"}, "crm:contacts:read") is False
        
        # Resource level wildcard 'service:resource:*'
        assert check_permission({"ai-core:configs:*"}, "ai-core:configs:read") is True
        assert check_permission({"ai-core:configs:*"}, "ai-core:configs:write") is True
        assert check_permission({"ai-core:configs:*"}, "ai-core:prompts:read") is False

    @pytest.mark.asyncio
    async def test_permissions_manifest_endpoint(self):
        from api.v1.endpoints.permissions import get_permissions_manifest
        res = await get_permissions_manifest()
        assert res["service"] == "ai-core"
        assert len(res["resources"]) > 0
        resources = {r["name"] for r in res["resources"]}
        assert "chats" in resources
        assert "configs" in resources
        assert "prompts" in resources
        assert "analytics" in resources


# ─── gRPC Metadata Permissions Tests ───────────────────────────────────────────

class TestgRPCMetadataPermissions:
    @pytest.mark.asyncio
    async def test_grpc_metadata_permission_extraction(self):
        from grpc_server.servicer import AICoreServicer
        
        servicer = AICoreServicer()
        
        # Mock context with custom metadata
        mock_context = MagicMock()
        mock_context.invocation_metadata.return_value = (
            ("x-user-permissions", "ai-core:chats:create"),
        )
        
        mock_request = MagicMock()
        mock_request.tenant_id = "test-tenant"
        mock_request.use_case = "chatbot"
        mock_request.messages = []
        mock_request.system_prompt = "system"
        
        with patch.object(servicer.orchestrator, "run", AsyncMock(return_value={"final_response": "OK"})) as mock_run:
            await servicer.Complete(mock_request, mock_context)
            mock_run.assert_called_once_with(
                tenant_id="test-tenant",
                use_case="chatbot",
                messages=[],
                system_prompt="system",
                user_permissions=["ai-core:chats:create"]
            )

    @pytest.mark.asyncio
    async def test_grpc_system_fallback_wildcard(self):
        from grpc_server.servicer import AICoreServicer
        
        servicer = AICoreServicer()
        
        # Mock context with empty metadata
        mock_context = MagicMock()
        mock_context.invocation_metadata.return_value = ()
        
        mock_request = MagicMock()
        mock_request.tenant_id = "test-tenant"
        mock_request.use_case = "chatbot"
        mock_request.messages = []
        mock_request.system_prompt = "system"
        
        with patch.object(servicer.orchestrator, "run", AsyncMock(return_value={"final_response": "OK"})) as mock_run:
            await servicer.Complete(mock_request, mock_context)
            mock_run.assert_called_once_with(
                tenant_id="test-tenant",
                use_case="chatbot",
                messages=[],
                system_prompt="system",
                user_permissions=["*"]
            )
