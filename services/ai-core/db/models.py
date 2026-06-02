import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Numeric, Boolean, JSON, DateTime, Uuid
from db.database import Base

class LLMUsageLog(Base):
    __tablename__ = "llm_usage_logs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(50), nullable=False, index=True)
    use_case = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=False)
    prompt_tokens = Column(Integer, nullable=False)
    completion_tokens = Column(Integer, nullable=False)
    cost_usd = Column(Numeric(10, 6), nullable=False)
    latency_ms = Column(Integer, nullable=False)
    cache_hit = Column(Boolean, default=False)
    is_fallback = Column(Boolean, default=False)
    metadata_json = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(50), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    use_case = Column(String(50), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    system_prompt = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
