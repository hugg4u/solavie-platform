import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    
    # DB Configuration
    AI_CORE_DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres_master_password@localhost:5432/postgres"
    
    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379/1"
    
    # Provider Keys
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    TAVILY_API_KEY: str | None = None
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
