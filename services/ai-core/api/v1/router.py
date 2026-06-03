from fastapi import APIRouter
from api.v1.endpoints.completions import router as completions_router
from api.v1.endpoints.configs import router as configs_router
from api.v1.endpoints.analytics import router as analytics_router

api_router = APIRouter()

api_router.include_router(completions_router)
api_router.include_router(configs_router)
api_router.include_router(analytics_router)
