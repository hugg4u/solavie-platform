# Logging & Observability — Comment Manager Service

## Log Format: Structured JSON
```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "info",
  "service": "comment-manager",
  "trace_id": "abc123",
  "tenant_id": "tenant-uuid",
  "message": "Comment classified",
  "context": {
    "comment_id": "comment-uuid",
    "post_id": "post-uuid",
    "platform": "facebook",
    "classification": "question",
    "confidence": 0.91,
    "action_taken": "auto_reply",
    "processing_time_ms": 320
  }
}
```

## Log Levels
| Level | Khi nào | Ví dụ |
|-------|---------|-------|
| ERROR | AI Core classification fail, auto-reply send fail | `"Classification failed: AI Core 503"` |
| WARN | Low classification confidence, override detected | `"Classification overridden: spam → neutral by agent"` |
| INFO | Comment classified, action taken, escalation sent | `"Spam hidden: comment-uuid on post-xyz"` |
| DEBUG | AI prompt/response, classification scores, override learning data | `"Scores: spam=0.12, neg=0.05, question=0.91"` |

## Prometheus Metrics
```typescript
comments_processed_total: Counter [platform, classification]
comments_classification_duration: Histogram []
comments_auto_hidden_total: Counter [platform] // spam auto-hide
comments_auto_replied_total: Counter [platform] // question auto-reply
comments_escalated_total: Counter [platform] // negative → agent
comments_overrides_total: Counter [from_class, to_class] // human corrections
comments_classification_accuracy: Gauge [] // based on override rate
comments_kafka_consumed_total: Counter [topic]
```

## Health Endpoints
```
GET /health   → {"status": "ok"}
GET /ready    → {"status": "ready", "ai_core": "connected", "postgres": "connected", "kafka": "connected"}
GET /metrics  → Prometheus format
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| ClassificationFailing | AI Core errors > 5 in 5m | warning |
| HighOverrideRate | overrides / processed > 20% in 1h | info (model needs retraining) |
| SpamSpike | spam classified > 3x normal rate in 15m | warning |
| EscalationFlood | escalated > 20 in 10m | warning |
