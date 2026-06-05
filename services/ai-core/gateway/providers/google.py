import logging
from typing import Dict, Any
from gateway.providers.base import BaseProviderAdapter

logger = logging.getLogger("solavie.ai_core.providers.google")

class GeminiAdapter(BaseProviderAdapter):
    """
    Adapter for Google Gemini API.
    Injects default safety settings and configures context caching for inputs > 32k tokens.
    """

    def sanitize_payload(self, call_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        AC 14.2 — Google Safety Settings & Context Caching.
        """
        sanitized = call_kwargs.copy()
        
        # Inject standard safety settings
        sanitized["safety_settings"] = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
        ]

        # Context caching validation
        messages = sanitized.get("messages", [])
        msg_text_len = sum(len(str(m.get("content", ""))) for m in messages)
        estimated_tokens = msg_text_len // 4  # rough 4-char-per-token estimate

        GEMINI_CONTEXT_CACHE_THRESHOLD = 32_000
        if estimated_tokens > GEMINI_CONTEXT_CACHE_THRESHOLD:
            logger.info(
                f"Gemini context caching activated: {estimated_tokens} tokens > {GEMINI_CONTEXT_CACHE_THRESHOLD} threshold"
            )
            sanitized.setdefault("extra_body", {})
            sanitized["extra_body"]["cachedContent"] = {
                "ttl": "300s"
            }
            
        return sanitized

    def parse_response(self, response: Any, model_used: str) -> Dict[str, Any]:
        return {"citations": []}
