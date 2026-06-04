from pydantic import BaseModel, Field, field_validator
from typing import Optional

class RouteConfigPayload(BaseModel):
    tenant_id: Optional[str] = Field(None, description="Tenant ID (optional if X-Tenant-ID header is used)")
    use_case: str = Field(..., description="Unique name of the use case (e.g. chatbot, content_generation)")
    primary_model: str = Field(..., description="Name of the primary LLM model")
    fallback_model: str = Field(..., description="Name of the fallback LLM model")
    provider: str = Field(..., description="Primary LLM provider (openai, anthropic, google, deepseek, local)")
    fallback_provider: str = Field(..., description="Fallback LLM provider (openai, anthropic, google, deepseek, local)")
    temperature: Optional[float] = Field(0.3, description="Temperature parameter for LLM")
    max_tokens: Optional[int] = Field(300, description="Max tokens limit for completion response")
    is_active: Optional[bool] = Field(True, description="Enable or disable this route config")

    @field_validator("temperature")
    @classmethod
    def validate_temp(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 2.0):
            raise ValueError("Temperature must be between 0.0 and 2.0")
        return v

class APIKeyConfigPayload(BaseModel):
    provider: str = Field(..., description="LLM provider name (openai, anthropic, google, local, etc.)")
    api_key: str = Field(..., description="Raw provider API key to encrypt and store")
    api_base: Optional[str] = Field(None, description="Custom base URL for the API endpoint")
    is_active: Optional[bool] = Field(True, description="Whether the key is active")

class PromptTemplateCreate(BaseModel):
    tenant_id: Optional[str] = Field(None, description="Tenant ID (optional if X-Tenant-ID header is used)")
    name: str = Field(..., description="Name of the prompt template")
    use_case: str = Field(..., description="Associated use case")
    system_prompt: str = Field(..., description="The system prompt content")

class PromptTemplateUpdate(BaseModel):
    system_prompt: str = Field(..., description="The new system prompt content")
