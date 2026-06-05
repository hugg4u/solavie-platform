"""
AI-CORE Service — FastAPI application entry point.

Responsibilities:
  - FastAPI app initialization and CORS configuration.
  - System endpoints: /health, /ready, /metrics.
  - Mount versioned API routers from api/v1/.
  - Start background tasks: sync_listener_loop and gRPC server.

All business-logic endpoints live in api/v1/endpoints/.
All gRPC logic lives in grpc_server/.
"""

import asyncio
import logging
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import os
from fastapi.staticfiles import StaticFiles

from core.config import settings
from db.database import engine, Base
from core.sync_listener import sync_listener_loop
from core.dynamic_cost import dynamic_cost_sync_loop
from api.v1.router import api_router

logger = logging.getLogger("solavie.ai_core")

app = FastAPI(title="Solavie AI-CORE Service", version="1.0.0")

# ── Mount static folder for test UI ──
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/ui", StaticFiles(directory=static_dir, html=True), name="static")

# ── CORS middleware ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount versioned API router ──
app.include_router(api_router, prefix="/api/v1")


# ── Startup lifecycle ──
@app.on_event("startup")
async def startup_event():
    # 1. Auto-create tables in dev if DB is fresh
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schemas verified/created successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")

    # 2. Start config sync background listener
    asyncio.create_task(sync_listener_loop())

    # 3. Start dynamic cost synchronization loop (AC 2.8)
    asyncio.create_task(dynamic_cost_sync_loop())

    # 4. Start gRPC server on port 50052
    try:
        from grpc_server.server import serve_grpc
        asyncio.create_task(serve_grpc())
    except ImportError:
        logger.warning("gRPC server not started: grpc_server module or proto stubs missing.")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutdown initiated.")
    
    # Explicitly close Redis connection to avoid 'Event loop is closed' RuntimeError
    try:
        from core.redis_client import redis_client
        await redis_client.aclose()
        logger.info("Redis connection closed successfully.")
    except Exception as e:
        logger.error(f"Error closing Redis client on shutdown: {e}")
        
    try:
        from grpc_server.server import stop_grpc
        await stop_grpc()
    except Exception as e:
        logger.error(f"Error stopping gRPC server on shutdown: {e}")


# ── System endpoints ──
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/ready")
async def ready_check():
    try:
        async with engine.connect() as conn:
            await conn.execute(select(1))
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database not ready: {str(e)}")


@app.get("/metrics")
async def metrics_endpoint():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
