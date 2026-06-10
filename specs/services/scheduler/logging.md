# Logging & Observability — Scheduler Service

## Log Format: Structured JSON
```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "info",
  "service": "scheduler",
  "trace_id": "abc123",
  "tenant_id": "tenant-uuid",
  "message": "Post published successfully",
  "context": {
    "schedule_id": "sched-uuid",
    "post_id": "post-uuid",
    "channels": ["facebook", "zalo"],
    "scheduled_at": "2025-01-15T10:30:00Z",
    "actual_publish_at": "2025-01-15T10:30:02Z",
    "delay_ms": 2000
  }
}
```

## Log Levels
| Level | Khi nào | Ví dụ |
|-------|---------|-------|
| ERROR | Security shared secret configuration missing | `"GATEWAY_SIGNING_SECRET is not configured"` |
| ERROR | Publish failed after retries, Quartz job error | `"Publish failed: channel-connector 503, retries exhausted"` |
| WARN | Signature validation failure, permission denied, unauthorized access attempt | `"HMAC signature verification failed: signature mismatch"` |
| WARN | Retry attempt, schedule missed window, automation disabled | `"Retry 2/3 for schedule sched-uuid"` |
| INFO | Schedule created, triggered, published, automation executed | `"Schedule triggered: 3 channels"` |
| DEBUG | Quartz job details, cron expressions, automation flow steps | `"Automation flow step 2/4: generate_content"` |

## Prometheus Metrics (Spring Boot Actuator + Micrometer)

// Zero-Trust Security Metrics
scheduler_security_signature_failures_total: Counter [tenant_id, client_ip]
scheduler_security_permission_denied_total: Counter [tenant_id, required_permission]
```java
// Exposed at /actuator/prometheus
schedules_created_total: Counter [tenant_id]
schedules_triggered_total: Counter [status] // success/failed/retrying
schedules_publish_duration: Timer []
schedules_retry_total: Counter [attempt] // 1/2/3
schedules_overdue: Gauge [] // schedules past due but not published
automations_executed_total: Counter [status, trigger_type]
automations_active: Gauge [tenant_id]
quartz_jobs_running: Gauge []

// Model Context Protocol (MCP) Metrics
scheduler_mcp_connections_active: Gauge [tenant_id]
scheduler_mcp_requests_total: Counter [tool_name, status] // status: success/error
scheduler_mcp_execution_duration_seconds: Timer [tool_name]
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| HighSignatureFailures | sum(rate(scheduler_security_signature_failures_total[5m])) > 5 | critical (potential spoofing attempt or key mismatch) |
| HighPermissionDenied | sum(rate(scheduler_security_permission_denied_total[5m])) > 10 | warning (user accessing forbidden resources) |
| PublishFailures | triggered{status=failed} > 3 in 10m | warning |
| OverdueSchedules | overdue > 5 for 5m | critical |
| QuartzJobStuck | jobs_running same value for > 10m | warning |

---

## Service Discovery Audit Logs

Khi `ServiceRegistryClient` thực hiện đăng ký hoặc hủy đăng ký trên Redis, nó phải ghi nhận log có cấu trúc JSON như sau:

### 1. Log Đăng ký Thành công (register)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "scheduler",
  "message": "Service node registration completed",
  "action": "register",
  "node_ip": "172.20.0.10",
  "node_port": 8003,
  "status": "success",
  "context": {
    "redis_key": "registry:service:scheduler"
  }
}
```

### 2. Log Hủy Đăng ký Thành công (deregister)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "scheduler",
  "message": "Service node deregistration completed",
  "action": "deregister",
  "node_ip": "172.20.0.10",
  "node_port": 8003,
  "status": "success",
  "context": {
    "redis_key": "registry:service:scheduler"
  }
}
```
