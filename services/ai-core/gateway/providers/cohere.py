import copy
from typing import Dict, Any
from gateway.providers.base import BaseProviderAdapter

class CohereAdapter(BaseProviderAdapter):
    """
    Adapter for Cohere API.
    Removes the forbidden 'name' parameter to prevent 422 error on V2 API.
    Parses Cohere's unique citation metadata.
    """

    def sanitize_payload(self, call_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Removes 'name' parameter from all messages in the payload.
        """
        sanitized = copy.deepcopy(call_kwargs)
        if "messages" in sanitized:
            for m in sanitized["messages"]:
                if isinstance(m, dict) and "name" in m:
                    del m["name"]
        return sanitized

    def parse_response(self, response: Any, model_used: str) -> Dict[str, Any]:
        """
        Extracts citations list from Cohere's response metadata.
        """
        citations = []
        meta = getattr(response, "meta", None)
        raw_citations = (
            getattr(response, "citations", None)
            or (getattr(meta, "citations", None) if meta else None)
            or []
        )
        for c in raw_citations:
            if isinstance(c, dict):
                citations.append({
                    "start": c.get("start"),
                    "end": c.get("end"),
                    "text": c.get("text"),
                    "source": c.get("document_ids", [])
                })
            else:
                citations.append({
                    "start": getattr(c, "start", None),
                    "end": getattr(c, "end", None),
                    "text": getattr(c, "text", None),
                    "source": getattr(c, "document_ids", [])
                })
        return {"citations": citations}
