from typing import Dict, Any
from gateway.providers.openai import OpenAIAdapter

class DeepSeekAdapter(OpenAIAdapter):
    """
    Adapter for DeepSeek API.
    AC 14.3: Sets a fast timeout of 5.0s to allow quick failover under high congestion.
    """

    def sanitize_payload(self, call_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        # Apply standard OpenAI prompt caching first
        sanitized = super().sanitize_payload(call_kwargs)
        # Apply DeepSeek-specific fast timeout
        sanitized["timeout"] = 5.0
        return sanitized
