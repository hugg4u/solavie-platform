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
| ERROR | Security shared secret configuration missing | `"GATEWAY_SIGNING_SECRET is not configured"` |
| ERROR | All delivery channels failed, Slack/email API down | `"Delivery failed: slack 503, email timeout, push rejected"` |
| WARN | Signature validation failure, permission denied, unauthorized access attempt | `"HMAC signature verification failed: signature mismatch"` |
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


// Zero-Trust Security Metrics
notification_security_signature_failures_total: Counter [tenant_id, client_ip]
notification_security_permission_denied_total: Counter [tenant_id, required_permission]

## Health Endpoints
```
GET /health   → {"status": "ok"}
GET /ready    → {"status": "ready", "slack": "connected", "email": "configured", "kafka": "connected"}
GET /metrics  → Prometheus format
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| HighSignatureFailures | sum(rate(notification_security_signature_failures_total[5m])) > 5 | critical (potential spoofing attempt or key mismatch) |
| HighPermissionDenied | sum(rate(notification_security_permission_denied_total[5m])) > 10 | warning (user accessing forbidden resources) |
| DeliveryFailureHigh | sent{status=failed} > 10% in 5m | critical |
| HandoffSLABreach | sla_breached{priority=critical} > 0 | critical |
| SlackAPIDown | slack delivery errors > 5 in 2m | warning |
| EmailBounceHigh | email bounces > 5% | warning |

---

## Service Discovery Audit Logs

Khi `ServiceRegistryClient` thực hiện đăng ký hoặc hủy đăng ký trên Redis, nó phải ghi nhận log có cấu trúc JSON như sau:

### 1. Log Đăng ký Thành công (register)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "notification",
  "message": "Service node registration completed",
  "action": "register",
  "node_ip": "172.20.0.10",
  "node_port": 3004,
  "status": "success",
  "context": {
    "redis_key": "registry:service:notification"
  }
}
```

### 2. Log Hủy Đăng ký Thành công (deregister)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "notification",
  "message": "Service node deregistration completed",
  "action": "deregister",
  "node_ip": "172.20.0.10",
  "node_port": 3004,
  "status": "success",
  "context": {
    "redis_key": "registry:service:notification"
  }
}
```
