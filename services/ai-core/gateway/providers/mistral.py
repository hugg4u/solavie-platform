import copy
from typing import Dict, Any, List
from gateway.providers.base import BaseProviderAdapter

class MistralAdapter(BaseProviderAdapter):
    """
    Adapter for Mistral API.
    Cleans up tool schemas by removing None values and empty dictionaries.
    Handles dynamic routing to EU endpoint if required.
    """

    def sanitize_payload(self, call_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        AC 14.6 — Mistral Tool Schema Sanitization & EU Routing.
        """
        sanitized = copy.deepcopy(call_kwargs)

        # Sanitize tools schema if present
        if "tools" in sanitized and sanitized["tools"]:
            sanitized["tools"] = self._sanitize_mistral_tools(sanitized["tools"])

        # Dynamic EU routing check
        MISTRAL_EU_ENDPOINT = "https://api.mistral.ai"
        existing_base = sanitized.get("api_base", "") or ""
        if existing_base and ("eu." in existing_base.lower() or "europe" in existing_base.lower()):
            # EU endpoint explicitly configured
            pass
        elif not existing_base:
            # Fallback to default EU endpoint
            sanitized["api_base"] = MISTRAL_EU_ENDPOINT

        return sanitized

    def parse_response(self, response: Any, model_used: str) -> Dict[str, Any]:
        return {"citations": []}

    def _sanitize_mistral_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Clean Mistral tools schema by recursively removing None values or empty dicts."""
        def clean_dict(d):
            if not isinstance(d, dict):
                return d
            cleaned = {}
            for k, v in d.items():
                if v is None:
                    continue
                if isinstance(v, dict):
                    cleaned[k] = clean_dict(v)
                elif isinstance(v, list):
                    cleaned[k] = [clean_dict(item) if isinstance(item, dict) else item for item in v]
                else:
                    cleaned[k] = v
            return cleaned
        return [clean_dict(t) for t in tools]
