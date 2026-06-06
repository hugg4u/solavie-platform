import os
import json
import logging
import pybreaker
import litellm
from core.config import settings

logger = logging.getLogger("solavie.ai_core.providers")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "providers_config.json")

# Load configuration from centralized JSON config file
try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        _config = json.load(f)
except Exception as e:
    logger.critical(f"Failed to load providers_config.json: {e}")
    _config = {"provider_priority": [], "aliases": {}, "providers": {}}

PROVIDER_PRIORITY = _config.get("provider_priority", [])
PROVIDER_ALIASES = _config.get("aliases", {})
PROVIDERS_REGISTRY = _config.get("providers", {})

# Use case default parameters
USE_CASE_PARAMS = {
    "chatbot": {
        "temperature": 0.3,
        "max_tokens": 300,
        "default_provider": "openai"
    },
    "content_generation": {
        "temperature": 0.7,
        "max_tokens": 1500,
        "default_provider": "anthropic"
    },
    "sentiment": {
        "temperature": 0.0,
        "max_tokens": 50,
        "default_provider": "openai"
    },
    "summarization": {
        "temperature": 0.2,
        "max_tokens": 200,
        "default_provider": "openai"
    },
    "classification": {
        "temperature": 0.0,
        "max_tokens": 50,
        "default_provider": "openai"
    },
    "utility": {
        "temperature": 0.3,
        "max_tokens": 1000,
        "default_provider": "openai"
    },
    "embedding": {
        "temperature": 0.0,
        "max_tokens": 0,
        "default_provider": "openai"
    }
}


# Exclude client-side/configuration errors from tripping the Circuit Breaker
EXCLUDED_EXCEPTIONS = [
    litellm.exceptions.BadRequestError,
    litellm.exceptions.InvalidRequestError,
    litellm.exceptions.PermissionDeniedError,
    litellm.exceptions.NotFoundError,
    litellm.exceptions.ContextWindowExceededError,
    litellm.exceptions.RateLimitError,
    litellm.exceptions.AuthenticationError,
]

# Instantiate Circuit Breakers dynamically from JSON configuration properties
PROVIDER_BREAKERS = {}
for p_name, p_info in PROVIDERS_REGISTRY.items():
    PROVIDER_BREAKERS[p_name] = pybreaker.CircuitBreaker(
        fail_max=p_info.get("fail_max", 5),
        reset_timeout=p_info.get("reset_timeout", 60.0),
        exclude=EXCLUDED_EXCEPTIONS
    )

# Map Circuit Breaker instances for provider aliases
for alias, target in PROVIDER_ALIASES.items():
    if target in PROVIDER_BREAKERS:
        PROVIDER_BREAKERS[alias] = PROVIDER_BREAKERS[target]

def get_provider_by_model(model_name: str) -> str:
    """Dynamically resolves provider name based on model name keywords configured in JSON."""
    if not model_name:
        return "local"
    name = model_name.lower()
    
    for provider, info in PROVIDERS_REGISTRY.items():
        for keyword in info.get("keywords", []):
            if keyword in name:
                return provider
    return "local"

