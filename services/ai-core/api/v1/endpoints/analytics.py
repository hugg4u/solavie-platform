import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from api.deps import get_db, get_effective_tenant, require_permission
from schemas.analytics import CostSimulationPayload
from db.models import LLMUsageLog

logger = logging.getLogger("solavie.ai_core.api.analytics")
router = APIRouter()
import litellm


@router.get("/usage")
async def get_usage(
    tenant_id: str | None = Query(None, alias="tenant_id"),
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None),
    user_permissions_csv: str = Depends(require_permission("ai-core:analytics:read"))
):
    tenant_uuid = get_effective_tenant(x_tenant_id, tenant_id)

    result = await db.execute(
        select(
            func.sum(LLMUsageLog.prompt_tokens).label("prompt"),
            func.sum(LLMUsageLog.completion_tokens).label("completion"),
            func.sum(LLMUsageLog.cost_usd).label("cost")
        ).where(LLMUsageLog.tenant_id == tenant_uuid)
    )
    row = result.fetchone()
    return {
        "tenant_id": str(tenant_uuid),
        "total_prompt_tokens": row.prompt or 0 if row else 0,
        "total_completion_tokens": row.completion or 0 if row else 0,
        "total_cost_usd": float(row.cost or 0.0) if row and row.cost is not None else 0.0
    }

@router.get("/usage/breakdown")
async def get_usage_breakdown(
    tenant_id: str | None = Query(None, alias="tenant_id"),
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None),
    user_permissions_csv: str = Depends(require_permission("ai-core:analytics:read"))
):
    tenant_uuid = get_effective_tenant(x_tenant_id, tenant_id)

    result = await db.execute(
        select(
            LLMUsageLog.use_case,
            func.sum(LLMUsageLog.prompt_tokens).label("prompt"),
            func.sum(LLMUsageLog.completion_tokens).label("completion"),
            func.sum(LLMUsageLog.cost_usd).label("cost")
        ).where(LLMUsageLog.tenant_id == tenant_uuid).group_by(LLMUsageLog.use_case)
    )
    rows = result.fetchall()
    return [
        {
            "use_case": r.use_case,
            "prompt_tokens": r.prompt or 0,
            "completion_tokens": r.completion or 0,
            "cost_usd": float(r.cost) if r.cost is not None else 0.0
        } for r in rows
    ]

@router.get("/analytics/usage-summary")
async def usage_summary(
    tenant_id: str | None = Query(None, alias="tenant_id"),
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None),
    user_permissions_csv: str = Depends(require_permission("ai-core:analytics:read"))
):
    tenant_uuid = get_effective_tenant(x_tenant_id, tenant_id)
        
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    result = await db.execute(
        select(
            LLMUsageLog.tenant_id,
            LLMUsageLog.use_case,
            LLMUsageLog.model,
            LLMUsageLog.provider,
            func.sum(LLMUsageLog.prompt_tokens).label("prompt"),
            func.sum(LLMUsageLog.completion_tokens).label("completion"),
            func.sum(LLMUsageLog.cost_usd).label("cost"),
            func.avg(LLMUsageLog.latency_ms).label("latency")
        ).where(
            and_(
                LLMUsageLog.tenant_id == tenant_uuid,
                LLMUsageLog.created_at >= cutoff
            )
        ).group_by(
            LLMUsageLog.tenant_id,
            LLMUsageLog.use_case,
            LLMUsageLog.model,
            LLMUsageLog.provider
        )
    )
    rows = result.fetchall()
    
    total_prompt = 0
    total_completion = 0
    total_cost = 0.0
    total_latency_sum = 0.0
    count = 0
    
    breakdown = []
    for r in rows:
        prompt_val = r.prompt or 0
        completion_val = r.completion or 0
        cost_val = float(r.cost) if r.cost is not None else 0.0
        latency_val = float(r.latency) if r.latency is not None else 0.0
        
        total_prompt += prompt_val
        total_completion += completion_val
        total_cost += cost_val
        total_latency_sum += latency_val
        count += 1
        
        breakdown.append({
            "tenant_id": str(r.tenant_id),
            "use_case": r.use_case,
            "model": r.model,
            "provider": r.provider,
            "prompt_tokens": prompt_val,
            "completion_tokens": completion_val,
            "cost_usd": cost_val,
            "avg_latency_ms": latency_val
        })
        
    avg_latency = total_latency_sum / count if count > 0 else 0.0
    
    return {
        "tenant_id": str(tenant_uuid),
        "days_limit": 30,
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_cost_usd": total_cost,
        "avg_latency_ms": avg_latency,
        "breakdown": breakdown
    }

@router.post("/analytics/simulate-cost")
async def simulate_cost(
    payload: CostSimulationPayload,
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None),
    user_permissions_csv: str = Depends(require_permission("ai-core:analytics:read"))
):
    tenant_uuid = get_effective_tenant(x_tenant_id, payload.tenant_id)
    new_model = payload.new_model
        
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    result = await db.execute(
        select(
            func.sum(LLMUsageLog.prompt_tokens).label("prompt"),
            func.sum(LLMUsageLog.completion_tokens).label("completion"),
            func.sum(LLMUsageLog.cost_usd).label("cost")
        ).where(
            and_(
                LLMUsageLog.tenant_id == tenant_uuid,
                LLMUsageLog.created_at >= cutoff
            )
        )
    )
    row = result.fetchone()
    
    prompt_tokens = row.prompt or 0 if row else 0
    completion_tokens = row.completion or 0 if row else 0
    historical_cost = float(row.cost) if row and row.cost is not None else 0.0
    
    # Dynamic price lookup from LiteLLM model registry
    model_info = litellm.model_cost.get(new_model)
    if model_info:
        input_price = model_info.get("input_cost_per_token", 1.5e-07)
        output_price = model_info.get("output_cost_per_token", 6.0e-07)
    else:
        from gateway.router import LLMGateway
        gateway = LLMGateway()
        fallback_model = gateway._get_cheapest_model_from_registry("openai")
        logger.warning(f"Model '{new_model}' not found in LiteLLM registry. Using fallback '{fallback_model}' pricing.")
        fallback_info = litellm.model_cost.get(fallback_model, {})
        input_price = fallback_info.get("input_cost_per_token", 1.5e-07)
        output_price = fallback_info.get("output_cost_per_token", 6.0e-07)
        
    simulated_input_cost = prompt_tokens * input_price
    simulated_output_cost = completion_tokens * output_price
    simulated_cost = simulated_input_cost + simulated_output_cost
    
    return {
        "tenant_id": str(tenant_uuid),
        "historical_cost_30d": historical_cost,
        "simulated_cost_30d": simulated_cost,
        "estimated_savings_30d": historical_cost - simulated_cost,
        "simulated_model": new_model
    }
