from pydantic import BaseModel, Field, field_validator
from typing import Optional

class CostSimulationPayload(BaseModel):
    tenant_id: Optional[str] = Field(None, description="Tenant ID (optional if X-Tenant-ID header is used)")
    new_model: str = Field(..., description="Target model ID to simulate costs (e.g. gpt-4o-mini, gpt-4o, claude-3-5-sonnet-20241022)")

