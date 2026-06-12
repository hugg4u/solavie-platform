from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    
    # DB Configuration
    AI_CORE_DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres_master_password@localhost:5432/postgres"
    
    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379/1"
    REDIS_STACK_URL: str = "redis://localhost:6399/0"
    SEMANTIC_CACHE_THRESHOLD: float = 0.92
    SEMANTIC_CACHE_TTL: int = 86400
    
    # Provider Keys
    TAVILY_API_KEY: str | None = None

    
    # Encryption & Sync Configuration
    ENCRYPTION_SECRET_KEY: str | None = "solavie_super_secret_master_key_change_me_in_production"
    TENANT_CONFIG_SERVICE_URL: str = "http://tenant-config-service:3006"
    KAFKA_BROKERS: str = "localhost:9092"

    
    # External Service URLs
    TAVILY_API_URL: str = "https://api.tavily.com/search"
    JINA_READER_URL: str = "https://r.jina.ai"
    SOCIAL_TRENDS_API_URL: str = "https://api.socialtrends.mock/trends"

    # Internal Service URLs
    KNOWLEDGE_BASE_SERVICE_URL: str = "http://knowledge-base:8004/api/v1"
    MESSAGING_SERVICE_URL: str = "http://messaging:8002/api/v1"
    ANALYTICS_SERVICE_URL: str = "http://analytics:8005/api/v1"
    CRM_SERVICE_URL: str = "http://crm:8003/api/v1"
    SCHEDULER_SERVICE_URL: str = "http://scheduler:8007/api/v1"
    COMMENT_MANAGER_SERVICE_URL: str = "http://comment-manager:8008/api/v1"
    NOTIFICATION_SERVICE_URL: str = "http://notification:8009/api/v1"
    CONTENT_SERVICE_URL: str = "http://content:8010/api/v1"
    
    # CORS Configuration
    CORS_ALLOWED_ORIGINS: list[str] = ["http://localhost:8006", "http://localhost:3000"]
    
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

    @model_validator(mode="after")
    def validate_production_keys(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            if (
                not self.ENCRYPTION_SECRET_KEY 
                or self.ENCRYPTION_SECRET_KEY == "solavie_super_secret_master_key_change_me_in_production"
            ):
                raise ValueError("ENCRYPTION_SECRET_KEY must be changed from the default value in production environment.")
        return self

settings = Settings()
