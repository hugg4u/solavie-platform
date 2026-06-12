from pydantic import BaseModel, Field
from typing import Optional, Literal
from uuid import UUID
from datetime import datetime

class CostSimulationPayload(BaseModel):
    tenant_id: Optional[str] = Field(None, description="Tenant ID (optional if X-Tenant-ID header is used)")
    new_model: str = Field(..., description="Target model ID to simulate costs (e.g. gpt-4o-mini, gpt-4o, claude-3-5-sonnet-20241022)")

class ConversationEvent(BaseModel):
    event_id: UUID = Field(..., description="Unique event identifier (UUID)")
    tenant_id: str = Field(..., description="Tenant identifier")
    conversation_id: str = Field(..., description="Conversation identifier")
    user_query: str = Field(..., description="Original query from user")
    standalone_query: str = Field(..., description="Query after rewrite (standalone query)")
    query_rewritten: bool = Field(..., description="True if query was rewritten")
    rag_similarity_score: float = Field(0.0, description="Max similarity score from Knowledge Base search")
    rag_docs_count: int = Field(0, description="Number of retrieved documents from Knowledge Base")
    nli_grounding_score: float = Field(0.0, description="NLI grounding verification score")
    confidence_score: float = Field(0.0, description="Overall confidence score of the answer")
    chatbot_action: Literal["reply", "handoff", "clarify", "lead_capture"] = Field("reply", description="Action taken by the chatbot")
    handoff_reason: Optional[str] = Field(None, description="Reason for handoff if chatbot_action is handoff")
    cache_hit: bool = Field(False, description="True if semantic cache was hit")
    model_used: str = Field(..., description="LLM Model used for completion")
    latency_ms: int = Field(..., description="Inference latency in milliseconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="UTC Timestamp of the event")
