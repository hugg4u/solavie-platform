from typing import Dict
from gateway.providers.base import BaseProviderAdapter
from gateway.providers.openai import OpenAIAdapter
from gateway.providers.deepseek import DeepSeekAdapter
from gateway.providers.anthropic import AnthropicAdapter
from gateway.providers.google import GeminiAdapter
from gateway.providers.cohere import CohereAdapter
from gateway.providers.perplexity import PerplexityAdapter
from gateway.providers.mistral import MistralAdapter

class ProviderFactory:
    """
    Factory for LLM Provider Adapters.
    Uses lazy-initialization and caching.
    """
    _adapters: Dict[str, BaseProviderAdapter] = {}

    @classmethod
    def get_adapter(cls, provider_name: str) -> BaseProviderAdapter:
        name = provider_name.strip().lower()
        if name not in cls._adapters:
            # Resolve provider name aliases
            from core.providers import PROVIDER_ALIASES
            normalized_name = PROVIDER_ALIASES.get(name, name)
            
            if normalized_name == "cohere":
                cls._adapters[name] = CohereAdapter()
            elif normalized_name == "perplexity":
                cls._adapters[name] = PerplexityAdapter()
            elif normalized_name in ("google", "gemini"):
                cls._adapters[name] = GeminiAdapter()
            elif normalized_name == "anthropic":
                cls._adapters[name] = AnthropicAdapter()
            elif normalized_name == "deepseek":
                cls._adapters[name] = DeepSeekAdapter()
            elif normalized_name == "mistral":
                cls._adapters[name] = MistralAdapter()
            else:
                # Default adapter for OpenAI, Groq, Together, Local models, Qwen, etc.
                cls._adapters[name] = OpenAIAdapter()
                
        return cls._adapters[name]
