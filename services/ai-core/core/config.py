from pydantic import model_validator
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
