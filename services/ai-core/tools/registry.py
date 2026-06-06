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
    # ── Category 1: Information Retrieval ──
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
                    "query": {"type": "string", "description": "Web search query"},
                    "max_results": {"type": "integer", "description": "Max results to return", "default": 5},
                    "time_range": {"type": "string", "description": "Time range: day, week, month, year", "default": "month"}
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
                    "url": {"type": "string", "description": "HTTP URL link to scrape"},
                    "extract_mode": {"type": "string", "description": "Extraction mode: full, summary, main_content", "default": "main_content"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analytics_query",
            "description": "Query marketing analytics: engagement metrics, top posts, reach, and performance trends.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_type": {"type": "string", "description": "Type of metric: engagement, reach, messages, posts"},
                    "channel": {"type": "string", "description": "Social channel: facebook, zalo, tiktok, all", "default": "all"},
                    "date_range": {"type": "string", "description": "Time window: today, 7d, 30d, 90d", "default": "30d"},
                    "top_k": {"type": "integer", "description": "Number of top items to return", "default": 5}
                },
                "required": ["metric_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "contact_lookup",
            "description": "Look up customer information, profile details, interaction history, and lead score.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string", "description": "Unique contact identifier in CRM (optional)"},
                    "external_id": {"type": "string", "description": "Platform specific user ID (optional)"},
                    "channel": {"type": "string", "description": "Integration platform channel (optional)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_social_trends",
            "description": "Get trending topics, popular hashtags, and viral ideas on social media platforms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "description": "Target platform: facebook, tiktok, all", "default": "all"},
                    "country": {"type": "string", "description": "Country code (e.g. VN, US)", "default": "VN"},
                    "category": {"type": "string", "description": "Category theme (optional)"}
                },
                "required": ["platform"]
            }
        }
    },
    # ── Category 2: Actions ──
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send an automated response or notification to a client's conversation channel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string", "description": "Unique identifier of the chat conversation"},
                    "content": {"type": "string", "description": "Message text to send"},
                    "content_type": {"type": "string", "description": "Type of content: text, image", "default": "text"}
                },
                "required": ["conversation_id", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "handoff_to_agent",
            "description": "Transfer conversation to human agent immediately with description and priority level.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string", "description": "Unique identifier of the chat conversation"},
                    "reason": {"type": "string", "description": "Explanation why handoff is needed"},
                    "priority": {"type": "string", "description": "Handoff priority: normal, high, critical", "default": "normal"}
                },
                "required": ["conversation_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tag_contact",
            "description": "Add tags to a customer contact profile in CRM for segmentation and tracking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string", "description": "CRM contact identifier"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Array of tags to append"
                    }
                },
                "required": ["contact_id", "tags"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_schedule",
            "description": "Schedule a social media post for publishing at a specific target time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "post_id": {"type": "string", "description": "Unique post identifier"},
                    "channel_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Target publishing social channels"
                    },
                    "scheduled_at": {"type": "string", "description": "Target date time in ISO8601 format"},
                    "timezone": {"type": "string", "description": "Local timezone override", "default": "Asia/Ho_Chi_Minh"}
                },
                "required": ["post_id", "channel_ids", "scheduled_at"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "hide_comment",
            "description": "Hide a spam, abusive, or inappropriate comment on a social post.",
            "parameters": {
                "type": "object",
                "properties": {
                    "comment_id": {"type": "string", "description": "Comment ID to hide"},
                    "reason": {"type": "string", "description": "Reason details for audit trail"}
                },
                "required": ["comment_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_notification",
            "description": "Send a workspace alert or notification to a specific team member.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "Target employee identifier"},
                    "title": {"type": "string", "description": "Alert title"},
                    "body": {"type": "string", "description": "Notification details body"},
                    "priority": {"type": "string", "description": "Priority: low, normal, high, critical", "default": "normal"}
                },
                "required": ["user_id", "title", "body"]
            }
        }
    },
    # ── Category 3: Content Creation ──
    {
        "type": "function",
        "function": {
            "name": "generate_content",
            "description": "Generate social media content draft using AI models with custom brand guidelines context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Main post theme or topic description"},
                    "platform": {"type": "string", "description": "Social media platform targets"},
                    "audience": {"type": "string", "description": "Target reader/customer audience group"},
                    "tone": {"type": "string", "description": "Content tone: professional, friendly, casual", "default": "professional"},
                    "include_web_research": {"type": "boolean", "description": "Enable web search integration to inject current information", "default": False}
                },
                "required": ["topic", "platform", "audience"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "adapt_content",
            "description": "Adapt existing content text for optimization in a different social network format.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Source text content"},
                    "target_platform": {"type": "string", "description": "Target social platform"},
                    "max_length": {"type": "integer", "description": "Optional max characters constraint"}
                },
                "required": ["content", "target_platform"]
            }
        }
    },
    # ── Category 4: Data Processing ──
    {
        "type": "function",
        "function": {
            "name": "embed_text",
            "description": "Convert raw text inputs into vector embedding representations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "texts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of texts to embed"
                    },
                    "dimensions": {"type": "integer", "description": "Vector output dimension sizing", "default": 512}
                },
                "required": ["texts"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "summarize",
            "description": "Summarize long documents or conversations into concise key points or paragraphs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Source text input"},
                    "max_length": {"type": "integer", "description": "Maximum tokens size for summary output", "default": 150},
                    "style": {"type": "string", "description": "Style format: bullet_points, paragraph, key_facts", "default": "bullet_points"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "translate",
            "description": "Translate text across languages using AI engine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Source content to translate"},
                    "source_language": {"type": "string", "description": "Source language code or 'auto'", "default": "auto"},
                    "target_language": {"type": "string", "description": "Target language code (e.g. vi, en)"}
                },
                "required": ["text", "target_language"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_sentiment",
            "description": "Analyze text input to categorize sentiment type and score.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Input text to evaluate"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_lead_score",
            "description": "Calculate behavior-driven lead score metrics for CRM contacts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string", "description": "Contact identifier"},
                    "behavior_data": {
                        "type": "object",
                        "description": "Behavior properties: message frequency, page visits, email opens"
                    }
                },
                "required": ["contact_id", "behavior_data"]
            }
        }
    }
]

