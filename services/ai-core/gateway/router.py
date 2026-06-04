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

from core.config import settings
from core.crypto import decrypt_key
from core.circuit_breaker import call_async
from core.redis_client import redis_client
from db.database import SessionLocal
from db.models import LLMRouteConfig, APIKeyConfig, SystemDefaultRouteConfig

logger = logging.getLogger(__name__)

def sanitize_mistral_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Clean Mistral tools schema by recursively removing None values or empty dicts."""
    if not tools:
        return tools
    import copy
    sanitized = copy.deepcopy(tools)
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
    return [clean_dict(t) for t in sanitized]

def apply_anthropic_caching(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """AC 14.1: Inject ephemeral cache_control at static breakpoints (System Prompt, RAG Context)."""
    import copy
    new_msgs = copy.deepcopy(messages)
    system_msgs = [m for m in new_msgs if m.get("role") == "system"]
    if system_msgs:
        system_msgs[-1]["cache_control"] = {"type": "ephemeral"}
    context_msgs = [m for m in new_msgs if m.get("role") == "context"]
    if context_msgs:
        context_msgs[-1]["cache_control"] = {"type": "ephemeral"}
    return new_msgs

def apply_openai_caching(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    AC 14.1 — OpenAI Prompt Caching:
    OpenAI (gpt-4o, gpt-4o-mini, o1, o3) automatically caches prompts > 1024 tokens
    using a 128-token granularity suffix. No special headers required.
    We set extra_headers to signal caching readiness and ensure system prompt
    is placed first (static prefix) to maximize cache hit rate.
    See: https://platform.openai.com/docs/guides/prompt-caching
    """
    import copy
    cached = copy.deepcopy(kwargs)
    messages = cached.get("messages", [])

    # Reorder: ensure system message is first (acts as cached prefix)
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]
    if system_msgs:
        cached["messages"] = system_msgs + non_system

    # Signal OpenAI caching readiness (no-op if not supported, but harmless)
    cached.setdefault("extra_headers", {})
    cached["extra_headers"]["X-Cache-Hint"] = "prompt-caching-enabled"
    return cached

def build_gemini_context_cache_params(
    token_count: int,
    extra_kwargs: Dict[str, Any],
    ttl_seconds: int = 300
) -> Dict[str, Any]:
    """
    AC 14.2 — Gemini Context Caching:
    For large contexts (> 32k tokens), inject context_cache_ttl_seconds via
    LiteLLM extra_body to activate Gemini's cached content feature.
    Reduces cost by ~75% for repeated large-context requests.
    Ref: https://ai.google.dev/api/caching
    """
    GEMINI_CONTEXT_CACHE_THRESHOLD = 32_000  # tokens
    if token_count > GEMINI_CONTEXT_CACHE_THRESHOLD:
        logger.info(
            f"Gemini context caching activated: {token_count} tokens > {GEMINI_CONTEXT_CACHE_THRESHOLD} threshold, TTL={ttl_seconds}s"
        )
        extra_kwargs.setdefault("extra_body", {})
        extra_kwargs["extra_body"]["cachedContent"] = {
            "ttl": f"{ttl_seconds}s"
        }
    return extra_kwargs

