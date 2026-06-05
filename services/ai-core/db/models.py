import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Numeric, Boolean, JSON, DateTime, Uuid, UniqueConstraint
from db.database import Base

class LLMUsageLog(Base):
    __tablename__ = "llm_usage_logs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid, nullable=False, index=True)
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
    tenant_id = Column(Uuid, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    use_case = Column(String(50), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    system_prompt = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    ab_test_weight = Column(Numeric(3, 2), default=0.0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class LLMRouteConfig(Base):
    __tablename__ = "llm_route_configs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    use_case = Column(String(50), nullable=False)
    tenant_id = Column(Uuid, nullable=False, index=True)
    primary_model = Column(String(100), nullable=False)
    fallback_model = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=False)
    fallback_provider = Column(String(50), nullable=False)
    temperature = Column(Numeric(3, 2), default=0.3)
    max_tokens = Column(Integer, default=300)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('use_case', 'tenant_id', name='uq_use_case_tenant'),
    )

class APIKeyConfig(Base):
    __tablename__ = "api_key_configs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id = Column(Uuid, nullable=False, index=True)
    provider = Column(String(50), nullable=False)
    api_key_encrypted = Column(String, nullable=False)
    api_base = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('tenant_id', 'provider', name='uq_tenant_provider'),
    )


class SystemDefaultRouteConfig(Base):
    __tablename__ = "system_default_route_configs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False)
    use_case = Column(String(50), nullable=False)
    primary_model = Column(String(100), nullable=False)
    fallback_model = Column(String(100), nullable=True)
    temperature = Column(Numeric(3, 2), default=0.3)
    max_tokens = Column(Integer, default=300)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('provider', 'use_case', name='uq_provider_use_case_default'),
    )

