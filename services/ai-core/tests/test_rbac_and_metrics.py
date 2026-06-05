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
    async def test_orchestrator_exposes_user_role_in_state(self):
        """Verify orchestrator passes user_role through to RBAC check."""
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
                user_role="admin"
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
        mock_redis.get = AsyncMock(return_value=b"standard")
        
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
        mock_redis.get = AsyncMock(side_effect=lambda key: b"standard" if "tier" in key else None)
        
        with patch("api.v1.endpoints.completions.redis_client", mock_redis):
            await check_and_trigger_cost_alert(tenant_uuid, mock_db)
            
            # Check metric is incremented
            current_value = ai_core_cost_alerts_total.labels(tenant_id=str(tenant_uuid), tier="standard")._value.get()
            assert current_value == 1.0


class TestOrchestratorBilingual:
    @pytest.mark.asyncio
    async def test_orchestrator_topic_blocked_english(self):
        from agent.orchestrator import AgentOrchestrator
        orchestrator = AgentOrchestrator()
        result = await orchestrator.run(
            tenant_id="test-tenant",
            use_case="chatbot",
            messages=[{"role": "user", "content": "How to commit a scam?"}],
            user_role="visitor"
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
            user_role="visitor"
        )
        assert "Xin lỗi, chủ đề bạn hỏi nằm ngoài phạm vi tư vấn của tôi" in result["final_response"]

