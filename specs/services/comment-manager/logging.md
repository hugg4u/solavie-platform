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
| ERROR | Security shared secret configuration missing | `"GATEWAY_SIGNING_SECRET is not configured"` |
| ERROR | AI Core classification fail, auto-reply send fail | `"Classification failed: AI Core 503"` |
| WARN | Signature validation failure, permission denied, unauthorized access attempt | `"HMAC signature verification failed: signature mismatch"` |
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

// Model Context Protocol (MCP) Metrics
comments_mcp_connections_active: Gauge [tenant_id]
comments_mcp_requests_total: Counter [tool_name, status] // status: success/error
comments_mcp_execution_duration_seconds: Histogram [tool_name]
```


// Zero-Trust Security Metrics
comment_manager_security_signature_failures_total: Counter [tenant_id, client_ip]
comment_manager_security_permission_denied_total: Counter [tenant_id, required_permission]

## Health Endpoints
```
GET /health   → {"status": "ok"}
GET /ready    → {"status": "ready", "ai_core": "connected", "postgres": "connected", "kafka": "connected"}
GET /metrics  → Prometheus format
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| HighSignatureFailures | sum(rate(comment_manager_security_signature_failures_total[5m])) > 5 | critical (potential spoofing attempt or key mismatch) |
| HighPermissionDenied | sum(rate(comment_manager_security_permission_denied_total[5m])) > 10 | warning (user accessing forbidden resources) |
| ClassificationFailing | AI Core errors > 5 in 5m | warning |
| HighOverrideRate | overrides / processed > 20% in 1h | info (model needs retraining) |
| SpamSpike | spam classified > 3x normal rate in 15m | warning |
| EscalationFlood | escalated > 20 in 10m | warning |