# ─── Use-Case Permission Matrix (AC 8.3 / Spec matching) ──────────────────────
PERMISSION_MATRIX = {
    "chatbot": [
        "knowledge_base_search",
        "contact_lookup",
        "send_message",
        "handoff_to_agent",
        "tag_contact",
        "analyze_sentiment",
        "translate",
        "summarize"
    ],
    "content_generation": [
        "knowledge_base_search",
        "web_search",
        "fetch_url",
        "analytics_query",
        "get_social_trends",
        "generate_content",
        "adapt_content",
        "translate"
    ],
    "comment_management": [
        "knowledge_base_search",
        "analyze_sentiment",
        "hide_comment",
        "send_notification"
    ],
    "lead_scoring": [
        "contact_lookup",
        "analytics_query",
        "calculate_lead_score",
        "tag_contact",
        "send_notification"
    ],
    "analytics_insights": [
        "analytics_query",
        "summarize",
        "web_search"
    ],
    # Fallback/compatibility aliases
    "summarization": ["knowledge_base_search", "summarize"],
    "sentiment": ["analyze_sentiment"],
    "classification": []
}

# ─── RBAC Tool Permissions (service:resource:action) (AC 8.3b) ───────────────
# Maps tool name → required Keycloak scope code (Global Permission Spec)
TOOL_PERMISSIONS = {
    "knowledge_base_search": "knowledge-base:documents:read",
    "web_search": "knowledge-base:documents:read",
    "fetch_url": "knowledge-base:documents:read",
    "analytics_query": "analytics:metrics:read",
    "contact_lookup": "crm:contacts:read",
    "get_social_trends": "knowledge-base:documents:read",
    "send_message": "messaging:conversations:chat",
    "handoff_to_agent": "messaging:conversations:chat",
    "tag_contact": "crm:contacts:update",
    "create_schedule": "scheduler:schedules:create",
    "hide_comment": "comment-manager:comments:update",
    "send_notification": "notification:notifications:send",
    "generate_content": "knowledge-base:documents:read",
    "adapt_content": "knowledge-base:documents:read",
    "embed_text": "knowledge-base:documents:read",
    "summarize": "knowledge-base:documents:read",
    "translate": "knowledge-base:documents:read",
    "analyze_sentiment": "knowledge-base:documents:read",
    "calculate_lead_score": "crm:contacts:update"
}