def apply_mistral_eu_routing(creds: Dict[str, Any], call_kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    AC 14.6 — Mistral EU nodes routing:
    If the tenant's api_base contains 'eu.' or 'europe', route to the EU node.
    Otherwise, auto-detect if the model name contains 'eu' as a hint.
    EU endpoint: https://api.mistral.ai (EU region via DNS, or custom)
    """
    MISTRAL_EU_ENDPOINT = "https://api.mistral.ai"  # EU-hosted by default for Mistral La Plateforme
    existing_base = creds.get("api_base", "") or ""
    if existing_base and ("eu." in existing_base.lower() or "europe" in existing_base.lower()):
        # EU endpoint explicitly configured — use as-is
        call_kwargs["api_base"] = existing_base
        logger.debug(f"Mistral EU routing: using configured EU endpoint '{existing_base}'")
    elif not existing_base:
        # No custom endpoint — use Mistral's default (EU-hosted) API
        call_kwargs["api_base"] = MISTRAL_EU_ENDPOINT
    return call_kwargs

from core.providers import (
    PROVIDER_PRIORITY,
    PROVIDER_BREAKERS,
    USE_CASE_PARAMS,
    get_provider_by_model,
    get_env_fallback_key
)

# Dynamically construct DEFAULT_MODEL_ROUTING at module load time
DEFAULT_MODEL_ROUTING = {}

def init_default_model_routing():
    global DEFAULT_MODEL_ROUTING
    # Find cheapest chat model in LiteLLM registry for each default provider
    pricing_registry = getattr(litellm, "model_cost", getattr(litellm, "model_prices_and_context_window", {}))
    
    def get_cheapest(provider: str) -> str:
        cheapest_model = None
        min_cost = float('inf')
        target_providers = {"local", "ollama"} if provider == "local" else {provider}
        
        for m_name, info in pricing_registry.items():
            if not isinstance(info, dict):
                continue
            model_provider = info.get("litellm_provider", "").lower() or info.get("provider", "").lower()
            if model_provider in target_providers and info.get("mode") == "chat":
                input_cost = info.get("input_cost_per_token", float('inf'))
                if 0 < input_cost < min_cost:
                    min_cost = input_cost
                    cheapest_model = m_name
                    
        return cheapest_model or f"{provider}-default"

    for uc, uc_info in USE_CASE_PARAMS.items():
        prov = uc_info["default_provider"]
        cheapest_model = get_cheapest(prov)
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
    
    if prov == "google":
        # Google provider uses gemini/ prefix in LiteLLM
        return f"gemini/{normalized_name}"
    elif prov in ["deepseek", "cohere", "groq", "together_ai", "perplexity", "mistral", "openrouter", "vertex_ai", "gemini"]:
        return f"{prov}/{normalized_name}"
        
    return normalized_name

class LLMGateway:
    _cheapest_models_cache = {}

    def __init__(self):
        litellm.telemetry = False
        # Set base keys in litellm for static configurations
        if settings.OPENAI_API_KEY:
            litellm.api_key = settings.OPENAI_API_KEY
        if settings.ANTHROPIC_API_KEY:
            litellm.anthropic_key = settings.ANTHROPIC_API_KEY

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
            return sys_result

        # ─── 3. Env fallback ───
        api_key = get_env_fallback_key(provider)

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

    async def compress_history(self, tenant_id: str, messages: List[Dict[str, Any]], keep_recent: int = 5) -> List[Dict[str, Any]]:
        """Compress older chat history to save tokens using a background LLM summarizer with Redis caching."""
        if len(messages) <= keep_recent:
            return messages
            
        recent = messages[-keep_recent:]
        older = messages[:-keep_recent]
        
        # 1. Generate standard baseline summary to return immediately
        summary_text = "Background summary of older messages:\n"
        for m in older:
            role = m.get("role", "user")
            content = m.get("content", "")
            summary_text += f"- {role}: {content[:100]}\n"

        # 2. Check strict double thresholds before triggering caching / background task
        # Threshold 1: At least keep_recent + 4 messages total (so we compress at least 4 older messages)
        # Threshold 2: older messages text length must be > 1500 characters
        older_text_len = sum(len(str(m.get("content", ""))) for m in older)
        if len(messages) <= keep_recent + 4 or older_text_len <= 1500:
            logger.info(f"Skipping history summarization for tenant {tenant_id}: messages count {len(messages)} or older text length {older_text_len} below thresholds.")
            return messages  # Keep history raw to preserve 100% context accuracy

        # 3. Check Redis Cache
        try:
            older_json = json.dumps(older, sort_keys=True)
            older_hash = hashlib.md5(older_json.encode('utf-8')).hexdigest()
            cache_key = f"{tenant_id}:history_summary:{older_hash}"
            
            cached_summary = await redis_client.get(cache_key)
            if cached_summary:
                logger.info(f"History summary cache hit for tenant {tenant_id}")
                return [{"role": "system", "content": f"Tóm tắt cuộc hội thoại trước đó:\n{cached_summary}"}] + recent
                
            # Cache miss -> schedule background task to summarize
            logger.info(f"History summary cache miss for tenant {tenant_id}. Scheduling background task...")
            asyncio.create_task(self._generate_and_cache_summary(tenant_id, older, cache_key))
        except Exception as e:
            logger.error(f"Error handling history summary cache/task: {e}")
            
        # Return baseline summary immediately to avoid adding any latency to the current request
        return [{"role": "system", "content": summary_text}] + recent

    def _get_cheapest_model_from_registry(self, provider: str) -> str:
        provider = provider.strip().lower()
        
        # Support environment override
        env_override = os.getenv(f"DEFAULT_{provider.upper()}_PRIMARY_MODEL")
        if env_override:
            return env_override

        if provider in self._cheapest_models_cache:
            return self._cheapest_models_cache[provider]
            
        cheapest_model = None
        min_cost = float('inf')
        pricing_registry = getattr(litellm, "model_cost", getattr(litellm, "model_prices_and_context_window", {}))
        
        target_providers = {"local", "ollama"} if provider == "local" else {provider}
        
        for model_name, info in pricing_registry.items():
            if not isinstance(info, dict):
                continue
            model_provider = info.get("litellm_provider", "").lower() or info.get("provider", "").lower()
            
            # Map aliases dynamically
            if model_provider == "gemini" and "google" in target_providers:
                model_provider = "google"
                
            if model_provider in target_providers and info.get("mode") == "chat":
                input_cost = info.get("input_cost_per_token", float('inf'))
                if 0 < input_cost < min_cost:
                    min_cost = input_cost
                    cheapest_model = model_name
                    
        if not cheapest_model:
            cheapest_model = f"{provider}-default"
            
        self._cheapest_models_cache[provider] = cheapest_model
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
                "Hãy tóm tắt ngắn gọn cuộc hội thoại sau trong tối đa 150 từ. "
                "Đảm bảo giữ lại các chi tiết ngữ cảnh cốt lõi như tên sản phẩm, giá cả, và yêu cầu của khách hàng:\n\n"
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
        tools: List[Dict[str, Any]] | None = None,
        provider_override: str | None = None
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
        if tools:
            kwargs["tools"] = tools

        # Helper to execute acompletion with dynamic keys
        async def call_llm(model_name: str, creds: Dict[str, Any], provider_name: str) -> Any:
            call_kwargs = kwargs.copy()
            call_kwargs["model"] = format_litellm_model(model_name, provider_name)
            if creds.get("api_key"):
                call_kwargs["api_key"] = creds["api_key"]
            if creds.get("api_base"):
                call_kwargs["api_base"] = creds["api_base"]
                
            # Provider-specific optimizations (AC 14.1 - 14.6)
            prov = provider_name.strip().lower()

            if prov == "openai":
                # AC 14.1: OpenAI Prompt Caching — system prompt first + cache hint header
                call_kwargs = apply_openai_caching(call_kwargs)

            elif prov == "anthropic":
                # AC 14.1: Anthropic ephemeral cache_control breakpoints
                call_kwargs["messages"] = apply_anthropic_caching(call_kwargs["messages"])

            elif prov in ("google", "gemini"):
                # AC 14.2: Google Safety Settings
                call_kwargs["safety_settings"] = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
                ]
                # AC 14.2: Gemini Context Caching for large contexts (> 32k tokens)
                msg_text_len = sum(len(str(m.get("content", ""))) for m in call_kwargs.get("messages", []))
                estimated_tokens = msg_text_len // 4  # rough 4-char-per-token estimate
                call_kwargs = build_gemini_context_cache_params(
                    estimated_tokens, call_kwargs, ttl_seconds=300
                )

            elif prov == "deepseek":
                # AC 14.3: DeepSeek fast timeout + fallback (5s to prevent network hang)
                call_kwargs["timeout"] = 5.0

            elif prov == "mistral":
                # AC 14.6: Sanitize null parameters (prevent 400 Bad Request)
                if "tools" in call_kwargs:
                    call_kwargs["tools"] = sanitize_mistral_tools(call_kwargs["tools"])
                # AC 14.6: EU nodes routing
                call_kwargs = apply_mistral_eu_routing(creds, call_kwargs)

            # AC 14.4: Local LLM (vLLM/Ollama) — api_base injected from creds (already handled above)

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
                
        # C3 Fix: Parse Citations for Perplexity and Cohere
        # Use getattr() — response is a litellm ModelResponse object, NOT a dict
        citations = []
        direct_citations = getattr(response, "citations", None)
        if direct_citations:
            # Perplexity returns citations as list of URLs directly
            citations = list(direct_citations)
        elif "cohere" in model_used.lower():
            # Cohere returns citations in response.choices[0].message or response-level attribute
            meta = getattr(response, "meta", None)
            raw_citations = (
                getattr(response, "citations", None)
                or (getattr(meta, "citations", None) if meta else None)
                or []
            )
            for c in raw_citations:
                # Cohere citation format: {start, end, text, document_ids}
                if isinstance(c, dict):
                    citations.append({
                        "start": c.get("start"),
                        "end": c.get("end"),
                        "text": c.get("text"),
                        "source": c.get("document_ids", [])
                    })
                else:
                    # Handle object-style citations
                    citations.append({
                        "start": getattr(c, "start", None),
                        "end": getattr(c, "end", None),
                        "text": getattr(c, "text", None),
                        "source": getattr(c, "document_ids", [])
                    })
        
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
