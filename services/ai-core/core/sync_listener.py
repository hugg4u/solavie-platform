import asyncio
import json
import logging
import uuid
import httpx
from sqlalchemy import select

from core.config import settings
from core.redis_client import redis_client
from db.database import SessionLocal
from db.models import LLMRouteConfig, APIKeyConfig, SystemDefaultRouteConfig, TenantMCPServer
from core.providers import PROVIDER_PRIORITY, get_provider_by_model

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
    
    # 1. Fetch from Tenant Config Service with exponential backoff retry (AC 2.6)
    config_data = {}
    max_retries = 3
    base_delay = 1.0
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    config_data = response.json()
                    logger.info(f"Successfully fetched config from Tenant Config Service: {config_data}")
                    break
                else:
                    raise httpx.HTTPStatusError(
                        f"Status {response.status_code}",
                        request=response.request,
                        response=response
                    )
        except Exception as e:
            if attempt == max_retries:
                logger.error(f"Failed to fetch config from Tenant Config Service after {max_retries} retries: {e}. Using defaults.")
            else:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Failed to fetch config (attempt {attempt + 1}/{max_retries + 1}) due to: {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)

    # 2. Extract values and populate local database
    model_routing = config_data.get("llm_model_routing", {})
    fallback_models = config_data.get("ai_fallback_models", [])
    api_keys = config_data.get("api_keys", {})



    async with SessionLocal() as db:
        # Check active keys count before sync
        stmt_count = select(APIKeyConfig).where(
            APIKeyConfig.tenant_id == tenant_uuid,
            APIKeyConfig.is_active == True
        )
        res_count = await db.execute(stmt_count)
        active_keys_before = len(res_count.scalars().all())

        # Determine the tenant's active providers to select the best default provider
        active_providers = set()
        for p_name, k_info in api_keys.items():
            if k_info.get("api_key_encrypted") and k_info.get("is_active", True) is not False:
                active_providers.add(p_name.strip().lower())
                
        try:
            stmt = select(APIKeyConfig.provider).where(
                APIKeyConfig.tenant_id == tenant_uuid,
                APIKeyConfig.is_active == True
            )
            res = await db.execute(stmt)
            for row in res.all():
                active_providers.add(row[0].strip().lower())
        except Exception as e:
            logger.error(f"Error querying existing active keys: {e}")

        # Priority resolution for defaults
        selected_provider = "openai"
        for p in PROVIDER_PRIORITY:
            if p in active_providers:
                selected_provider = p
                break

        # Populate model_routing from system_default_route_configs in DB if empty
        if not model_routing:
            try:
                stmt = select(SystemDefaultRouteConfig).where(
                    SystemDefaultRouteConfig.provider == selected_provider,
                    SystemDefaultRouteConfig.is_active == True
                )
                res = await db.execute(stmt)
                db_defaults = res.scalars().all()
                for d_config in db_defaults:
                    model_routing[d_config.use_case] = d_config.primary_model
            except Exception as e:
                logger.error(f"Error querying default system routes for tenant sync: {e}")

            # Safe Python backup fallback
            if not model_routing:
                from gateway.router import LLMGateway
                gateway = LLMGateway()
                cheapest_model = gateway._get_cheapest_model_from_registry(selected_provider, mode="chat")
                cheapest_embed = gateway._get_cheapest_model_from_registry(selected_provider, mode="embedding")
                model_routing = {
                    "chatbot": cheapest_model,
                    "content_generation": cheapest_model,
                    "summarization": cheapest_model,
                    "sentiment": cheapest_model,
                    "classification": cheapest_model,
                    "utility": cheapest_model,
                    "embedding": cheapest_embed
                }

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
            
            # Query default details from DB
            default_config = None
            try:
                stmt = select(SystemDefaultRouteConfig).where(
                    SystemDefaultRouteConfig.provider == provider,
                    SystemDefaultRouteConfig.use_case == uc
                )
                res = await db.execute(stmt)
                default_config = res.scalar_one_or_none()
            except Exception as e:
                logger.error(f"Error querying default config for routing sync: {e}")

            if default_config:
                fallback_model = default_config.fallback_model or default_config.primary_model
                fallback_provider = provider
                temp = float(default_config.temperature)
                max_tok = default_config.max_tokens
            else:
                # Safe fallback heuristics
                from core.providers import USE_CASE_PARAMS
                from gateway.router import LLMGateway
                gateway = LLMGateway()
                cheapest_model = gateway._get_cheapest_model_from_registry(provider)
                params = USE_CASE_PARAMS.get(uc, {"temperature": 0.3, "max_tokens": 300})
                fallback_model = fallback_models[0] if fallback_models else cheapest_model
                fallback_provider = get_provider_by_model(fallback_model)
                temp = params["temperature"]
                max_tok = params["max_tokens"]
            
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
                
            stmt = select(APIKeyConfig).where(
                APIKeyConfig.tenant_id == tenant_uuid,
                APIKeyConfig.provider == provider_name
            )
            result = await db.execute(stmt)
            key_config = result.scalar_one_or_none()
            
            if not key_config:
                key_config = APIKeyConfig(
                    tenant_id=tenant_uuid,
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
            cred_cache_key = f"{tenant_uuid}:config:api_keys:{provider_name}"
            await redis_client.delete(cred_cache_key)
            logger.info(f"Invalidated provider credentials cache for {cred_cache_key}")

        # Sync MCP Servers Whitelist
        mcp_servers = config_data.get("mcp_server_whitelist") or config_data.get("mcp_servers", [])
        new_servers = {s["server_name"]: s for s in mcp_servers if "server_name" in s}

        try:
            stmt_mcp = select(TenantMCPServer).where(TenantMCPServer.tenant_id == tenant_uuid)
            res_mcp = await db.execute(stmt_mcp)
            existing_servers = res_mcp.scalars().all()
            existing_map = {s.server_name: s for s in existing_servers}

            for s_name, s_data in new_servers.items():
                url_val = s_data.get("sse_url")
                status_val = s_data.get("status", "active")
                is_active_val = (status_val == "active" or s_data.get("is_active", True) is not False)
                
                if s_name in existing_map:
                    db_server = existing_map[s_name]
                    db_server.sse_url = url_val
                    db_server.is_active = is_active_val
                else:
                    db_server = TenantMCPServer(
                        tenant_id=tenant_uuid,
                        server_name=s_name,
                        sse_url=url_val,
                        is_active=is_active_val
                    )
                    db.add(db_server)
                    
            # Deactivate servers not present in new whitelist
            for s_name, db_server in existing_map.items():
                if s_name not in new_servers:
                    db_server.is_active = False

            # Invalidate Redis cache for MCP servers
            mcp_cache_key = f"{tenant_uuid}:config:mcp_servers"
            await redis_client.delete(mcp_cache_key)
            logger.info(f"Invalidated MCP servers whitelist cache for {mcp_cache_key}")
        except Exception as e:
            logger.error(f"Error syncing MCP servers whitelist for tenant {tenant_id}: {e}")

        await db.commit()

        if active_keys_before == 0:
            stmt_count_after = select(APIKeyConfig).where(
                APIKeyConfig.tenant_id == tenant_uuid,
                APIKeyConfig.is_active == True
            )
            res_count_after = await db.execute(stmt_count_after)
            active_keys_after = res_count_after.scalars().all()
            if len(active_keys_after) > 0:
                first_active_provider = active_keys_after[0].provider
                from core.dynamic_cost import auto_create_tenant_routes_from_defaults
                await auto_create_tenant_routes_from_defaults(db, tenant_uuid, first_active_provider)

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

