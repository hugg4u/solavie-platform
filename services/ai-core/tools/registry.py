import logging
from typing import List, Dict, Any
import redis

from core.config import settings

logger = logging.getLogger(__name__)

# Available tools in the system
ALL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "knowledge_base_search",
            "description": "Search internal knowledge base for company documents, guidelines, manuals, and FAQs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query keywords"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the internet for current events, news, and market information.",
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
    "content_generation": ["web_search", "knowledge_base_search"],
    "summarization": ["knowledge_base_search"],
    "sentiment": [],
    "classification": []
}

class ToolPermissionManager:
    def __init__(self):
        try:
            self.redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}. Rate limiting will be bypassed.")
            self.redis_client = None

    def get_tools_for_use_case(self, use_case: str) -> List[Dict[str, Any]]:
        """Returns tool schemas authorized for a specific use case."""
        allowed_names = PERMISSION_MATRIX.get(use_case, [])
        return [t for t in ALL_TOOLS if t["function"]["name"] in allowed_names]

    def is_tool_allowed(self, use_case: str, tool_name: str) -> bool:
        """Validates if a use case is allowed to invoke a specific tool."""
        return tool_name in PERMISSION_MATRIX.get(use_case, [])

    def check_rate_limit(self, tenant_id: str, tool_name: str) -> bool:
        """
        Enforce rate limits per tool per tenant using Redis.
        Limit: 50 calls per hour per tenant for all tools, or 3 per request.
        """
        if not self.redis_client:
            return True
            
        key = f"rate_limit:{tenant_id}:{tool_name}"
        try:
            # Check hourly rate limit
            current_count = self.redis_client.get(key)
            if current_count and int(current_count) >= 50:
                logger.warning(f"Rate limit exceeded for tenant {tenant_id} on tool {tool_name}")
                return False
                
            # Increment and set TTL if new
            pipe = self.redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, 3600, nx=True)  # Expires in 1 hour
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Redis rate limit check error: {e}")
            return True  # Fallback to allow if Redis has an issue
