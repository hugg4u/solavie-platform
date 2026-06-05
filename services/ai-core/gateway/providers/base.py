from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseProviderAdapter(ABC):
    """
    Abstract Base Class for LLM Provider Adapters.
    Encapsulates parameter sanitization and response parsing logic.
    """

    @abstractmethod
    def sanitize_payload(self, call_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize and configure API parameters specifically for this provider before calling LiteLLM.
        """
        pass

    @abstractmethod
    def parse_response(self, response: Any, model_used: str) -> Dict[str, Any]:
        """
        Parse and extract provider-specific response metadata (e.g. citations, reasoning).
        """
        pass