# ─── Baseline Rate Limits per Tier (AC 8.4) ──────────────────────────────────
# Overridable at runtime via Tenant Config Service updating Redis key `tier:{tier}:limits`
BASELINE_TIER_LIMITS = {
    "free": {
        "knowledge_base_search": 100,
        "web_search": 20,
        "fetch_url": 5,
        "analytics_query": 10,
        "contact_lookup": 50,
        "get_social_trends": 10,
        "send_message": 50,
        "handoff_to_agent": 5,
        "tag_contact": 50,
        "create_schedule": 5,
        "hide_comment": 10,
        "send_notification": 50,
        "generate_content": 5,
        "adapt_content": 10,
        "embed_text": 100,
        "summarize": 100,
        "translate": 100,
        "analyze_sentiment": 100,
        "calculate_lead_score": 50
    },
    "standard": {
        "knowledge_base_search": 500,
        "web_search": 50,
        "fetch_url": 30,
        "analytics_query": 50,
        "contact_lookup": 200,
        "get_social_trends": 50,
        "send_message": 100,
        "handoff_to_agent": 20,
        "tag_contact": 200,
        "create_schedule": 30,
        "hide_comment": 50,
        "send_notification": 200,
        "generate_content": 20,
        "adapt_content": 50,
        "embed_text": 500,
        "summarize": 500,
        "translate": 500,
        "analyze_sentiment": 500,
        "calculate_lead_score": 200
    },
    "enterprise": {
        "knowledge_base_search": 5000,
        "web_search": 200,
        "fetch_url": 100,
        "analytics_query": 500,
        "contact_lookup": 2000,
        "get_social_trends": 200,
        "send_message": 200,
        "handoff_to_agent": 100,
        "tag_contact": 1000,
        "create_schedule": 200,
        "hide_comment": 200,
        "send_notification": 1000,
        "generate_content": 100,
        "adapt_content": 200,
        "embed_text": 5000,
        "summarize": 5000,
        "translate": 5000,
        "analyze_sentiment": 5000,
        "calculate_lead_score": 1000
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
        if role_norm == "admin":
            return ["*"]
        elif role_norm in ["manager", "standard_user"]:
            return [
                "knowledge-base:documents:read",
                "messaging:conversations:chat",
                "crm:contacts:read",
                "crm:contacts:update",
                "scheduler:schedules:create",
                "comment-manager:comments:update",
                "notification:notifications:send",
                "analytics:metrics:read"
            ]
        elif role_norm in ["agent", "support"]:
            return [
                "knowledge-base:documents:read",
                "messaging:conversations:chat"
            ]
        return ["knowledge-base:documents:read"]  # Minimum visitor permission

    async def is_user_authorized(self, tenant_id: str, user_role: str, tool_name: str) -> bool:
        """
        Dynamic RBAC check: verify user role has required module:action permission (AC 8.3b).
        Reads from Redis key: {tenant_id}:permissions:{user_role}
        """
        required_perm = TOOL_PERMISSIONS.get(tool_name)
        if not required_perm:
            return True  # No RBAC restriction for this tool

        user_perms = await self.get_user_permissions(tenant_id, user_role)
        from api.deps import check_permission
        return check_permission(set(user_perms), required_perm)

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
