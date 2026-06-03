import asyncio
import json
import logging
import uuid
import httpx
from sqlalchemy import select

from core.config import settings
from core.redis_client import redis_client
from db.database import SessionLocal
from db.models import LLMRouteConfig, APIKeyConfig

logger = logging.getLogger(__name__)

async def fetch_and_sync_config(tenant_id: str, use_case: str | None = None) -> None:
    """
    Fetches the actual configuration from Tenant Config Service via REST API
    and synchronizes it to the local PostgreSQL database (ai_core_db).
    """
    tenant_uuid = uuid.UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
    
    logger.info(f"Fetching config for tenant {tenant_id} from Tenant Config Service at {settings.TENANT_CONFIG_SERVICE_URL}...")
    
    url = f"{settings.TENANT_CONFIG_SERVICE_URL}/api/v1/config/ai_kb"
    headers = {"X-Tenant-ID": str(tenant_uuid)}
    
    # 1. Fetch from Tenant Config Service
    config_data = {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                config_data = response.json()
                logger.info(f"Successfully fetched config from Tenant Config Service: {config_data}")
            else:
                logger.warning(f"Tenant Config Service returned status {response.status_code}. Using defaults.")
    except Exception as e:
        logger.error(f"Failed to fetch config from Tenant Config Service due to: {e}. Using defaults.")

    # 2. Extract values and populate local database
    model_routing = config_data.get("llm_model_routing", {})
    fallback_models = config_data.get("ai_fallback_models", [])
    api_keys = config_data.get("api_keys", {})

    # Default mappings if empty
    if not model_routing:
        model_routing = {
            "chatbot": "gpt-4o-mini",
            "content_generation": "claude-3-5-sonnet-20241022",
            "summarization": "gpt-4o-mini",
            "sentiment": "gpt-4o-mini",
            "classification": "gpt-4o-mini"
        }
    if not fallback_models:
        fallback_models = ["claude-3-haiku-20240307", "gpt-4o"]

    # Helper function to guess provider from model name
    def get_provider_by_model(model_name: str) -> str:
        name = model_name.lower()
        if "gpt" in name or "text-embedding" in name:
            return "openai"
        if "claude" in name:
            return "anthropic"
        if "gemini" in name:
            return "google"
        return "local"

    async with SessionLocal() as db:
        # Sync Model Routing Configs
        for uc, model in model_routing.items():
            # Skip if we only want to sync a specific use case
            if use_case and uc != use_case:
                continue
                
            stmt = select(LLMRouteConfig).where(
                LLMRouteConfig.tenant_id == tenant_uuid,
                LLMRouteConfig.use_case == uc
            )
            result = await db.execute(stmt)
            route = result.scalar_one_or_none()
            
            provider = get_provider_by_model(model)
            # Pick a fallback model of a different provider if possible
            fallback_model = fallback_models[0] if fallback_models else "claude-3-haiku-20240307"
            fallback_provider = get_provider_by_model(fallback_model)
            
            temp = 0.7 if uc == "content_generation" else 0.3
            max_tok = 1500 if uc == "content_generation" else 300
            
            if not route:
                route = LLMRouteConfig(
                    tenant_id=tenant_uuid,
                    use_case=uc,
                    primary_model=model,
                    fallback_model=fallback_model,
                    provider=provider,
                    fallback_provider=fallback_provider,
                    temperature=temp,
                    max_tokens=max_tok,
                    is_active=True
                )
                db.add(route)
            else:
                route.primary_model = model
                route.fallback_model = fallback_model
                route.provider = provider
                route.fallback_provider = fallback_provider
                route.temperature = temp
                route.max_tokens = max_tok
                route.is_active = True
                
            # Invalidate Redis cache for this routing
            cache_key = f"{tenant_uuid}:config:llm_model_routing:{uc}"
            await redis_client.delete(cache_key)
            logger.info(f"Invalidated model routing cache for {cache_key}")
            
        # Sync API Keys
        for provider_name, key_info in api_keys.items():
            encrypted_key = key_info.get("api_key_encrypted")
            if not encrypted_key:
                continue
                
            stmt = select(APIKeyConfig).where(APIKeyConfig.provider == provider_name)
            result = await db.execute(stmt)
            key_config = result.scalar_one_or_none()
            
            if not key_config:
                key_config = APIKeyConfig(
                    provider=provider_name,
                    api_key_encrypted=encrypted_key,
                    api_base=key_info.get("api_base"),
                    is_active=key_info.get("is_active", True)
                )
                db.add(key_config)
            else:
                key_config.api_key_encrypted = encrypted_key
                key_config.api_base = key_info.get("api_base", key_config.api_base)
                key_config.is_active = key_info.get("is_active", key_config.is_active)
                
            # Invalidate credentials cache
            cred_cache_key = f"config:api_keys:{provider_name}"
            await redis_client.delete(cred_cache_key)
            logger.info(f"Invalidated provider credentials cache for {cred_cache_key}")

        await db.commit()

async def sync_listener_loop() -> None:
    """
    Background loop listening to Redis Pub/Sub channels:
      - config.updates          — Tenant-level AI/KB config changes
      - system.limits.updates   — System-level tier limit changes (from System Admin)
    """
    pubsub = redis_client.pubsub()
    channels = ["config.updates", "system.limits.updates"]
    await pubsub.subscribe(*channels)
    logger.info(f"Sync listener subscribed to Redis channels: {channels}")
    
    try:
        while True:
            # We check for message with a timeout of 1s
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                try:
                    channel = message.get("channel", b"").decode("utf-8") if isinstance(message.get("channel"), bytes) else message.get("channel", "")
                    payload = json.loads(message["data"])
                    logger.info(f"Captured event on channel '{channel}': {payload}")
                    
                    if channel == "config.updates":
                        # ── Tenant config sync ──
                        category = payload.get("category")
                        tenant_id = payload.get("tenant_id")
                        use_case = payload.get("use_case")
                        
                        if category == "ai_kb" and tenant_id:
                            await fetch_and_sync_config(tenant_id, use_case)
                            logger.info(f"Config sync completed successfully for tenant {tenant_id}.")
                    
                    elif channel == "system.limits.updates":
                        # ── System-level tier limit invalidation ──
                        tier_name = payload.get("tier_name")
                        if tier_name:
                            cache_key = f"tier:{tier_name}:limits"
                            await redis_client.delete(cache_key)
                            logger.info(f"Invalidated dynamic tier limits cache: '{cache_key}'")
                        else:
                            # Wildcard: invalidate all known tier keys
                            for t in ["free", "standard", "enterprise"]:
                                await redis_client.delete(f"tier:{t}:limits")
                            logger.info("Invalidated ALL dynamic tier limits caches (no tier_name specified).")

                except Exception as ex:
                    logger.error(f"Error parsing sync event message: {ex}")
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        logger.info("Sync listener task cancelled.")
    except Exception as e:
        logger.error(f"Sync listener loop error: {e}")
    finally:
        await pubsub.unsubscribe(*channels)

