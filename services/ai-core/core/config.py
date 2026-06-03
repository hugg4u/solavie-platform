from pydantic_settings import BaseSettings, SettingsConfigDict

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
    
    # Encryption & Sync Configuration
    ENCRYPTION_SECRET_KEY: str | None = "solavie_super_secret_master_key_change_me_in_production"
    TENANT_CONFIG_SERVICE_URL: str = "http://localhost:3006"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

settings = Settings()
