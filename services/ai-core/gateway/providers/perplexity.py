from typing import Dict, Any
from gateway.providers.base import BaseProviderAdapter

class PerplexityAdapter(BaseProviderAdapter):
    """
    Adapter for Perplexity API (Sonar models).
    Excludes 'tools' parameter since Perplexity does not support function calling.
    Extracts direct search URL citations from Perplexity's response.
    """

    def sanitize_payload(self, call_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Removes 'tools' parameter to prevent client validation errors on Perplexity.
        """
        sanitized = call_kwargs.copy()
        if "tools" in sanitized:
            del sanitized["tools"]
        return sanitized

    def parse_response(self, response: Any, model_used: str) -> Dict[str, Any]:
        """
        Extracts citations from Perplexity's response.
        """
        citations = []
        direct_citations = getattr(response, "citations", None)
        if direct_citations:
            citations = list(direct_citations)
        return {"citations": citations}
