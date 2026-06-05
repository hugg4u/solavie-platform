import copy
from typing import Dict, Any
from gateway.providers.base import BaseProviderAdapter

class OpenAIAdapter(BaseProviderAdapter):
    """
    Adapter for OpenAI API and compatible models (DeepSeek, Groq, local models, etc.).
    Applies automatic prompt caching configurations.
    """

    def sanitize_payload(self, call_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        AC 14.1 — OpenAI Prompt Caching:
        Reorders messages to place system instructions first and adds X-Cache-Hint.
        """
        cached = copy.deepcopy(call_kwargs)
        messages = cached.get("messages", [])

        # Reorder: ensure system message is first (acts as cached prefix)
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]
        if system_msgs:
            cached["messages"] = system_msgs + non_system

        # Signal OpenAI caching readiness
        cached.setdefault("extra_headers", {})
        cached["extra_headers"]["X-Cache-Hint"] = "prompt-caching-enabled"
        return cached

    def parse_response(self, response: Any, model_used: str) -> Dict[str, Any]:
        """
        OpenAI response parsing contains no citations by default.
        """
        return {"citations": []}
