import os
import json
import logging
import asyncio
import httpx
import litellm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import SessionLocal
from db.models import SystemDefaultRouteConfig
from core.redis_client import redis_client

logger = logging.getLogger("solavie.ai_core.dynamic_cost")

LITELLM_PRICING_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
CACHE_FILE_PATH = "storage/model_prices_cache.json"

# Fallback hardcoded defaults if LiteLLM registry lookup fails completely (all 12 providers mapped)
from core.providers import PROVIDERS_REGISTRY, USE_CASE_PARAMS

async def sync_dynamic_cost_registry() -> None:
    """
    Fetches the latest LLM pricing registry from LiteLLM GitHub repository,
    saves it to a local cache file, updates LiteLLM's in-memory registry,
    and recalculates/saves system default models in the database.
    """
    os.makedirs(os.path.dirname(CACHE_FILE_PATH), exist_ok=True)
    pricing_data = None

    # 1. Attempt to fetch remote JSON from GitHub (timeout 5s)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(LITELLM_PRICING_URL)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and len(data) > 100:
                    # Lấy 100 phần tử đầu để kiểm tra cấu trúc mẫu
                    sample_keys = list(data.keys())[:100]
                    valid_samples = sum(
                        1 for k in sample_keys
                        if isinstance(data[k], dict) and ("input_cost_per_token" in data[k] or "output_cost_per_token" in data[k])
                    )
                    if valid_samples >= 10: # Ít nhất 10/100 mẫu khớp định dạng giá LiteLLM
                        pricing_data = data
                        # Cache locally
                        with open(CACHE_FILE_PATH, "w", encoding="utf-8") as f:
                            json.dump(pricing_data, f, indent=2)
                        logger.info("Successfully fetched and cached latest LiteLLM pricing registry from GitHub using structural validation.")
                    else:
                        logger.warning("Fetched pricing registry JSON format failed structural validation.")
                else:
                    logger.warning("Fetched pricing registry JSON format is invalid.")
            else:
                logger.warning(f"Failed to fetch pricing registry: HTTP {response.status_code}")
    except Exception as e:
        logger.warning(f"Error fetching dynamic pricing registry from GitHub: {e}")

    # 2. If remote fetch failed, try loading from local cache file
    if not pricing_data:
        if os.path.exists(CACHE_FILE_PATH):
            try:
                with open(CACHE_FILE_PATH, "r", encoding="utf-8") as f:
                    pricing_data = json.load(f)
                logger.info("Loaded LiteLLM pricing registry from local cache file.")
            except Exception as cache_err:
                logger.error(f"Failed to load cached pricing file: {cache_err}")
        else:
            logger.info("No local pricing cache found. Using LiteLLM built-in registry.")

    # 3. If we loaded pricing data, apply it to LiteLLM
    if pricing_data:
        try:
            litellm.set_model_cost(pricing_data)
        except Exception as e:
            logger.error(f"Failed to load pricing data into LiteLLM registry: {e}")

    # 4. Trigger database synchronization for system default models
    try:
        async with SessionLocal() as db:
            await sync_system_default_configs(db)
    except Exception as db_err:
        logger.error(f"Error during system default configs sync: {db_err}")

async def sync_system_default_configs(db: AsyncSession) -> None:
    """
    Scans the current LiteLLM registry to identify the cheapest models for each provider
    and updates/UPSERTs the 'system_default_route_configs' table for all use cases.
    """
    logger.info("Syncing system default route configurations in database...")
    pricing_registry = getattr(litellm, "model_cost", getattr(litellm, "model_prices_and_context_window", {}))
    providers = list(PROVIDERS_REGISTRY.keys())

    # Map to hold list of chat models and their cost per provider: provider -> [(model_name, cost)]
    provider_chat_models = {p: [] for p in providers}

    # 1. Scan LiteLLM registry to collect all chat models with valid input costs
    for model_name, info in pricing_registry.items():
        if not isinstance(info, dict):
            continue
        
        model_provider = info.get("litellm_provider", "").lower() or info.get("provider", "").lower()
        matched_provider = None
        
        if model_provider in provider_chat_models:
            matched_provider = model_provider
        elif model_provider == "ollama" and "local" in provider_chat_models:
            matched_provider = "local"
        elif model_provider == "gemini" and "google" in provider_chat_models:
            matched_provider = "google"

        if not matched_provider:
            continue
        
        # We only care about chat models
        if info.get("mode") == "chat":
            input_cost = info.get("input_cost_per_token")
            # Filter out models with no cost info or negative cost
            if input_cost is not None and input_cost > 0:
                provider_chat_models[matched_provider].append((model_name, input_cost))

    # 2. For each provider, determine primary (cheapest) and fallback (second cheapest or same)
    resolved_defaults = {}
    for provider in providers:
        models_list = provider_chat_models[provider]
        if models_list:
            # Sort by input cost ascending
            models_list.sort(key=lambda x: x[1])
            cheapest = models_list[0][0]
            fallback = models_list[1][0] if len(models_list) > 1 else cheapest
            resolved_defaults[provider] = {"primary": cheapest, "fallback": fallback}
            logger.debug(f"Resolved provider '{provider}': primary={cheapest}, fallback={fallback}")
        else:
            # Fallback to dynamic bootstrap string naming if registry scanning returns nothing
            cheapest_fallback = f"{provider}-default"
            resolved_defaults[provider] = {"primary": cheapest_fallback, "fallback": cheapest_fallback}
            logger.warning(f"No chat models found in registry for provider '{provider}'. Using dynamic fallback model naming.")

    # 3. Synchronize database records for each provider and use case
    for provider, models in resolved_defaults.items():
        primary = models["primary"]
        fallback = models["fallback"]

        for use_case, params in USE_CASE_PARAMS.items():
            # Check if record exists
            stmt = select(SystemDefaultRouteConfig).where(
                SystemDefaultRouteConfig.provider == provider,
                SystemDefaultRouteConfig.use_case == use_case
            )
            result = await db.execute(stmt)
            config = result.scalar_one_or_none()

            temp = params["temperature"]
            max_tok = params["max_tokens"]

            if not config:
                config = SystemDefaultRouteConfig(
                    provider=provider,
                    use_case=use_case,
                    primary_model=primary,
                    fallback_model=fallback,
                    temperature=temp,
                    max_tokens=max_tok,
                    is_active=True
                )
                db.add(config)
            else:
                config.primary_model = primary
                config.fallback_model = fallback
                config.temperature = temp
                config.max_tokens = max_tok
                config.is_active = True

            # Invalidate Redis cache key for this default config
            cache_key = f"system_default_route_config:{provider}:{use_case}"
            await redis_client.delete(cache_key)

    await db.commit()
    logger.info("Successfully updated system default route configurations on DB and invalidated cache.")

