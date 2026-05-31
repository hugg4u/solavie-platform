# Logging & Observability — Chatbot Service

## Log Format: Structured JSON
```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "info",
  "service": "chatbot",
  "trace_id": "abc123",
  "tenant_id": "tenant-uuid",
  "message": "Response generated",
  "context": {
    "conversation_id": "conv-uuid",
    "intent": "faq",
    "sentiment": "neutral",
    "confidence": 0.85,
    "action": "reply",
    "language": "vi",
    "latency_ms": 1200,
    "model_used": "gpt-4o-mini",
    "rag_docs_found": 3
  }
}
```

## Log Levels
| Level | Khi nào | Ví dụ |
|-------|---------|-------|
| ERROR | AI Core timeout, Knowledge Base unreachable, LangGraph error | `"AI Core gRPC timeout: 5000ms"` |
| WARN | Low confidence handoff, no RAG docs found, retry | `"Handoff: confidence 0.42, no relevant docs"` |
| INFO | Intent classified, response generated, handoff executed | `"Reply sent: faq, confidence 0.85, 1200ms"` |
| DEBUG | Full prompt, RAG documents, LangGraph state transitions | `"Graph state: classify → retrieve → generate"` |

## OpenTelemetry: Python setup (same as AI Core)

## Trace Spans
```
[gRPC ProcessMessage] (root)
├── [classify_intent] — 300ms (parallel with embed)
├── [embed_query] — 100ms (parallel with classify)
├── [retrieve_knowledge] — 50ms
│   └── [http_call_knowledge_base] — 40ms
├── [generate_response] — 1200ms
│   └── [grpc_call_ai_core] — 1100ms
├── [score_confidence] — 5ms
├── [decide_action] — 1ms
└── [save_checkpoint] — 5ms (PostgreSQL)
```

## Prometheus Metrics
```python
# Request metrics
chatbot_requests_total: Counter ['tenant_id', 'intent', 'action'] # action: reply/handoff/clarify
chatbot_request_duration: Histogram ['intent']
chatbot_e2e_latency: Histogram [] # Full end-to-end (target < 2s)

# Intent distribution
chatbot_intent_total: Counter ['intent'] # faq/sales/support/complaint/chitchat

# Confidence
chatbot_confidence_score: Histogram [buckets: 0.0-1.0 step 0.1]
chatbot_handoff_total: Counter ['reason'] # low_confidence/sentiment/timeout

# Sentiment
chatbot_sentiment_total: Counter ['sentiment'] # positive/neutral/negative/angry

# RAG
chatbot_rag_docs_found: Histogram [] # How many relevant docs found
chatbot_rag_no_results_total: Counter [] # Queries with 0 results

# Language
chatbot_language_total: Counter ['language'] # vi/en/other

# LangGraph
chatbot_graph_steps_total: Counter ['node'] # classify/retrieve/generate/handoff
chatbot_checkpoint_saves_total: Counter []
```

## Health Endpoints
```
GET /health   → {"status": "ok"}
GET /ready    → {"status": "ready", "ai_core_grpc": "connected", "knowledge_base": "connected", "postgres": "connected"}
GET /metrics  → Prometheus format
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| AICoreUnreachable | grpc errors > 5 in 1m | critical |
| HighLatency | e2e_latency p95 > 3s | warning |
| HighHandoffRate | handoff / requests > 50% in 30m | warning |
| NoRAGResults | rag_no_results > 20% in 15m | warning |
| SentimentSpike | sentiment{angry} rate spike > 3x | info |
