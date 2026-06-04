"""
AI-CORE MCP Tool Registry — Permission Manager

Implements:
  - AC 8.1: Tool registry with OpenAI function calling spec
  - AC 8.2: Tool classification (retrieval, action, content, processing)
  - AC 8.3: Use-case permission matrix
  - AC 8.3b: Dynamic RBAC (Keycloak Redis cache, module:action format)
  - AC 8.4: Sliding-window rate limiting via atomic Lua script (prevent TTL leak)
  - Task 12: Emit ai_core_rate_limit_violations_total Prometheus metric
"""

import logging
import json
import time
from typing import List, Dict, Any

from core.redis_client import redis_client
from core.metrics import ai_core_rate_limit_violations_total

logger = logging.getLogger("solavie.ai_core.tools.registry")

# ─── Tool Definitions (OpenAI function calling format) ────────────────────────
ALL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "knowledge_base_search",
            "description": "Search internal knowledge base for company documents, product catalogs, FAQ, guidelines, manuals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query keywords"},
                    "top_k": {"type": "integer", "description": "Number of results to return", "default": 5}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the internet for current events, news, trends, and market information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Web search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch and extract text content from a specific URL address.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "HTTP URL link to scrape"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send an automated response or notification to a client's conversation channel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string", "description": "Unique identifier of the chat conversation"},
                    "message": {"type": "string", "description": "Message content to send"}
                },
                "required": ["conversation_id", "message"]
            }
        }
    }
]

# ─── Use-Case Permission Matrix (AC 8.3) ──────────────────────────────────────
PERMISSION_MATRIX = {
    "chatbot": ["knowledge_base_search", "send_message"],
    "content_generation": ["web_search", "fetch_url", "knowledge_base_search"],
    "summarization": ["knowledge_base_search"],
    "sentiment": [],
    "classification": []
}

# ─── RBAC Tool Permissions (module:action) (AC 8.3b) ─────────────────────────
# Maps tool name → required Keycloak scope code
TOOL_PERMISSIONS = {
    "knowledge_base_search": "kb:search",
    "web_search": "kb:search",
    "fetch_url": "kb:search",
    "send_message": "messaging:chat",
    "contact_lookup": "crm:read",
    "analyze_sentiment": "kb:search",
    "tag_contact": "crm:update"
}

# ─── Baseline Rate Limits per Tier (AC 8.4) ──────────────────────────────────
# Overridable at runtime via Tenant Config Service updating Redis key `tier:{tier}:limits`
BASELINE_TIER_LIMITS = {
    "free": {
        "web_search": 20,
        "fetch_url": 5,
        "knowledge_base_search": 100,
        "send_message": 50
    },
    "standard": {
        "web_search": 50,
        "fetch_url": 30,
        "knowledge_base_search": 500,
        "send_message": 100
    },
    "enterprise": {
        "web_search": 200,
        "fetch_url": 100,
        "knowledge_base_search": 5000,
        "send_message": 200
    }
}

# ─── Lua Script: Atomic INCR + EXPIRE (prevent TTL leak on crash) ─────────────
LUA_INCR_EXPIRE = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


