import logging
import time
import json
import uuid
import hashlib
from typing import List, Dict, Any, AsyncGenerator
import pybreaker
import litellm
from litellm import acompletion, completion_cost
from sqlalchemy import select

from core.config import settings
from core.crypto import decrypt_key
from core.circuit_breaker import call_async
from core.redis_client import redis_client
from db.database import SessionLocal
from db.models import LLMRouteConfig, APIKeyConfig

logger = logging.getLogger(__name__)

# Static fallback routing configuration
DEFAULT_MODEL_ROUTING = {
    "chatbot": {
        "primary_model": "gpt-4o-mini",
        "fallback_model": "claude-3-haiku-20240307",
        "max_tokens": 300,
        "temperature": 0.3,
        "provider": "openai",
        "fallback_provider": "anthropic"
    },
    "content_generation": {
        "primary_model": "claude-3-5-sonnet-20241022",
        "fallback_model": "gpt-4o",
        "max_tokens": 1500,
        "temperature": 0.7,
        "provider": "anthropic",
        "fallback_provider": "openai"
    },
    "sentiment": {
        "primary_model": "gpt-4o-mini",
        "fallback_model": "claude-3-haiku-20240307",
        "max_tokens": 50,
        "temperature": 0.0,
        "provider": "openai",
        "fallback_provider": "anthropic"
    },
    "summarization": {
        "primary_model": "gpt-4o-mini",
        "fallback_model": "claude-3-haiku-20240307",
        "max_tokens": 200,
        "temperature": 0.2,
        "provider": "openai",
        "fallback_provider": "anthropic"
    },
    "classification": {
        "primary_model": "gpt-4o-mini",
        "fallback_model": "claude-3-haiku-20240307",
        "max_tokens": 50,
        "temperature": 0.0,
        "provider": "openai",
        "fallback_provider": "anthropic"
    }
}

# Dynamic Circuit Breaker per provider
# Opens if a provider fails 5 times in 30 seconds, resets after 60 seconds.
PROVIDER_BREAKERS = {
    "openai": pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60.0),
    "anthropic": pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60.0),
    "google": pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60.0),
    "local": pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60.0),
}

def safe_uuid(val: Any) -> uuid.UUID | None:
    """Safely convert any value to UUID."""
    if not val:
        return None
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except ValueError:
        return None

