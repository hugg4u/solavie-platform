import logging
import uuid
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

import litellm
from api.deps import get_db, get_effective_tenant, require_permission
from schemas.completions import CompletionRequest, EmbedRequest, SummarizeRequest
from db.models import LLMUsageLog
from agent.orchestrator import AgentOrchestrator
from gateway.router import LLMGateway, format_litellm_model

logger = logging.getLogger("solavie.ai_core.api.completions")
router = APIRouter()
orchestrator = AgentOrchestrator()
gateway = LLMGateway()

from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from core.redis_client import redis_client
from core.metrics import ai_core_cost_alerts_total
import json

async def check_and_trigger_cost_alert(tenant_uuid: uuid.UUID, db: AsyncSession):
    """
    AC 5.4: Monitor accumulated 30-day LLM cost for the tenant, compare it with 
    their cost limit config, and trigger system alerts if usage is >= threshold.
    """
    import time
    tenant_str = str(tenant_uuid)
    now = time.time()
    limits_json = None
    
    # 1. Get tenant limits config from Local Memory Cache of gateway or Redis
    if tenant_str in gateway._local_limits_cache:
        cache_data = gateway._local_limits_cache[tenant_str]
        if now < cache_data["expires_at"]:
            limits_json = cache_data["data"]

    if limits_json is None:
        try:
            limits_raw = await redis_client.get(f"tenant:{tenant_uuid}:limits")
            if limits_raw:
                val_str = limits_raw.decode("utf-8") if isinstance(limits_raw, bytes) else limits_raw
                limits_json = json.loads(val_str)
                gateway._local_limits_cache[tenant_str] = {
                    "data": limits_json,
                    "expires_at": now + 10.0
                }
        except Exception as re:
            logger.error(f"Cost Alert: Redis error reading limits: {re}")
            if tenant_str in gateway._local_limits_cache:
                limits_json = gateway._local_limits_cache[tenant_str]["data"]

    if not limits_json:
        logger.info(f"Cost Alert: No limit configured or error reading limits for tenant {tenant_uuid}. Skipping check.")
        return
        
    try:
        cost_limit = limits_json.get("cost_limit_usd")
        if cost_limit is None:
            logger.info(f"Cost Alert: Limit is null (unlimited) for tenant {tenant_uuid}. Skipping check.")
            return
            
        cost_limit = float(cost_limit)
        warning_threshold = float(limits_json.get("cost_alert_threshold_percent", 80))
        cost_policy = limits_json.get("cost_limit_policy", "notify_only")

        # 2. Calculate 30-day accumulated cost
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        stmt = select(func.sum(LLMUsageLog.cost_usd)).where(
            LLMUsageLog.tenant_id == tenant_uuid,
            LLMUsageLog.created_at >= cutoff
        )
        result = await db.execute(stmt)
        total_cost = float(result.scalar() or 0.0)

        # 3. Update Redis accumulated cost cache (10s TTL)
        try:
            await redis_client.setex(f"tenant:{tenant_uuid}:accumulated_cost", 10, str(total_cost))
        except Exception as re:
            logger.error(f"Failed to set accumulated cost in Redis for alert: {re}")
            
        # Update Local Cache
        gateway._local_accumulated_cost_cache[tenant_str] = {
            "data": total_cost,
            "expires_at": now + 10.0
        }
        
        # 4. Check warning threshold
        if total_cost >= (warning_threshold / 100.0) * cost_limit:
            tier = "standard"
            try:
                tier_bytes = await redis_client.get(f"tenant:{tenant_uuid}:tier")
                if tier_bytes:
                    tier = tier_bytes.decode("utf-8").strip().lower()
            except Exception as re:
                logger.error(f"Cost Alert: Error reading tier from Redis: {re}")
                
            logger.warning(
                f"[Cost Alert] Tenant {tenant_uuid} (tier: {tier}) has reached "
                f"{total_cost/cost_limit:.1%} of their 30-day cost limit: "
                f"{total_cost:.4f} / {cost_limit:.2f} USD (Policy: {cost_policy})"
            )
            # Increment Prometheus counter
            ai_core_cost_alerts_total.labels(tenant_id=str(tenant_uuid), tier=tier).inc()
            
    except Exception as e:
        logger.error(f"Error in cost alert verification: {e}")




