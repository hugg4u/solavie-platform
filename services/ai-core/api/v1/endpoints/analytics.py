import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from api.deps import get_db, get_effective_tenant
from schemas.analytics import CostSimulationPayload
from db.models import LLMUsageLog

logger = logging.getLogger("solavie.ai_core.api.analytics")
router = APIRouter()
import litellm


@router.get("/usage")
async def get_usage(
    tenant_id: str | None = Query(None, alias="tenant_id"),
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None)
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
    x_tenant_id: str | None = Header(None)
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
    x_tenant_id: str | None = Header(None)
):
    tenant_uuid = get_effective_tenant(x_tenant_id, tenant_id)
        
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    result = await db.execute(
        select(
            func.sum(LLMUsageLog.prompt_tokens).label("prompt"),
            func.sum(LLMUsageLog.completion_tokens).label("completion"),
            func.sum(LLMUsageLog.cost_usd).label("cost"),
            func.avg(LLMUsageLog.latency_ms).label("latency")
        ).where(
            and_(
                LLMUsageLog.tenant_id == tenant_uuid,
                LLMUsageLog.created_at >= cutoff
            )
        )
    )
    row = result.fetchone()
    
    return {
        "tenant_id": str(tenant_uuid),
        "days_limit": 30,
        "total_prompt_tokens": row.prompt or 0 if row else 0,
        "total_completion_tokens": row.completion or 0 if row else 0,
        "total_cost_usd": float(row.cost) if row and row.cost is not None else 0.0,
        "avg_latency_ms": float(row.latency) if row and row.latency is not None else 0.0
    }

@router.post("/analytics/simulate-cost")
async def simulate_cost(
    payload: CostSimulationPayload,
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None)
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