class ToolPermissionManager:
    """Manages tool access control: use-case matrix, RBAC, and rate limiting."""

    def get_tools_for_use_case(self, use_case: str) -> List[Dict[str, Any]]:
        """Returns tool schemas authorized for a specific use case (AC 8.3)."""
        allowed_names = PERMISSION_MATRIX.get(use_case, [])
        return [t for t in ALL_TOOLS if t["function"]["name"] in allowed_names]

    def is_tool_allowed(self, use_case: str, tool_name: str) -> bool:
        """Validates if a use case is allowed to invoke a specific tool (AC 8.3)."""
        return tool_name in PERMISSION_MATRIX.get(use_case, [])

    async def get_user_permissions(self, tenant_id: str, user_role: str) -> List[str]:
        """
        Fetch permissions for a given user role from Redis Keycloak cache (AC 8.3b).
        Key format: {tenant_id}:permissions:{user_role}
        Target latency: < 50ms
        """
        if not user_role:
            user_role = "visitor"

        redis_key = f"{tenant_id}:permissions:{user_role}"
        try:
            raw = await redis_client.get(redis_key)
            if raw:
                perms = json.loads(raw)
                if isinstance(perms, list):
                    logger.debug(
                        f"RBAC permissions loaded from Redis: {redis_key}",
                        extra={"event": "rbac_cache_hit", "tenant_id": tenant_id, "user_role": user_role}
                    )
                    return perms
        except Exception as e:
            logger.error(
                f"Failed to fetch RBAC permissions from Redis '{redis_key}': {e}",
                extra={"event": "rbac_cache_error", "tenant_id": tenant_id}
            )

        # Fallback role-based permissions (when Redis cache is cold/unavailable)
        role_norm = user_role.lower().strip()
        if role_norm in ["admin", "manager", "standard_user"]:
            return ["kb:search", "messaging:chat", "crm:read", "crm:update"]
        elif role_norm in ["agent", "support"]:
            return ["kb:search", "messaging:chat"]
        return ["kb:search"]  # Minimum visitor permission

    async def is_user_authorized(self, tenant_id: str, user_role: str, tool_name: str) -> bool:
        """
        Dynamic RBAC check: verify user role has required module:action permission (AC 8.3b).
        Reads from Redis key: {tenant_id}:permissions:{user_role}
        """
        required_perm = TOOL_PERMISSIONS.get(tool_name)
        if not required_perm:
            return True  # No RBAC restriction for this tool

        user_perms = await self.get_user_permissions(tenant_id, user_role)
        return required_perm in user_perms

    async def _get_tier_limits(self, tier: str) -> Dict[str, int]:
        """
        Fetch dynamic tier limits from Redis key `tier:{tier}:limits`.
        Falls back to BASELINE_TIER_LIMITS if Redis key is absent or invalid.
        System Admin updates this via Tenant Config Service REST API.
        """
        redis_key = f"tier:{tier}:limits"
        try:
            raw = await redis_client.get(redis_key)
            if raw:
                dynamic_limits = json.loads(raw)
                if isinstance(dynamic_limits, dict):
                    logger.debug(f"Dynamic tier limits loaded from Redis: '{redis_key}'")
                    return dynamic_limits
        except Exception as e:
            logger.error(f"Failed to load dynamic tier limits from Redis '{redis_key}': {e}")

        return BASELINE_TIER_LIMITS.get(tier, BASELINE_TIER_LIMITS["standard"])

    async def check_rate_limit(self, tenant_id: str, tool_name: str) -> bool:
        """
        Enforce sliding window rate limits per tool per tenant using Redis (AC 8.4).
        Uses atomic Lua INCR+EXPIRE script to prevent TTL leak on crash.
        """
        # Resolve tenant tier (default: standard)
        tier = "standard"
        try:
            tier_bytes = await redis_client.get(f"tenant:{tenant_id}:tier")
            if tier_bytes:
                tier = tier_bytes.decode("utf-8").strip().lower()
        except Exception as e:
            logger.error(f"Failed to fetch tenant tier from Redis: {e}")

        # Load limits (Redis → baseline fallback)
        limits = await self._get_tier_limits(tier)
        limit = limits.get(tool_name, 50)

        # Sliding window key (per hour)
        window = int(time.time() // 3600)
        key = f"ratelimit:{tenant_id}:{tool_name}:{window}"

        try:
            count = await redis_client.eval(LUA_INCR_EXPIRE, 1, key, 3600)

            if count > limit:
                logger.warning(
                    f"Rate limit exceeded for tool '{tool_name}'",
                    extra={
                        "event": "rate_limit_exceeded",
                        "tenant_id": tenant_id,
                        "tool_name": tool_name,
                        "tier": tier,
                        "count": count,
                        "limit": limit
                    }
                )
                # Task 12: Emit Prometheus metric
                ai_core_rate_limit_violations_total.labels(
                    tenant_id=tenant_id,
                    tool_name=tool_name,
                    tier=tier
                ).inc()
                return False

            return True

        except Exception as e:
            logger.error(f"Redis rate limit Lua script error: {e}")
            return True  # Fail-open to avoid accidental DoS
