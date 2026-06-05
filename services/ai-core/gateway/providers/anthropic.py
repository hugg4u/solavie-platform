import copy
from typing import Dict, Any
from gateway.providers.base import BaseProviderAdapter

class AnthropicAdapter(BaseProviderAdapter):
    """
    Adapter for Anthropic API.
    Applies ephemeral cache control to system and context messages.
    """

    def sanitize_payload(self, call_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        AC 14.1 — Anthropic Caching:
        Injects cache_control={"type": "ephemeral"} to the last system and context messages.
        """
        cached = copy.deepcopy(call_kwargs)
        messages = cached.get("messages", [])
        if not messages:
            return cached

        system_msgs = [m for m in messages if m.get("role") == "system"]
        if system_msgs:
            system_msgs[-1]["cache_control"] = {"type": "ephemeral"}

        context_msgs = [m for m in messages if m.get("role") == "context"]
        if context_msgs:
            context_msgs[-1]["cache_control"] = {"type": "ephemeral"}

        cached["messages"] = messages
        return cached

    def parse_response(self, response: Any, model_used: str) -> Dict[str, Any]:
        return {"citations": []}
