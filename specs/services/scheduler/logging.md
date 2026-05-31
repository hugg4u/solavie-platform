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
| ERROR | Publish failed after retries, Quartz job error | `"Publish failed: channel-connector 503, retries exhausted"` |
| WARN | Retry attempt, schedule missed window, automation disabled | `"Retry 2/3 for schedule sched-uuid"` |
| INFO | Schedule created, triggered, published, automation executed | `"Schedule triggered: 3 channels"` |
| DEBUG | Quartz job details, cron expressions, automation flow steps | `"Automation flow step 2/4: generate_content"` |

## Prometheus Metrics (Spring Boot Actuator + Micrometer)
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
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| PublishFailures | triggered{status=failed} > 3 in 10m | warning |
| OverdueSchedules | overdue > 5 for 5m | critical |
| QuartzJobStuck | jobs_running same value for > 10m | warning |
