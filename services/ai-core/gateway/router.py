import os
import logging
import time
import json
import uuid
import hashlib
import asyncio
from typing import List, Dict, Any, AsyncGenerator
import pybreaker
import litellm
from litellm import acompletion, completion_cost
from sqlalchemy import select

from gateway.providers.factory import ProviderFactory
from core.config import settings
from core.crypto import decrypt_key
from core.circuit_breaker import call_async
from core.redis_client import redis_client
from db.database import SessionLocal
from db.models import LLMRouteConfig, APIKeyConfig, SystemDefaultRouteConfig
from core.utils import is_vietnamese

logger = logging.getLogger(__name__)

from core.providers import (
    PROVIDER_PRIORITY,
    PROVIDER_BREAKERS,
    USE_CASE_PARAMS,
    get_provider_by_model
)


# Dynamically construct DEFAULT_MODEL_ROUTING at module load time
DEFAULT_MODEL_ROUTING = {}

def init_default_model_routing():
    global DEFAULT_MODEL_ROUTING
    
    # Try to load local cache file on module load to populate LiteLLM registry immediately
    CACHE_FILE_PATH = "storage/model_prices_cache.json"
    if os.path.exists(CACHE_FILE_PATH):
        try:
            with open(CACHE_FILE_PATH, "r", encoding="utf-8") as f:
                pricing_data = json.load(f)
            litellm.model_cost = pricing_data
            logger.info("Pre-loaded LiteLLM pricing registry from local cache file on startup.")
        except Exception as cache_err:
            logger.error(f"Failed to pre-load cached pricing file: {cache_err}")

    # Find cheapest model in LiteLLM registry for each default provider and mode
    pricing_registry = getattr(litellm, "model_cost", getattr(litellm, "model_prices_and_context_window", {}))
    
    def get_cheapest(provider: str, mode: str = "chat") -> str:
        cheapest_model = None
        min_cost = float('inf')
        
        if provider == "local":
            target_providers = {"local", "ollama"}
        elif provider == "cohere":
            target_providers = {"cohere", "cohere_chat"}
        else:
            target_providers = {provider}
        
        for m_name, info in pricing_registry.items():
            if not isinstance(info, dict):
                continue
            model_provider = info.get("litellm_provider", "").lower() or info.get("provider", "").lower()
            
            # Map aliases dynamically
            if model_provider == "gemini" and "google" in target_providers:
                model_provider = "google"
            elif model_provider == "cohere_chat" and "cohere" in target_providers:
                model_provider = "cohere"
                
            if model_provider in target_providers and info.get("mode") == mode:
                input_cost = info.get("input_cost_per_token", float('inf'))
                if 0 < input_cost < min_cost:
                    min_cost = input_cost
                    cheapest_model = m_name
                    
        if cheapest_model:
            return cheapest_model
        return f"{provider}-default" if mode == "chat" else "text-embedding-3-small"

    for uc, uc_info in USE_CASE_PARAMS.items():
        prov = uc_info["default_provider"]
        mode = "embedding" if uc == "embedding" else "chat"
        cheapest_model = get_cheapest(prov, mode)
        DEFAULT_MODEL_ROUTING[uc] = {
            "primary_model": cheapest_model,
            "fallback_model": cheapest_model,
            "max_tokens": uc_info["max_tokens"],
            "temperature": uc_info["temperature"],
            "provider": prov,
            "fallback_provider": prov
        }

init_default_model_routing()

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

def format_litellm_model(model_name: str, provider: str) -> str:
    """Format model name with provider prefix if required by LiteLLM."""
    if not model_name:
        return model_name
    
    # Normalize model name: strip, lowercase, replace spaces with hyphens
    normalized_name = model_name.strip().lower().replace(" ", "-")
    
    if "/" in normalized_name:
        return normalized_name
        
    # Standardize provider name
    prov = provider.strip().lower()
    
    # Resolve aliases using central configuration
    from core.providers import PROVIDER_ALIASES
    prov = PROVIDER_ALIASES.get(prov, prov)
    
    if prov == "google":
        # Google provider uses gemini/ prefix in LiteLLM
        return f"gemini/{normalized_name}"
    elif prov in ["deepseek", "cohere", "groq", "together_ai", "perplexity", "mistral", "openrouter", "vertex_ai", "gemini", "azure", "xai"]:
        return f"{prov}/{normalized_name}"
        
    return normalized_name