@router.post("/completions")
async def completions(
    request: CompletionRequest,
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None),
    user_permissions_csv: str = Depends(require_permission("ai-core:chats:create"))
):
    tenant_uuid = get_effective_tenant(x_tenant_id, request.tenant_id)
    use_case = request.use_case or "chatbot"
    messages_list = [{"role": msg.role, "content": msg.content} for msg in request.messages]
    user_perms = [p.strip() for p in user_permissions_csv.split(",") if p.strip()]
    
    try:
        result = await orchestrator.run(
            tenant_id=str(tenant_uuid),
            use_case=use_case,
            messages=messages_list,
            system_prompt=request.system_prompt,
            user_permissions=user_perms
        )
        
        # Log to Database
        usage_log = LLMUsageLog(
            tenant_id=tenant_uuid,
            use_case=use_case,
            model=result.get("model_used", "routed"),
            provider=result.get("provider", "openai"),
            prompt_tokens=result.get("prompt_tokens", 0),
            completion_tokens=result.get("completion_tokens", 0),
            cost_usd=result.get("cost_usd", 0.0),
            latency_ms=result.get("latency_ms", 0),
            cache_hit=result.get("cache_hit", False),
            is_fallback=result.get("is_fallback", False),
            metadata_json=request.metadata or {}
        )
        db.add(usage_log)
        await db.commit()
        
        # Trigger Cost Alert Check (AC 5.4)
        await check_and_trigger_cost_alert(tenant_uuid, db)
        
        return result
    except ValueError as e:
        logger.warning(f"Validation/Configuration error: {e}")
        if "LLM usage limit exceeded" in str(e):
            raise HTTPException(status_code=429, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Completions endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/embeddings")
async def generate_embeddings(
    request: EmbedRequest,
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None),
    user_permissions_csv: str = Depends(require_permission("ai-core:chats:create"))
):
    tenant_uuid = get_effective_tenant(x_tenant_id, request.tenant_id)
    model = request.model or "text-embedding-3-small"
    
    # Check cost limit first
    await gateway.check_cost_limit(str(tenant_uuid))
    
    # Determine provider (default to openai for text-embedding)
    provider = "openai"
    if "cohere" in model.lower():
        provider = "cohere"
        
    try:
        creds = await gateway.get_provider_credentials(str(tenant_uuid), provider)
        
        call_kwargs = {
            "model": model,
            "input": request.texts,
        }
        if request.dimensions:
            call_kwargs["dimensions"] = request.dimensions
        if creds.get("api_key"):
            call_kwargs["api_key"] = creds["api_key"]
        if creds.get("api_base"):
            call_kwargs["api_base"] = creds["api_base"]
            
        response = await litellm.aembedding(**call_kwargs)
        
        # Calculate cost
        try:
            from litellm import completion_cost
            cost = completion_cost(completion_response=response)
        except Exception:
            cost = 0.0
            
        embeddings = [item["embedding"] for item in response["data"]]
        prompt_tokens = response.get("usage", {}).get("prompt_tokens", 0)
        
        return {
            "embeddings": embeddings,
            "usage": {"prompt_tokens": prompt_tokens, "cost_usd": cost}
        }
    except ValueError as e:
        logger.warning(f"Validation/Configuration error in embeddings: {e}")
        if "LLM usage limit exceeded" in str(e):
            raise HTTPException(status_code=429, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Embeddings API error: {e}")
        # Fail-safe local mock fallback if API key is not active/provided yet
        embeddings = [[0.01] * (request.dimensions or 512) for _ in request.texts]
        return {
            "embeddings": embeddings,
            "usage": {"prompt_tokens": len(request.texts) * 5, "cost_usd": 0.00001},
            "warning": f"Mock fallback triggered due to exception: {str(e)}"
        }

@router.post("/summarize")
async def summarize_text(
    request: SummarizeRequest,
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None),
    user_permissions_csv: str = Depends(require_permission("ai-core:chats:create"))
):
    tenant_uuid = get_effective_tenant(x_tenant_id, request.tenant_id)
    
    try:
        # We use LLMGateway routing for 'summarization' usecase
        route = await gateway.get_routing(str(tenant_uuid), "summarization")
        provider = route["provider"]
        model = format_litellm_model(route["primary_model"], provider)
        
        creds = await gateway.get_provider_credentials(str(tenant_uuid), provider)
        
        max_len = request.max_length or route.get("max_tokens", 200)
        
        call_kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"You are a summarization assistant. Summarize the text to a maximum of {max_len} characters/words. Keep it concise."},
                {"role": "user", "content": request.text}
            ],
            "max_tokens": max_len,
            "temperature": 0.3
        }
        if creds.get("api_key"):
            call_kwargs["api_key"] = creds["api_key"]
        if creds.get("api_base"):
            call_kwargs["api_base"] = creds["api_base"]

        # Strategy Pattern: Use ProviderAdapter to clean up parameters dynamically
        from gateway.providers.factory import ProviderFactory
        adapter = ProviderFactory.get_adapter(provider)
        call_kwargs = adapter.sanitize_payload(call_kwargs)

        response = await litellm.acompletion(**call_kwargs)
        summary = response.choices[0].message.content or ""
        
        prompt_tokens = response.usage.prompt_tokens if hasattr(response, "usage") else 0
        completion_tokens = response.usage.completion_tokens if hasattr(response, "usage") else 0
        
        try:
            from litellm import completion_cost
            cost = completion_cost(completion_response=response)
        except Exception:
            cost = 0.0
            
        return {
            "summary": summary,
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "cost_usd": cost}
        }
    except ValueError as e:
        logger.warning(f"Validation/Configuration error in summarize: {e}")
        if "LLM usage limit exceeded" in str(e):
            raise HTTPException(status_code=429, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Summarization API error: {e}")
        # Fail-safe local mock fallback
        summary = f"Summary of: {request.text[:100]}..."
        return {
            "summary": summary,
            "usage": {"prompt_tokens": len(request.text) // 4, "completion_tokens": 20, "cost_usd": 0.00005},
            "warning": f"Mock fallback triggered due to exception: {str(e)}"
        }

from core.providers import PROVIDERS_REGISTRY, PROVIDER_ALIASES

@router.get("/models")
async def list_models(
    user_permissions_csv: str = Depends(require_permission("ai-core:configs:read"))
):
    """
    Returns a dynamic list of chat models across the 12 supported providers from LiteLLM registry.
    """
    SUPPORTED_PROVIDERS = set(PROVIDERS_REGISTRY.keys())
    
    pricing_registry = getattr(litellm, "model_cost", getattr(litellm, "model_prices_and_context_window", {}))
    models_dict = {}
    
    # 1. Scan LiteLLM registry
    for model_name, info in pricing_registry.items():
        if not isinstance(info, dict):
            continue
        
        # We only want chat mode models
        if info.get("mode") != "chat":
            continue
            
        provider = info.get("litellm_provider", "").lower() or info.get("provider", "").lower()
        if not provider:
            continue
            
        # Normalize provider name using dynamic aliases configured in JSON
        provider = provider.strip().lower()
        provider = PROVIDER_ALIASES.get(provider, provider)
            
        if provider not in SUPPORTED_PROVIDERS:
            continue
            
        # Key model list by (provider, model_name) to avoid duplicates
        models_dict[(provider, model_name)] = {
            "id": model_name,
            "provider": provider
        }
        
    # 2. Add local defaults if not already present
    local_defaults = [
        {"id": "qwen2.5-coder", "provider": "local"},
        {"id": "llama3", "provider": "local"},
    ]
    for ld in local_defaults:
        key = (ld["provider"], ld["id"])
        if key not in models_dict:
            models_dict[key] = ld
            
    # 3. Sort by provider then model ID
    sorted_models = sorted(models_dict.values(), key=lambda x: (x["provider"], x["id"]))
    
    return {"models": sorted_models}