class LLMGateway:
    def __init__(self):
        litellm.telemetry = False
        # Set base keys in litellm for static configurations
        if settings.OPENAI_API_KEY:
            litellm.api_key = settings.OPENAI_API_KEY
        if settings.ANTHROPIC_API_KEY:
            litellm.anthropic_key = settings.ANTHROPIC_API_KEY

    async def get_routing(self, tenant_id: str, use_case: str) -> Dict[str, Any]:
        """Gets routing configuration from Redis cache, database, or fallback map."""
        tenant_uuid = safe_uuid(tenant_id)
        if not tenant_uuid:
            return DEFAULT_MODEL_ROUTING.get(use_case, DEFAULT_MODEL_ROUTING["chatbot"])

        cache_key = f"{tenant_uuid}:config:llm_model_routing:{use_case}"
        
        # 1. Check Redis Cache
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.error(f"Redis get routing error: {e}")

        # 2. Query Postgres
        try:
            async with SessionLocal() as db:
                stmt = select(LLMRouteConfig).where(
                    LLMRouteConfig.tenant_id == tenant_uuid,
                    LLMRouteConfig.use_case == use_case,
                    LLMRouteConfig.is_active == True
                )
                result = await db.execute(stmt)
                config = result.scalar_one_or_none()
                
                if config:
                    route_dict = {
                        "primary_model": config.primary_model,
                        "fallback_model": config.fallback_model,
                        "provider": config.provider,
                        "fallback_provider": config.fallback_provider,
                        "temperature": float(config.temperature),
                        "max_tokens": config.max_tokens
                    }
                    # Save to Redis Cache (TTL 5 minutes)
                    await redis_client.setex(cache_key, 300, json.dumps(route_dict))
                    return route_dict
        except Exception as e:
            logger.error(f"Database query routing error: {e}")

        # 3. Fallback to default static routing map
        fallback_route = DEFAULT_MODEL_ROUTING.get(use_case, DEFAULT_MODEL_ROUTING["chatbot"])
        try:
            await redis_client.setex(cache_key, 300, json.dumps(fallback_route))
        except Exception:
            pass
        return fallback_route

    # ── Sentinel UUID representing system-level (global) config ──
    SYSTEM_TENANT_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")

    async def get_provider_credentials(self, tenant_id: str, provider: str) -> Dict[str, Any]:
        """
        Fetches LLM API Keys with hierarchical precedence:
          1. BYOK — Tenant-specific key  (tenant_id == <actual tenant>)
          2. System Config — Shared key   (tenant_id == 00000000-…-000000000000)
          3. Env fallback — .env / settings

        Cache keys are tenant-scoped to prevent cross-tenant leakage.
        """
        tenant_uuid = safe_uuid(tenant_id)

        # ─── 1. BYOK: tenant-specific credential ───
        if tenant_uuid and tenant_uuid != self.SYSTEM_TENANT_UUID:
            result = await self._lookup_credentials(tenant_uuid, provider)
            if result:
                return result

        # ─── 2. System Config: shared credential ───
        sys_result = await self._lookup_credentials(self.SYSTEM_TENANT_UUID, provider)
        if sys_result:
            return sys_result

        # ─── 3. Env fallback ───
        api_key = None
        if provider == "openai":
            api_key = settings.OPENAI_API_KEY
        elif provider == "anthropic":
            api_key = settings.ANTHROPIC_API_KEY

        return {"api_key": api_key, "api_base": None}

    async def _lookup_credentials(
        self, tenant_uuid: uuid.UUID, provider: str
    ) -> Dict[str, Any] | None:
        """
        Internal helper: look up credentials from Redis cache then Postgres
        for a specific (tenant_uuid, provider) pair.
        Returns dict with api_key/api_base, or None if not found.
        """
        cache_key = f"{tenant_uuid}:config:api_keys:{provider}"

        # Check Redis Cache
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                cached_data = json.loads(cached)
                decrypted = decrypt_key(cached_data.get("api_key_encrypted"))
                return {"api_key": decrypted, "api_base": cached_data.get("api_base")}
        except Exception as e:
            logger.error(f"Redis get credentials error for {cache_key}: {e}")

        # Query Postgres
        try:
            async with SessionLocal() as db:
                stmt = select(APIKeyConfig).where(
                    APIKeyConfig.tenant_id == tenant_uuid,
                    APIKeyConfig.provider == provider,
                    APIKeyConfig.is_active == True
                )
                result = await db.execute(stmt)
                config = result.scalar_one_or_none()

                if config:
                    cache_dict = {
                        "api_key_encrypted": config.api_key_encrypted,
                        "api_base": config.api_base
                    }
                    await redis_client.setex(cache_key, 300, json.dumps(cache_dict))
                    decrypted = decrypt_key(config.api_key_encrypted)
                    return {"api_key": decrypted, "api_base": config.api_base}
        except Exception as e:
            logger.error(f"Database query credentials error for {cache_key}: {e}")

        return None

    def compress_history(self, messages: List[Dict[str, Any]], keep_recent: int = 5) -> List[Dict[str, Any]]:
        """Compress older chat history to save tokens."""
        if len(messages) <= keep_recent:
            return messages
            
        recent = messages[-keep_recent:]
        older = messages[:-keep_recent]
        
        # Summarize older messages
        summary_text = "Background summary of older messages:\n"
        for m in older:
            role = m.get("role", "user")
            content = m.get("content", "")
            summary_text += f"- {role}: {content[:100]}\n"
            
        # Return summary system prompt + recent messages
        return [{"role": "system", "content": summary_text}] + recent

    def optimize_context(self, messages: List[Dict[str, Any]], max_context_chars: int = 3200) -> List[Dict[str, Any]]:
        """Optimizes context documents within messages to avoid token blowup."""
        optimized = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "context" and len(content) > max_context_chars:
                content = content[:max_context_chars//2] + "\n...[TRUNCATED FOR TOKEN OPTIMIZATION]...\n" + content[-max_context_chars//2:]
            optimized.append({"role": role, "content": content})
        return optimized

    async def complete(
        self,
        tenant_id: str,
        use_case: str,
        messages: List[Dict[str, Any]],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        model_override: str | None = None,
        tools: List[Dict[str, Any]] | None = None
    ) -> Dict[str, Any]:
        """Sends chat completion using routing and failover with optional tool support and pybreaker."""
        route = await self.get_routing(tenant_id, use_case)
        model = model_override or route["primary_model"]
        fallback_model = route["fallback_model"]
        
        # Format messages
        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)
        
        # Apply token optimization
        formatted_messages = self.compress_history(formatted_messages)
        formatted_messages = self.optimize_context(formatted_messages)
        
        # Max tokens and temperature
        max_tok = max_tokens or route["max_tokens"]
        temp = temperature if temperature is not None else route["temperature"]
        
        start_time = time.time()
        is_fallback_used = False
        model_used = model
        
        # Determine providers
        primary_provider = route["provider"]
        fallback_provider = route["fallback_provider"]
        
        # Get credentials dynamically (BYOK → System → Env)
        primary_creds = await self.get_provider_credentials(tenant_id, primary_provider)
        fallback_creds = await self.get_provider_credentials(tenant_id, fallback_provider)
        
        # Set up kwargs for litellm
        kwargs = {
            "model": model,
            "messages": formatted_messages,
            "max_tokens": max_tok,
            "temperature": temp,
            "timeout": 10.0
        }
        if tools:
            kwargs["tools"] = tools

        # Helper to execute acompletion with dynamic keys
        async def call_llm(model_name: str, creds: Dict[str, Any]) -> Any:
            call_kwargs = kwargs.copy()
            call_kwargs["model"] = model_name
            if creds.get("api_key"):
                call_kwargs["api_key"] = creds["api_key"]
            if creds.get("api_base"):
                call_kwargs["api_base"] = creds["api_base"]
            return await acompletion(**call_kwargs)

        response = None
        # 1. Execute Primary call under primary provider's Circuit Breaker
        breaker = PROVIDER_BREAKERS.get(primary_provider, PROVIDER_BREAKERS["openai"])
        try:
            response = await call_async(breaker, call_llm, model, primary_creds)
            model_used = model
        except Exception as e:
            logger.warning(
                f"Primary model/provider {model} ({primary_provider}) failed or circuit is open for use case {use_case} on tenant {tenant_id}: {str(e)}. "
                f"Falling back to {fallback_model} ({fallback_provider})..."
            )
            is_fallback_used = True

        # 2. If primary failed, execute Fallback call under fallback provider's Circuit Breaker
        if is_fallback_used:
            fallback_breaker = PROVIDER_BREAKERS.get(fallback_provider, PROVIDER_BREAKERS["anthropic"])
            try:
                # Wrap with 15s timeout for fallback
                response = await call_async(fallback_breaker, call_llm, fallback_model, fallback_creds)
                model_used = fallback_model
            except Exception as e:
                logger.error(f"Fallback model {fallback_model} ({fallback_provider}) also failed: {e}")
                raise e
            
        latency = int((time.time() - start_time) * 1000)
        
        # Calculate cost
        try:
            cost = completion_cost(completion_response=response)
        except Exception:
            cost = 0.0001
            
        prompt_tokens = response.usage.prompt_tokens if hasattr(response, "usage") else 0
        completion_tokens = response.usage.completion_tokens if hasattr(response, "usage") else 0
        
        choice_message = response.choices[0].message
        content = getattr(choice_message, "content", None)
        tool_calls = getattr(choice_message, "tool_calls", None)
        
        # Convert tool_calls to dict format if present for serializability
        tool_calls_list = []
        if tool_calls:
            for tc in tool_calls:
                tc_dict = {
                    "id": getattr(tc, "id", None),
                    "type": getattr(tc, "type", "function"),
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                tool_calls_list.append(tc_dict)
        
        return {
            "content": content,
            "tool_calls": tool_calls_list if tool_calls_list else None,
            "model_used": model_used,
            "provider": primary_provider if not is_fallback_used else fallback_provider,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost,
            "latency_ms": latency,
            "cache_hit": response.get("cache_hit", False),
            "is_fallback": is_fallback_used
        }