class LLMGateway:
    _cheapest_models_cache = {}

    def __init__(self):
        litellm.telemetry = False
        # AC FIX-1B: Enable automatic message sanitization for all providers.
        # LiteLLM will auto-repair invalid turn ordering (e.g., consecutive assistant messages,
        # tool responses without a preceding tool call) before sending to any provider.
        litellm.modify_params = True
        if settings.ENVIRONMENT == "development":
            litellm._turn_on_debug()


    def _is_model_in_registry(self, model_name: str, provider: str) -> bool:
        """Checks if a model name is active/registered in the LiteLLM registry."""
        prov = provider.strip().lower()
        if prov == "local":
            return True
            
        pricing_registry = getattr(litellm, "model_cost", getattr(litellm, "model_prices_and_context_window", {}))
        if model_name in pricing_registry:
            return True
            
        formatted = format_litellm_model(model_name, provider)
        if formatted in pricing_registry:
            return True
            
        # Allow fine-tuned or custom deployment names, or brand new models with year suffixes
        import re
        normalized_name = model_name.strip().lower()
        if (
            normalized_name.startswith("ft:") or 
            ":ft:" in normalized_name or 
            "fine-tuned" in normalized_name or
            "finetuned" in normalized_name or
            normalized_name.startswith("custom-") or
            re.search(r"[-_](202[5-9]|20[3-9]\d)", normalized_name)
        ):
            return True
            
        return False

    def resolve_active_default_model(self, tenant_id: str, provider: str, model_name: str) -> str:
        """
        Active Verification: Checks if a model exists in LiteLLM registry.
        If it does not exist (deprecated/killed), fallbacks to the cheapest active model
        and increments a Prometheus warning metric.
        """
        if self._is_model_in_registry(model_name, provider):
            return model_name
            
        # Fallback to cheapest model
        resolved = self._get_cheapest_model_from_registry(provider)
        logger.warning(
            f"Active Verification failed for tenant {tenant_id}: Model '{model_name}' for provider '{provider}' "
            f"is deprecated or not registered. Falling back to cheapest model '{resolved}'."
        )
        
        # Increment Prometheus metric
        try:
            from core.metrics import ai_core_model_deprecation_fallbacks_total
            ai_core_model_deprecation_fallbacks_total.labels(
                tenant_id=tenant_id,
                provider=provider,
                deprecated_model=model_name,
                resolved_model=resolved
            ).inc()
        except Exception as e:
            logger.error(f"Error incrementing model deprecation metric: {e}")
            
        return resolved

    async def get_system_default_route(self, tenant_id: str, use_case: str) -> Dict[str, Any]:
        """
        Dynamically resolves the default model configuration for a tenant.
        1. Finds the tenant's active API keys to identify the provider.
        2. Queries the 'system_default_route_configs' database table for this provider.
        3. Falls back to hardcoded defaults if DB is empty or missing.
        """
        tenant_uuid = safe_uuid(tenant_id)
        
        # Check active API keys for tenant
        active_providers = []
        if tenant_uuid:
            try:
                async with SessionLocal() as db:
                    stmt = select(APIKeyConfig.provider).where(
                        APIKeyConfig.tenant_id == tenant_uuid,
                        APIKeyConfig.is_active == True
                    )
                    res = await db.execute(stmt)
                    active_providers = [row[0].strip().lower() for row in res.all()]
            except Exception as e:
                logger.error(f"Error querying active keys for tenant default: {e}")

        # Choose provider based on priority
        provider = "openai" # default system fallback
        for p in PROVIDER_PRIORITY:
            if p in active_providers:
                provider = p
                break
                
        # Query system defaults table
        try:
            async with SessionLocal() as db:
                stmt = select(SystemDefaultRouteConfig).where(
                    SystemDefaultRouteConfig.provider == provider,
                    SystemDefaultRouteConfig.use_case == use_case,
                    SystemDefaultRouteConfig.is_active == True
                )
                res = await db.execute(stmt)
                config = res.scalar_one_or_none()
                if config:
                    return {
                        "primary_model": config.primary_model,
                        "fallback_model": config.fallback_model or config.primary_model,
                        "provider": config.provider,
                        "fallback_provider": config.provider,
                        "temperature": float(config.temperature),
                        "max_tokens": config.max_tokens
                    }
        except Exception as e:
            logger.error(f"Error querying system_default_route_configs: {e}")

        # Dynamic fallback from LiteLLM registry if DB query fails/is empty
        cheapest_model = self._get_cheapest_model_from_registry(provider)
        uc_params = USE_CASE_PARAMS.get(use_case, {"temperature": 0.3, "max_tokens": 300})
        
        return {
            "primary_model": cheapest_model,
            "fallback_model": cheapest_model,
            "provider": provider,
            "fallback_provider": provider,
            "temperature": uc_params["temperature"],
            "max_tokens": uc_params["max_tokens"]
        }

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

        # 3. Fallback to default route configuration from system defaults DB
        try:
            fallback_route = await self.get_system_default_route(tenant_id, use_case)
            await redis_client.setex(cache_key, 300, json.dumps(fallback_route))
            return fallback_route
        except Exception as e:
            logger.error(f"Error resolving dynamic fallback route: {e}")
            fallback_route = DEFAULT_MODEL_ROUTING.get(use_case, DEFAULT_MODEL_ROUTING["chatbot"])
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
            logger.warning(
                f"Falling back to system-level shared credentials for provider '{provider}' (tenant: {tenant_id})"
            )
            return sys_result

        # ─── 3. No credentials resolved ───
        raise ValueError(
            f"API credentials not configured for provider '{provider}' and tenant '{tenant_id}'."
        )


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

    async def compress_history(self, tenant_id: str, messages: List[Dict[str, Any]], keep_recent: int = 5) -> List[Dict[str, Any]]:
        """Compress older chat history to save tokens using a background LLM summarizer with Redis caching."""
        # Separate system messages from conversation messages to preserve system instructions intact
        system_messages = []
        seen_system_contents = set()
        for m in messages:
            if m.get("role") == "system":
                content = m.get("content", "").strip()
                if content not in seen_system_contents:
                    seen_system_contents.add(content)
                    system_messages.append(m)
        chat_messages = [m for m in messages if m.get("role") != "system"]

        if len(chat_messages) <= keep_recent:
            return system_messages + chat_messages
            
        split_index = len(chat_messages) - keep_recent
        
        # PASS 1: Prevent orphaning tool messages in the 'recent' slice by pulling in their preceding
        # assistant tool call message. Without this, a 'tool' result could appear without its
        # matching 'assistant+tool_calls' message, causing Gemini/OpenAI 400 errors.
        while split_index > 0:
            has_orphaned_tool = False
            for idx in range(split_index, len(chat_messages)):
                if chat_messages[idx].get("role") == "tool":
                    tool_call_id = chat_messages[idx].get("tool_call_id")
                    
                    found_assistant_in_recent = False
                    for aidx in range(split_index, idx):
                        if (chat_messages[aidx].get("role") == "assistant" 
                            and chat_messages[aidx].get("tool_calls")):
                            tcs = chat_messages[aidx]["tool_calls"]
                            if any(isinstance(tc, dict) and tc.get("id") == tool_call_id for tc in tcs):
                                found_assistant_in_recent = True
                                break
                    
                    if not found_assistant_in_recent:
                        has_orphaned_tool = True
                        break
            
            if has_orphaned_tool:
                split_index -= 1
            else:
                break

        # AC FIX-1A (CRITICAL): PASS 2 — Gemini API requires that an assistant+tool_calls message
        # MUST immediately follow a 'user' or 'tool' message. If the first message of the 'recent'
        # slice is assistant+tool_calls, it would be placed directly after the [system summary],
        # which violates the Gemini turn-ordering rule and causes a 400 INVALID_ARGUMENT error.
        # Fix: pull split_index backwards until 'recent' starts with a 'user' or 'tool' message.
        while split_index > 0:
            first_recent = chat_messages[split_index]
            if (first_recent.get("role") == "assistant" and first_recent.get("tool_calls")):
                split_index -= 1
            else:
                break
                
        recent = chat_messages[split_index:]
        older = chat_messages[:split_index]
        
        # Detect if conversation is in Vietnamese
        is_vn = any(is_vietnamese(m.get("content", "")) for m in messages if m.get("role") == "user")
        
        # 1. Generate standard baseline summary to return immediately.
        # FIX-2: Only include user/assistant roles in summary — tool messages contain raw JSON
        # that is meaningless when truncated, and system messages are already preserved separately.
        if is_vn:
            summary_text = "Tóm tắt lịch sử cuộc hội thoại trước đó:\n"
            summary_prefix = "Tóm tắt cuộc hội thoại trước đó:\n"
        else:
            summary_text = "Background summary of older messages:\n"
            summary_prefix = "Summary of the previous conversation:\n"
            
        for m in older:
            role = m.get("role", "user")
            content = m.get("content", "")
            # Skip tool/system roles: tool messages are raw JSON (meaningless truncated),
            # system messages are already captured in system_messages list.
            if role in ("user", "assistant") and content:
                summary_text += f"- {role}: {content[:150]}\n"

        # 2. Check strict double thresholds before triggering caching / background task
        # Threshold 1: At least keep_recent + 4 messages total (so we compress at least 4 older messages)
        # Threshold 2: older messages text length must be > 1500 characters
        older_text_len = sum(len(str(m.get("content", ""))) for m in older)
        if len(chat_messages) <= keep_recent + 4 or older_text_len <= 1500:
            logger.info(f"Skipping history summarization for tenant {tenant_id}: chat messages count {len(chat_messages)} or older text length {older_text_len} below thresholds.")
            return system_messages + chat_messages  # Keep history raw to preserve 100% context accuracy

        # 3. Check Redis Cache
        try:
            older_json = json.dumps(older, sort_keys=True)
            older_hash = hashlib.md5(older_json.encode('utf-8')).hexdigest()
            cache_key = f"{tenant_id}:history_summary:{older_hash}"
            
            cached_summary = await redis_client.get(cache_key)
            if cached_summary:
                logger.info(f"History summary cache hit for tenant {tenant_id}")
                return system_messages + [{"role": "system", "content": f"{summary_prefix}{cached_summary}"}] + recent
                
            # Cache miss -> schedule background task to summarize
            logger.info(f"History summary cache miss for tenant {tenant_id}. Scheduling background task...")
            # FIX-7: Add done_callback to catch and log background task exceptions silently
            task = asyncio.create_task(self._generate_and_cache_summary(tenant_id, older, cache_key))
            task.add_done_callback(
                lambda t: logger.error(f"Background history summary task failed for tenant {tenant_id}: {t.exception()}")
                if not t.cancelled() and t.exception() else None
            )
        except Exception as e:
            logger.error(f"Error handling history summary cache/task: {e}")
            
        # Return baseline summary immediately to avoid adding any latency to the current request
        return system_messages + [{"role": "system", "content": summary_text}] + recent

    def _get_cheapest_model_from_registry(self, provider: str, mode: str = "chat") -> str:
        provider = provider.strip().lower()
        
        # Support environment override
        env_override = os.getenv(f"DEFAULT_{provider.upper()}_PRIMARY_MODEL")
        if env_override and mode == "chat":
            return env_override

        cache_key = f"{provider}:{mode}"
        if cache_key in self._cheapest_models_cache:
            return self._cheapest_models_cache[cache_key]
            
        cheapest_model = None
        min_cost = float('inf')
        pricing_registry = getattr(litellm, "model_cost", getattr(litellm, "model_prices_and_context_window", {}))
        
        # Map target providers to include cohere_chat
        if provider == "local":
            target_providers = {"local", "ollama"}
        elif provider == "cohere":
            target_providers = {"cohere", "cohere_chat"}
        else:
            target_providers = {provider}
        
        for model_name, info in pricing_registry.items():
            if not isinstance(info, dict):
                continue
            model_provider = info.get("litellm_provider", "").lower() or info.get("provider", "").lower()
            
            # Map aliases dynamically
            if model_provider == "gemini" and "google" in target_providers:
                model_provider = "google"
            elif model_provider == "cohere_chat" and "cohere" in target_providers:
                model_provider = "cohere"
                
            if model_provider in target_providers and info.get("mode") == mode:
                input_cost = info.get("input_cost_per_token", float('inf'))
                if 0 < input_cost < min_cost:
                    min_cost = input_cost
                    cheapest_model = model_name
                    
        if not cheapest_model:
            cheapest_model = f"{provider}-default" if mode == "chat" else "text-embedding-3-small"
            
        self._cheapest_models_cache[cache_key] = cheapest_model
        return cheapest_model


    async def _get_cheapest_available_provider(self, tenant_id: str) -> tuple[str, str]:
        """
        Dynamically resolves the tenant's configured provider from Route Configs,
        then finds the cheapest model for that provider from LiteLLM registry.
        Falls back to active provider keys lookup if Route Config is not set.
        """
        tenant_uuid = safe_uuid(tenant_id)
        provider = None
        
        if tenant_uuid:
            try:
                async with SessionLocal() as db:
                    # 1. Try to find route for summarization first
                    stmt = select(LLMRouteConfig).where(
                        LLMRouteConfig.tenant_id == tenant_uuid,
                        LLMRouteConfig.use_case == "summarization"
                    )
                    result = await db.execute(stmt)
                    route = result.scalars().first()
                    
                    if not route:
                        # 2. Fallback to chatbot route config
                        stmt = select(LLMRouteConfig).where(
                            LLMRouteConfig.tenant_id == tenant_uuid,
                            LLMRouteConfig.use_case == "chatbot"
                        )
                        result = await db.execute(stmt)
                        route = result.scalars().first()
                        
                    if route:
                        provider = route.provider.strip().lower()
            except Exception as e:
                logger.error(f"Error querying route configs for tenant {tenant_id}: {e}")
                
        if provider:
            model = self._get_cheapest_model_from_registry(provider)
            logger.info(f"Resolved provider '{provider}' from Route Config and dynamic model '{model}' for tenant {tenant_id}")
            return provider, model

        # Fallback: scan active provider API keys
        active_providers = set()
        if tenant_uuid:
            try:
                async with SessionLocal() as db:
                    stmt = select(APIKeyConfig).where(
                        APIKeyConfig.tenant_id == tenant_uuid,
                        APIKeyConfig.is_active == True
                    )
                    result = await db.execute(stmt)
                    configs = result.scalars().all()
                    active_providers = {c.provider.strip().lower() for c in configs if c.api_key_encrypted}
            except Exception as e:
                logger.error(f"Error querying active provider API keys: {e}")
                
        for p in PROVIDER_PRIORITY:
            if p in active_providers:
                model = self._get_cheapest_model_from_registry(p)
                logger.info(f"Fallback selected active provider '{p}' and dynamic model '{model}' for tenant {tenant_id}")
                return p, model
                
        default_p = "openai"
        return default_p, self._get_cheapest_model_from_registry(default_p)

    async def _generate_and_cache_summary(self, tenant_id: str, older_messages: List[Dict[str, Any]], cache_key: str):
        """Asynchronously calls LLM (cheapest active provider via complete) to summarize old messages, then caches in Redis."""
        try:
            # Resolve cheapest active provider
            provider, model = await self._get_cheapest_available_provider(tenant_id)
            logger.info(f"Background history summarization task using provider '{provider}' and model '{model}' for tenant {tenant_id}")
            
            # Ensure keys exist before invoking complete
            try:
                await self.get_provider_credentials(tenant_id, provider)
            except ValueError:
                logger.warning(f"No API key configured for cheapest selected provider '{provider}' for tenant {tenant_id}. Cancelling task.")
                return

            # Build log text
            conversation_text = ""
            for m in older_messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                conversation_text += f"{role.upper()}: {content}\n"
                
            prompt = (
                "Summarize the following conversation briefly in at most 150 words. "
                "Ensure you retain core context details such as product names, prices, and customer requirements. "
                "The response MUST be written in the same language as the input conversation (e.g. if the conversation is in Vietnamese, write in Vietnamese; if in English, write in English):\n\n"
                f"{conversation_text}"
            )
            
            response = await self.complete(
                tenant_id=tenant_id,
                use_case="summarization",
                messages=[{"role": "user", "content": prompt}],
                model_override=model,
                provider_override=provider
            )
            
            summary = response.get("content")
            if summary:
                await redis_client.setex(cache_key, 3600, summary.strip())
                logger.info(f"Successfully generated and cached history summary for tenant {tenant_id}")
        except Exception as e:
            logger.warning(f"Failed to generate background history summary for tenant {tenant_id}: {e}")


    def optimize_context(self, messages: List[Dict[str, Any]], max_context_chars: int = 3200) -> List[Dict[str, Any]]:
        """Optimizes context documents within messages to avoid token blowup."""
        optimized = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            if role == "context" and content and len(content) > max_context_chars:
                truncated = content[:max_context_chars//2] + "\n...[TRUNCATED FOR TOKEN OPTIMIZATION]...\n" + content[-max_context_chars//2:]
                new_msg = msg.copy()
                new_msg["content"] = truncated
                optimized.append(new_msg)
            else:
                optimized.append(msg)
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
        tools: List[Dict[str, Any]] | None = None,
        provider_override: str | None = None,
        response_format: Dict[str, Any] | None = None
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
        if use_case == "chatbot":
            formatted_messages = await self.compress_history(tenant_id, formatted_messages)
        formatted_messages = self.optimize_context(formatted_messages)
        
        # Max tokens and temperature
        max_tok = max_tokens or route["max_tokens"]
        temp = temperature if temperature is not None else route["temperature"]
        
        # Determine providers
        primary_provider = provider_override or route["provider"]
        fallback_provider = route["fallback_provider"]

        # Active Verification for both primary and fallback models to prevent deprecation failures
        model = self.resolve_active_default_model(tenant_id, primary_provider, model)
        fallback_model = self.resolve_active_default_model(tenant_id, fallback_provider, fallback_model)

        start_time = time.time()
        is_fallback_used = False
        model_used = model

        
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
        # AC FIX-6: Add repetition penalties for chatbot use case to prevent the AI from
        # repeating the same phrases, translations or answers in multi-turn conversations.
        if use_case == "chatbot":
            kwargs["frequency_penalty"] = 0.3
            kwargs["presence_penalty"] = 0.1
        if tools:
            kwargs["tools"] = tools
        if response_format:
            kwargs["response_format"] = response_format

        # Helper to execute acompletion with dynamic keys
        async def call_llm(model_name: str, creds: Dict[str, Any], provider_name: str) -> Any:
            call_kwargs = kwargs.copy()
            call_kwargs["model"] = format_litellm_model(model_name, provider_name)
            if creds.get("api_key"):
                call_kwargs["api_key"] = creds["api_key"]
            if creds.get("api_base"):
                call_kwargs["api_base"] = creds["api_base"]
                
            # Strategy Pattern: Use ProviderAdapter to clean up parameters dynamically
            adapter = ProviderFactory.get_adapter(provider_name)
            call_kwargs = adapter.sanitize_payload(call_kwargs)

            return await acompletion(**call_kwargs)

        response = None
        # 1. Execute Primary call under primary provider's Circuit Breaker
        breaker = PROVIDER_BREAKERS.get(primary_provider, PROVIDER_BREAKERS["openai"])
        try:
            response = await call_async(breaker, call_llm, model, primary_creds, primary_provider)
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
                response = await call_async(fallback_breaker, call_llm, fallback_model, fallback_creds, fallback_provider)
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
        
        # Emit Prometheus Metrics (AC 5.5)
        try:
            from core.metrics import (
                ai_core_llm_calls_total,
                ai_core_llm_cost_usd_total,
                ai_core_llm_latency_seconds
            )
            provider_val = primary_provider if not is_fallback_used else fallback_provider
            ai_core_llm_calls_total.labels(
                tenant_id=tenant_id,
                use_case=use_case,
                provider=provider_val,
                model=model_used,
                is_fallback=str(is_fallback_used).lower()
            ).inc()
            
            ai_core_llm_cost_usd_total.labels(
                tenant_id=tenant_id,
                use_case=use_case,
                provider=provider_val
            ).inc(cost)
            
            ai_core_llm_latency_seconds.labels(
                tenant_id=tenant_id,
                use_case=use_case,
                provider=provider_val
            ).observe(latency / 1000.0)
        except Exception as e_metric:
            logger.warning(f"Failed to emit LLM Prometheus metrics: {e_metric}")
        
        choice_message = response.choices[0].message
        content = getattr(choice_message, "content", None)
        tool_calls = getattr(choice_message, "tool_calls", None)
        
        # DeepSeek-R1 logic: extract reasoning_content
        reasoning_content = None
        if hasattr(choice_message, "reasoning_content") and choice_message.reasoning_content:
            reasoning_content = choice_message.reasoning_content
        elif content and "<think>" in content and "</think>" in content:
            try:
                parts = content.split("</think>")
                think_part = parts[0].replace("<think>", "").strip()
                content_part = parts[1].strip()
                reasoning_content = think_part
                content = content_part
            except Exception:
                pass
                
        # Parse Citations dynamically through Provider Adapter
        active_provider = primary_provider if not is_fallback_used else fallback_provider
        adapter = ProviderFactory.get_adapter(active_provider)
        parsed_meta = adapter.parse_response(response, model_used)
        citations = parsed_meta.get("citations", [])
        
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
            # C2 Fix: use getattr() — ModelResponse is an object, NOT a dict
            "cache_hit": getattr(response, "cache_hit", False),
            "is_fallback": is_fallback_used,
            "reasoning_content": reasoning_content,
            "citations": citations
        }

    async def embed(
        self,
        tenant_id: str,
        texts: List[str],
        model_override: str | None = None,
        provider_override: str | None = None
    ) -> Dict[str, Any]:
        """Sends text embedding request using routing and failover with pybreaker."""
        route = await self.get_routing(tenant_id, "embedding")
        model = model_override or route["primary_model"]
        fallback_model = route["fallback_model"]
        
        primary_provider = provider_override or route["provider"]
        fallback_provider = route["fallback_provider"]

        # Active Verification
        model = self.resolve_active_default_model(tenant_id, primary_provider, model)
        fallback_model = self.resolve_active_default_model(tenant_id, fallback_provider, fallback_model)

        start_time = time.time()
        is_fallback_used = False
        model_used = model

        # Get credentials dynamically (BYOK → System → Env)
        primary_creds = await self.get_provider_credentials(tenant_id, primary_provider)
        fallback_creds = await self.get_provider_credentials(tenant_id, fallback_provider)

        # Set up kwargs for litellm.aembedding
        kwargs = {
            "input": texts,
            "timeout": 10.0
        }

        # Helper to execute aembedding with dynamic keys
        async def call_embed(model_name: str, creds: Dict[str, Any], provider_name: str) -> Any:
            call_kwargs = kwargs.copy()
            call_kwargs["model"] = format_litellm_model(model_name, provider_name)
            if creds.get("api_key"):
                call_kwargs["api_key"] = creds["api_key"]
            if creds.get("api_base"):
                call_kwargs["api_base"] = creds["api_base"]
            
            return await litellm.aembedding(**call_kwargs)

        response = None
        # 1. Execute Primary call under primary provider's Circuit Breaker
        breaker = PROVIDER_BREAKERS.get(primary_provider, PROVIDER_BREAKERS["openai"])
        try:
            response = await call_async(breaker, call_embed, model, primary_creds, primary_provider)
            model_used = model
        except Exception as e:
            logger.warning(
                f"Primary embedding model/provider {model} ({primary_provider}) failed or circuit is open on tenant {tenant_id}: {str(e)}. "
                f"Falling back to {fallback_model} ({fallback_provider})..."
            )
            is_fallback_used = True

        # 2. If primary failed, execute Fallback call under fallback provider's Circuit Breaker
        if is_fallback_used:
            fallback_breaker = PROVIDER_BREAKERS.get(fallback_provider, PROVIDER_BREAKERS["openai"])
            try:
                response = await call_async(fallback_breaker, call_embed, fallback_model, fallback_creds, fallback_provider)
                model_used = fallback_model
            except Exception as e:
                logger.error(f"Fallback embedding model {fallback_model} ({fallback_provider}) also failed: {e}")
                raise e

        latency = int((time.time() - start_time) * 1000)

        # Calculate cost
        try:
            cost = litellm.embedding_cost(model=model_used, response=response)
        except Exception:
            cost = 0.0
            
        prompt_tokens = response.usage.prompt_tokens if hasattr(response, "usage") else 0
        
        # Emit Prometheus Metrics
        try:
            from core.metrics import (
                ai_core_llm_calls_total,
                ai_core_llm_cost_usd_total,
                ai_core_llm_latency_seconds
            )
            provider_val = primary_provider if not is_fallback_used else fallback_provider
            ai_core_llm_calls_total.labels(
                tenant_id=tenant_id,
                use_case="embedding",
                provider=provider_val,
                model=model_used,
                is_fallback=str(is_fallback_used).lower()
            ).inc()
            
            ai_core_llm_cost_usd_total.labels(
                tenant_id=tenant_id,
                use_case="embedding",
                provider=provider_val
            ).inc(cost)
            
            ai_core_llm_latency_seconds.labels(
                tenant_id=tenant_id,
                use_case="embedding",
                provider=provider_val
            ).observe(latency / 1000.0)
        except Exception as e_metric:
            logger.warning(f"Failed to emit embedding Prometheus metrics: {e_metric}")

        # Extract embeddings
        embeddings = [item["embedding"] for item in response["data"]]
        return {
            "embeddings": embeddings,
            "model_used": model_used,
            "provider": primary_provider if not is_fallback_used else fallback_provider,
            "prompt_tokens": prompt_tokens,
            "cost_usd": cost,
            "latency_ms": latency,
            "is_fallback": is_fallback_used
        }

# Hot reload test comment
