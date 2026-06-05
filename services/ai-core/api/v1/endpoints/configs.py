import logging
import uuid
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.deps import get_db, get_effective_tenant
from schemas.configs import RouteConfigPayload, APIKeyConfigPayload, PromptTemplateCreate, PromptTemplateUpdate
from db.models import LLMRouteConfig, APIKeyConfig, PromptTemplate
from core.crypto import encrypt_key
from core.redis_client import redis_client

logger = logging.getLogger("solavie.ai_core.api.configs")
router = APIRouter()

from pydantic import BaseModel, Field

class ABTestConfigPayload(BaseModel):
    ab_test_weight: float = Field(..., ge=0.0, le=1.0, description="Weight for this prompt template in A/B testing (0.0 to 1.0)")

# Routes Config Endpoints
@router.get("/configs/routes")
async def list_routes(
    tenant_id: str | None = Query(None, alias="tenant_id"),
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None)
):
    tenant_uuid = get_effective_tenant(x_tenant_id, tenant_id)
    result = await db.execute(
        select(LLMRouteConfig).where(LLMRouteConfig.tenant_id == tenant_uuid)
    )
    return result.scalars().all()

@router.post("/configs/routes")
async def create_or_update_route(
    payload: RouteConfigPayload,
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None)
):
    tenant_uuid = get_effective_tenant(x_tenant_id, payload.tenant_id)
    
    stmt = select(LLMRouteConfig).where(
        LLMRouteConfig.tenant_id == tenant_uuid,
        LLMRouteConfig.use_case == payload.use_case
    )
    result = await db.execute(stmt)
    route = result.scalar_one_or_none()
    
    if not route:
        route = LLMRouteConfig(
            tenant_id=tenant_uuid,
            use_case=payload.use_case,
            primary_model=payload.primary_model,
            fallback_model=payload.fallback_model,
            provider=payload.provider,
            fallback_provider=payload.fallback_provider,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            is_active=payload.is_active
        )
        db.add(route)
    else:
        route.primary_model = payload.primary_model
        route.fallback_model = payload.fallback_model
        route.provider = payload.provider
        route.fallback_provider = payload.fallback_provider
        route.temperature = payload.temperature
        route.max_tokens = payload.max_tokens
        route.is_active = payload.is_active
        
    await db.commit()
    await db.refresh(route)
    
    # Invalidate Redis cache key
    cache_key = f"{tenant_uuid}:config:llm_model_routing:{payload.use_case}"
    await redis_client.delete(cache_key)
    
    return route

# API Keys Endpoints
@router.get("/configs/keys")
async def list_keys(
    tenant_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None)
):
    tenant_uuid = get_effective_tenant(x_tenant_id, tenant_id)
    result = await db.execute(
        select(APIKeyConfig).where(APIKeyConfig.tenant_id == tenant_uuid)
    )
    keys = result.scalars().all()
    masked = []
    for k in keys:
        masked.append({
            "id": k.id,
            "provider": k.provider,
            "api_base": k.api_base,
            "is_active": k.is_active,
            "api_key_masked": "sk-...xxxx"
        })
    return masked

@router.post("/configs/keys")
async def create_or_update_key(
    payload: APIKeyConfigPayload,
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None)
):
    tenant_uuid = get_effective_tenant(x_tenant_id, None) # API Keys must rely on injected tenant header
    encrypted = encrypt_key(payload.api_key)
    
    # Check count of active keys before saving
    stmt_count = select(APIKeyConfig).where(
        APIKeyConfig.tenant_id == tenant_uuid,
        APIKeyConfig.is_active == True
    )
    res_count = await db.execute(stmt_count)
    active_keys_count = len(res_count.scalars().all())
    
    stmt = select(APIKeyConfig).where(
        APIKeyConfig.tenant_id == tenant_uuid,
        APIKeyConfig.provider == payload.provider
    )
    result = await db.execute(stmt)
    key_config = result.scalar_one_or_none()
    
    is_active_now = payload.is_active if payload.is_active is not None else True
    
    if not key_config:
        key_config = APIKeyConfig(
            tenant_id=tenant_uuid,
            provider=payload.provider,
            api_key_encrypted=encrypted,
            api_base=payload.api_base,
            is_active=is_active_now
        )
        db.add(key_config)
    else:
        key_config.api_key_encrypted = encrypted
        key_config.api_base = payload.api_base
        if payload.is_active is not None:
            key_config.is_active = payload.is_active
        
    await db.commit()
    await db.refresh(key_config)
    
    # Invalidate Redis cache key
    cache_key = f"{tenant_uuid}:config:api_keys:{payload.provider}"
    await redis_client.delete(cache_key)
    
    # Trigger auto-route creation if this is the first active key
    if active_keys_count == 0 and key_config.is_active:
        from core.dynamic_cost import auto_create_tenant_routes_from_defaults
        await auto_create_tenant_routes_from_defaults(db, tenant_uuid, payload.provider)
        
    return {"status": "success", "provider": payload.provider}

# Prompts Endpoints
@router.get("/prompts")
async def list_prompts(
    tenant_id: str | None = Query(None, alias="tenant_id"),
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None)
):
    tenant_uuid = get_effective_tenant(x_tenant_id, tenant_id)
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.tenant_id == tenant_uuid)
    )
    return result.scalars().all()

@router.post("/prompts")
async def create_prompt(
    payload: PromptTemplateCreate,
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None)
):
    tenant_uuid = get_effective_tenant(x_tenant_id, payload.tenant_id)
    prompt = PromptTemplate(
        tenant_id=tenant_uuid,
        name=payload.name,
        use_case=payload.use_case,
        system_prompt=payload.system_prompt,
        ab_test_weight=payload.ab_test_weight or 0.0
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return prompt

@router.put("/prompts/{prompt_id}")
async def update_prompt(
    prompt_id: str,
    payload: PromptTemplateUpdate,
    db: AsyncSession = Depends(get_db)
):
    prompt_uuid = uuid.UUID(prompt_id)
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == prompt_uuid)
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
        
    if payload.system_prompt is not None:
        prompt.system_prompt = payload.system_prompt
    if payload.ab_test_weight is not None:
        prompt.ab_test_weight = payload.ab_test_weight
        
    prompt.version += 1
    await db.commit()
    return prompt

@router.post("/prompts/{prompt_id}/ab-test")
async def configure_ab_test(
    prompt_id: str,
    payload: ABTestConfigPayload,
    db: AsyncSession = Depends(get_db)
):
    prompt_uuid = uuid.UUID(prompt_id)
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == prompt_uuid)
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
        
    prompt.ab_test_weight = payload.ab_test_weight
    await db.commit()
    await db.refresh(prompt)
    return prompt