async def dynamic_cost_sync_loop() -> None:
    """
    Background loop that runs periodically to fetch the latest cost registry
    and sync default configurations. Default interval: 24 hours.
    """
    # Sleep interval (default 24 hours)
    interval = int(os.getenv("DYNAMIC_COST_SYNC_INTERVAL_SECONDS", 24 * 3600))
    logger.info(f"Starting dynamic cost registry synchronization background task (interval: {interval}s)")
    
    # Wait a short duration (10s) on startup before running to let the web server initialize
    await asyncio.sleep(10.0)

    try:
        while True:
            logger.info("Triggering background dynamic cost registry synchronization...")
            await sync_dynamic_cost_registry()
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("Dynamic cost sync background task cancelled.")
    except Exception as e:
        logger.error(f"Error in dynamic cost sync loop: {e}")

async def auto_create_tenant_routes_from_defaults(db: AsyncSession, tenant_uuid, provider: str) -> None:
    """
    Automatically creates LLMRouteConfig records for all 5 use cases for a tenant
    based on the system default route configuration (cheapest models) for the given provider.
    """
    import uuid
    # Convert tenant_uuid to UUID if it's a string
    if isinstance(tenant_uuid, str):
        try:
            tenant_uuid = uuid.UUID(tenant_uuid)
        except Exception:
            logger.error(f"Invalid tenant_uuid string: {tenant_uuid}")
            return

    logger.info(f"Auto-creating route configs for tenant {tenant_uuid} using provider defaults: {provider}")
    from db.models import LLMRouteConfig, SystemDefaultRouteConfig
    
    # 1. Query SystemDefaultRouteConfig for this provider
    stmt = select(SystemDefaultRouteConfig).where(
        SystemDefaultRouteConfig.provider == provider,
        SystemDefaultRouteConfig.is_active == True
    )
    result = await db.execute(stmt)
    defaults = result.scalars().all()
    
    if not defaults:
        logger.warning(f"No active system default routes found for provider '{provider}'. Auto-creation skipped.")
        return
        
    for default in defaults:
        use_case = default.use_case
        
        # 2. Check if a route config already exists for this tenant and use case
        stmt_exist = select(LLMRouteConfig).where(
            LLMRouteConfig.tenant_id == tenant_uuid,
            LLMRouteConfig.use_case == use_case
        )
        res_exist = await db.execute(stmt_exist)
        exist_config = res_exist.scalar_one_or_none()
        
        if not exist_config:
            # Create a new route config
            new_config = LLMRouteConfig(
                tenant_id=tenant_uuid,
                use_case=use_case,
                primary_model=default.primary_model,
                fallback_model=default.fallback_model or default.primary_model,
                provider=provider,
                fallback_provider=provider,
                temperature=default.temperature,
                max_tokens=default.max_tokens,
                is_active=True
            )
            db.add(new_config)
            logger.info(f"Auto-created Route Config for tenant {tenant_uuid}, use_case: {use_case}")
        
        # 3. Invalidate Redis Cache per use case
        cache_key = f"{tenant_uuid}:config:llm_model_routing:{use_case}"
        try:
            await redis_client.delete(cache_key)
        except Exception as e:
            logger.error(f"Error deleting cache key {cache_key}: {e}")
            
    await db.commit()
    logger.info(f"Completed auto-creation of route configs for tenant {tenant_uuid}")
