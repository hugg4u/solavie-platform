import logging
import json
import time
from typing import List, Dict, Any

from core.config import settings
from core.redis_client import redis_client

logger = logging.getLogger(__name__)

# Available tools in the system conforming to OpenAI function calling specifications
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

# Permission Matrix: mapping usecase to allowed tool names
PERMISSION_MATRIX = {
    "chatbot": ["knowledge_base_search", "send_message"],
    "content_generation": ["web_search", "fetch_url", "knowledge_base_search"],
    "summarization": ["knowledge_base_search"],
    "sentiment": [],
    "classification": []
}

# Baseline fallback rate limits — used only when Redis `tier:{tier}:limits` is absent.
# System Admin can override these at runtime via Tenant Config Service.
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

class ToolPermissionManager:
    def get_tools_for_use_case(self, use_case: str) -> List[Dict[str, Any]]:
        """Returns tool schemas authorized for a specific use case."""
        allowed_names = PERMISSION_MATRIX.get(use_case, [])
        return [t for t in ALL_TOOLS if t["function"]["name"] in allowed_names]

    def is_tool_allowed(self, use_case: str, tool_name: str) -> bool:
        """Validates if a use case is allowed to invoke a specific tool."""
        return tool_name in PERMISSION_MATRIX.get(use_case, [])

    async def _get_tier_limits(self, tier: str) -> Dict[str, int]:
        """
        Fetch dynamic tier limits from Redis key ``tier:{tier}:limits``.
        Falls back to BASELINE_TIER_LIMITS if Redis key does not exist or is invalid.

        The Redis value is expected to be a JSON object like:
            {"web_search": 80, "fetch_url": 40, ...}
        System Admin updates this key via Tenant Config Service REST API.
        """
        redis_key = f"tier:{tier}:limits"
        try:
            raw = await redis_client.get(redis_key)
            if raw:
                dynamic_limits = json.loads(raw)
                if isinstance(dynamic_limits, dict):
                    logger.debug(f"Loaded dynamic tier limits from Redis key '{redis_key}'")
                    return dynamic_limits
        except Exception as e:
            logger.error(f"Failed to load dynamic tier limits from Redis key '{redis_key}': {e}")

        # Fallback to baseline
        return BASELINE_TIER_LIMITS.get(tier, BASELINE_TIER_LIMITS["standard"])

    async def check_rate_limit(self, tenant_id: str, tool_name: str) -> bool:
        """
        Enforce sliding window token bucket rate limits per tool per tenant using Redis,
        dynamically querying and applying limits based on the tenant's subscription tier.
        """
        # Determine tenant subscription tier from Redis (default to standard)
        tier = "standard"
        try:
            tier_bytes = await redis_client.get(f"tenant:{tenant_id}:tier")
            if tier_bytes:
                tier = tier_bytes.decode("utf-8").strip().lower()
        except Exception as e:
            logger.error(f"Failed to fetch tenant tier from Redis: {e}")

        # Load dynamic limits (Redis first, baseline fallback)
        limits = await self._get_tier_limits(tier)
        limit = limits.get(tool_name, 50)

        # Sliding window hourly key
        window = int(time.time() // 3600)
        key = f"ratelimit:{tenant_id}:{tool_name}:{window}"

        try:
            # Atomic increment
            count = await redis_client.incr(key)
            if count == 1:
                # Set TTL to 1 hour
                await redis_client.expire(key, 3600)

            if count > limit:
                logger.warning(f"Rate limit exceeded for tenant {tenant_id} on tool {tool_name} (Tier: {tier}, {count}/{limit})")
                return False
            return True
        except Exception as e:
            logger.error(f"Redis rate limit check error: {e}")
            return True  # Fallback to allow if Redis has an issue

