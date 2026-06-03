import logging
import uuid
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, get_effective_tenant
from schemas.completions import CompletionRequest, EmbedRequest, SummarizeRequest
from db.models import LLMUsageLog
from agent.orchestrator import AgentOrchestrator

logger = logging.getLogger("solavie.ai_core.api.completions")
router = APIRouter()
orchestrator = AgentOrchestrator()

@router.post("/completions")
async def completions(
    request: CompletionRequest,
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None)
):
    tenant_uuid = get_effective_tenant(x_tenant_id, request.tenant_id)
    use_case = request.use_case or "chatbot"
    messages_list = [{"role": msg.role, "content": msg.content} for msg in request.messages]
    
    try:
        result = await orchestrator.run(
            tenant_id=str(tenant_uuid),
            use_case=use_case,
            messages=messages_list,
            system_prompt=request.system_prompt
        )
        
        # Log to Database
        usage_log = LLMUsageLog(
            tenant_id=tenant_uuid,
            use_case=use_case,
            model=result.get("model_used", "routed"),
            provider=result.get("provider", "openai"),
            prompt_tokens=result.get("total_tokens_used", 0) // 2,
            completion_tokens=result.get("total_tokens_used", 0) // 2,
            cost_usd=result.get("cost_usd", 0.0),
            latency_ms=100,
            cache_hit=False,
            is_fallback=result.get("is_fallback", False),
            metadata_json=request.metadata or {}
        )
        db.add(usage_log)
        await db.commit()
        
        return result
    except Exception as e:
        logger.error(f"Completions endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/embeddings")
async def generate_embeddings(
    request: EmbedRequest,
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None)
):
    tenant_uuid = get_effective_tenant(x_tenant_id, request.tenant_id)
    embeddings = [[0.01] * 512 for _ in request.texts]
    return {
        "embeddings": embeddings,
        "usage": {"prompt_tokens": len(request.texts) * 5, "cost_usd": 0.00001}
    }

@router.post("/summarize")
async def summarize_text(
    request: SummarizeRequest,
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None)
):
    tenant_uuid = get_effective_tenant(x_tenant_id, request.tenant_id)
    summary = f"Summary of: {request.text[:100]}..."
    return {
        "summary": summary,
        "usage": {"prompt_tokens": len(request.text) // 4, "completion_tokens": 20, "cost_usd": 0.00005}
    }

@router.get("/models")
async def list_models():
    return {
        "models": [
            {"id": "gpt-4o-mini", "provider": "openai", "use_case": "chatbot"},
            {"id": "gpt-4o", "provider": "openai", "use_case": "content_generation"},
            {"id": "claude-3-5-sonnet-20241022", "provider": "anthropic", "use_case": "content_generation"},
            {"id": "claude-3-haiku-20240307", "provider": "anthropic", "use_case": "chatbot"}
        ]
    }
