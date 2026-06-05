# Logging & Observability — Notification Service

## Log Format: Structured JSON
```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "info",
  "service": "notification",
  "trace_id": "abc123",
  "tenant_id": "tenant-uuid",
  "message": "Notification delivered",
  "context": {
    "notification_id": "notif-uuid",
    "user_id": "user-uuid",
    "type": "handoff",
    "channel": "slack",
    "priority": "critical",
    "delivery_time_ms": 850
  }
}
```

## Log Levels
| Level | Khi nào | Ví dụ |
|-------|---------|-------|
| ERROR | All delivery channels failed, Slack/email API down | `"Delivery failed: slack 503, email timeout, push rejected"` |
| WARN | Primary channel failed (fallback used), quiet hours skipped for critical | `"Slack failed, fallback to email"` |
| INFO | Notification sent, delivered, read | `"Handoff notification delivered via slack in 850ms"` |
| DEBUG | Preference lookup, channel selection logic, retry details | `"User prefs: slack=true, email=true, quiet=22:00-08:00"` |

## Prometheus Metrics
```typescript
notifications_sent_total: Counter [type, channel, priority, status] // status: delivered/failed
notifications_delivery_duration: Histogram [channel, priority]
notifications_retry_total: Counter [channel]
notifications_quiet_hours_skipped: Counter [] // critical notifications during quiet hours
notifications_kafka_consumed_total: Counter [topic]
notifications_unread: Gauge [tenant_id]

// SLA tracking
notifications_sla_met_total: Counter [priority] // delivered within SLA
notifications_sla_breached_total: Counter [priority] // exceeded SLA

// Model Context Protocol (MCP) Metrics
notifications_mcp_connections_active: Gauge [tenant_id]
notifications_mcp_requests_total: Counter [tool_name, status] // status: success/error
notifications_mcp_execution_duration_seconds: Histogram [tool_name]
```

## Health Endpoints
```
GET /health   → {"status": "ok"}
GET /ready    → {"status": "ready", "slack": "connected", "email": "configured", "kafka": "connected"}
GET /metrics  → Prometheus format
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| DeliveryFailureHigh | sent{status=failed} > 10% in 5m | critical |
| HandoffSLABreach | sla_breached{priority=critical} > 0 | critical |
| SlackAPIDown | slack delivery errors > 5 in 2m | warning |
| EmailBounceHigh | email bounces > 5% | warning |
