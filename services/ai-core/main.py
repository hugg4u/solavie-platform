import asyncio
import logging
import uuid
from typing import Dict, Any, List
from fastapi import FastAPI, Depends, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
import grpc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from core.config import settings
from db.database import get_db, engine, Base
from db.models import LLMUsageLog, PromptTemplate
from gateway.router import LLMGateway
from agent.orchestrator import AgentOrchestrator

# Try to import grpc definitions
try:
    from proto import ai_core_pb2, ai_core_pb2_grpc
except ImportError:
    import sys
    sys.stderr.write("Warning: proto files not found. Compilation will happen during container run.\n")
    ai_core_pb2 = None
    ai_core_pb2_grpc = None

# Logging setup conforming to specs: structured JSON (simulated via formatting) or standard format
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "category": "%(name)s", "message": "%(message)s"}'
)
logger = logging.getLogger("solavie.ai_core")

app = FastAPI(title="Solavie AI-CORE Service", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

gateway = LLMGateway()
orchestrator = AgentOrchestrator()

@app.on_event("startup")
async def startup_event():
    # Automatically create tables in development if database is empty/fresh
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schemas verified/created successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")
        
    # Start gRPC server in background
    if ai_core_pb2_grpc:
        asyncio.create_task(serve_grpc())
    else:
        logger.warning("gRPC server not started: protobuf modules missing.")

# REST Endpoints
@app.post("/api/v1/completions")
async def completions(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    x_tenant_id: str | None = Header(None)
):
    tenant_id = x_tenant_id or payload.get("tenant_id") or "default-tenant"
    use_case = payload.get("use_case", "chatbot")
    messages = payload.get("messages", [])
    system_prompt = payload.get("system_prompt")
    
    try:
        result = await orchestrator.run(
            tenant_id=tenant_id,
            use_case=use_case,
            messages=messages,
            system_prompt=system_prompt
        )
        
        # Log to Database
        usage_log = LLMUsageLog(
            tenant_id=tenant_id,
            use_case=use_case,
            model=result.get("model_used", "routed"),
            provider="multi",
            prompt_tokens=result.get("total_tokens_used", 0) // 2, # simple split estimate
            completion_tokens=result.get("total_tokens_used", 0) // 2,
            cost_usd=result.get("cost_usd", 0.0),
            latency_ms=100, # default or mock
            cache_hit=False,
            is_fallback=False,
            metadata_json=payload.get("metadata", {})
        )
        db.add(usage_log)
        
        return result
    except Exception as e:
        logger.error(f"Completions endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/embeddings")
async def generate_embeddings(payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    # Simulating embedding generation
    texts = payload.get("texts", [])
    tenant_id = payload.get("tenant_id", "default")
    
    embeddings = [[0.01] * 512 for _ in texts]
    return {
        "embeddings": embeddings,
        "usage": {"prompt_tokens": len(texts) * 5, "cost_usd": 0.00001}
    }

@app.post("/api/v1/summarize")
async def summarize_text(payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    text = payload.get("text", "")
    tenant_id = payload.get("tenant_id", "default")
    
    summary = f"Summary of: {text[:100]}..."
    return {
        "summary": summary,
        "usage": {"prompt_tokens": len(text) // 4, "completion_tokens": 20, "cost_usd": 0.00005}
    }

@app.get("/api/v1/models")
async def list_models():
    return {
        "models": [
            {"id": "gpt-4o-mini", "provider": "openai", "use_case": "chatbot"},
            {"id": "claude-3-5-sonnet-20241022", "provider": "anthropic", "use_case": "content_generation"}
        ]
    }

@app.get("/api/v1/usage")
async def get_usage(tenant_id: str = Query(..., alias="tenant_id"), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            func.sum(LLMUsageLog.prompt_tokens).label("prompt"),
            func.sum(LLMUsageLog.completion_tokens).label("completion"),
            func.sum(LLMUsageLog.cost_usd).label("cost")
        ).where(LLMUsageLog.tenant_id == tenant_id)
    )
    row = result.fetchone()
    return {
        "tenant_id": tenant_id,
        "total_prompt_tokens": row.prompt or 0 if row else 0,
        "total_completion_tokens": row.completion or 0 if row else 0,
        "total_cost_usd": float(row.cost or 0.0) if row else 0.0
    }

@app.get("/api/v1/usage/breakdown")
async def get_usage_breakdown(tenant_id: str = Query(..., alias="tenant_id"), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            LLMUsageLog.use_case,
            func.sum(LLMUsageLog.prompt_tokens).label("prompt"),
            func.sum(LLMUsageLog.completion_tokens).label("completion"),
            func.sum(LLMUsageLog.cost_usd).label("cost")
        ).where(LLMUsageLog.tenant_id == tenant_id).group_by(LLMUsageLog.use_case)
    )
    rows = result.fetchall()
    return [
        {
            "use_case": r.use_case,
            "prompt_tokens": r.prompt,
            "completion_tokens": r.completion,
            "cost_usd": float(r.cost)
        } for r in rows
    ]

@app.get("/api/v1/prompts")
async def list_prompts(tenant_id: str = Query(..., alias="tenant_id"), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.tenant_id == tenant_id)
    )
    prompts = result.scalars().all()
    return prompts

@app.post("/api/v1/prompts")
async def create_prompt(payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    prompt = PromptTemplate(
        tenant_id=payload["tenant_id"],
        name=payload["name"],
        use_case=payload["use_case"],
        system_prompt=payload["system_prompt"]
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return prompt

@app.put("/api/v1/prompts/{prompt_id}")
async def update_prompt(prompt_id: str, payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    prompt_uuid = uuid.UUID(prompt_id)
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == prompt_uuid)
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
        
    prompt.system_prompt = payload["system_prompt"]
    prompt.version += 1
    await db.commit()
    return prompt

# gRPC Servicer Implementation
if ai_core_pb2_grpc:
    class AICoreServicer(ai_core_pb2_grpc.AICoreServicer):
        async def Complete(self, request, context):
            # Map gRPC messages to dict format
            messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
            
            try:
                result = await orchestrator.run(
                    tenant_id=request.tenant_id,
                    use_case=request.use_case,
                    messages=messages,
                    system_prompt=request.system_prompt
                )
                
                # Formulate response
                return ai_core_pb2.CompletionResponse(
                    content=result.get("final_response", ""),
                    model_used="routed",
                    confidence=1.0,
                    usage=ai_core_pb2.TokenUsage(
                        prompt_tokens=result.get("total_tokens_used", 0) // 2,
                        completion_tokens=result.get("total_tokens_used", 0) // 2,
                        cost_usd=result.get("cost_usd", 0.0),
                        cache_hit=False
                    )
                )
            except Exception as e:
                logger.error(f"gRPC Complete method failed: {e}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                return ai_core_pb2.CompletionResponse()

        async def Embed(self, request, context):
            embeddings = []
            for _ in request.texts:
                embeddings.append(ai_core_pb2.Embedding(values=[0.01] * 512))
            return ai_core_pb2.EmbedResponse(
                embeddings=embeddings,
                usage=ai_core_pb2.TokenUsage(prompt_tokens=10, cost_usd=0.00001)
            )

        async def Summarize(self, request, context):
            return ai_core_pb2.SummarizeResponse(
                summary=f"Summary of: {request.text[:100]}...",
                usage=ai_core_pb2.TokenUsage(prompt_tokens=10, cost_usd=0.00001)
            )

# gRPC Server function
async def serve_grpc():
    server = grpc.aio.server()
    ai_core_pb2_grpc.add_AICoreServicer_to_server(AICoreServicer(), server)
    server.add_insecure_port("[::]:50051")
    logger.info("Starting gRPC server on [::]:50051")
    await server.start()
    await server.wait_for_termination()
