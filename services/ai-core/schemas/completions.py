from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the message author (system, user, assistant, tool, context)")
    content: str = Field(..., max_length=50000, description="The content of the message")

class CompletionRequest(BaseModel):
    tenant_id: Optional[str] = Field(None, description="Tenant ID (optional if X-Tenant-ID header is used)")
    use_case: Optional[str] = Field("chatbot", description="Use case name (e.g., chatbot, content_generation)")
    messages: List[ChatMessage] = Field(..., max_length=100, description="List of messages in the conversation history")
    system_prompt: Optional[str] = Field(None, description="Optional override system prompt template")
    max_tokens: Optional[int] = Field(None, description="Optional override max tokens limit")
    temperature: Optional[float] = Field(None, description="Optional override temperature")
    model_override: Optional[str] = Field(None, description="Optional model ID override")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadata dictionary")

class EmbedRequest(BaseModel):
    tenant_id: Optional[str] = Field(None, description="Tenant ID (optional if X-Tenant-ID header is used)")
    texts: List[str] = Field(..., max_length=100, description="List of strings to embed")
    model: Optional[str] = Field("text-embedding-3-small", description="Embedding model name")
    dimensions: Optional[int] = Field(512, description="Target dimensions for embedding")

class SummarizeRequest(BaseModel):
    tenant_id: Optional[str] = Field(None, description="Tenant ID (optional if X-Tenant-ID header is used)")
    text: str = Field(..., max_length=50000, description="Text content to summarize")
    max_length: Optional[int] = Field(None, description="Target maximum length for summary")
