# Logging & Observability — Analytics Service

## Log Format: Structured JSON
```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "info",
  "service": "analytics",
  "trace_id": "abc123",
  "tenant_id": "tenant-uuid",
  "message": "Metrics aggregated",
  "context": {
    "metric_type": "engagement",
    "channel": "facebook",
    "records_processed": 150,
    "aggregation_time_ms": 45
  }
}
```


### RAG Event Ingestion Log Format (MỚI)
```json
{
  "timestamp": "2026-06-12T14:10:00.123Z",
  "level": "info",
  "service": "analytics",
  "trace_id": "abc123def456",
  "tenant_id": "tenant-uuid",
  "message": "Successfully consumed and stored RAG metric event",
  "action": "rag_event_ingestion_success",
  "context": {
    "event_id": "event-uuid",
    "conversation_id": "conversation-uuid",
    "rag_similarity": 0.87,
    "chatbot_action": "reply"
  }
}
```

```json
{
  "timestamp": "2026-06-12T14:10:05.123Z",
  "level": "error",
  "service": "analytics",
  "trace_id": "abc123def456",
  "tenant_id": "tenant-uuid",
  "message": "Failed to consume RAG metric event from Kafka",
  "action": "rag_event_ingestion_failure",
  "context": {
    "error_message": "Invalid JSON format: missing tenant_id",
    "raw_payload": "{\"event_id\":\"...\"}"
  }
}
```

## Log Levels
| Level | Khi nào | Ví dụ |
|-------|---------|-------|
| ERROR | Security shared secret configuration missing | `"GATEWAY_SIGNING_SECRET is not configured"` |
| ERROR | TimescaleDB write fail, Kafka consume error, report generation fail | `"TimescaleDB connection pool exhausted"` |
| WARN | Signature validation failure, permission denied, unauthorized access attempt | `"HMAC signature verification failed: signature mismatch"` |
| WARN | Slow aggregation, missing data gaps, report timeout | `"Aggregation took 30s (threshold: 10s)"` |
| INFO | Metrics ingested, report generated, insights created | `"Weekly report generated for tenant-abc"` |
| DEBUG | Raw Kafka events, SQL queries, AI insight prompts | `"Continuous aggregate refreshed: daily_metrics"` |

## Prometheus Metrics (Spring Boot Actuator)
```java
// /actuator/prometheus
analytics_events_consumed_total: Counter [topic, tenant_id]
analytics_aggregation_duration: Timer [metric_type]
analytics_reports_generated_total: Counter [report_type, status]
analytics_insights_generated_total: Counter [tenant_id]
analytics_timescaledb_write_duration: Timer []
analytics_kafka_consumer_lag: Gauge [topic, partition]
analytics_data_points_stored: Gauge [tenant_id] // total data points

// Model Context Protocol (MCP) Metrics
analytics_mcp_connections_active: Gauge [tenant_id]
analytics_mcp_requests_total: Counter [tool_name, status] // status: success/error
analytics_mcp_execution_duration_seconds: Timer [tool_name]
```


// Zero-Trust Security Metrics
analytics_security_signature_failures_total: Counter [tenant_id, client_ip]
analytics_security_permission_denied_total: Counter [tenant_id, required_permission]

## Health Endpoints
```
GET /health   → {"status": "ok"}
GET /ready    → {"status": "ready", "timescaledb": "connected", "kafka": "connected"}
GET /actuator/prometheus → Prometheus metrics
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| HighSignatureFailures | sum(rate(analytics_security_signature_failures_total[5m])) > 5 | critical (potential spoofing attempt or key mismatch) |
| HighPermissionDenied | sum(rate(analytics_security_permission_denied_total[5m])) > 10 | warning (user accessing forbidden resources) |
| KafkaLagHigh | consumer_lag > 5000 for 5m | warning |
| AggregationSlow | aggregation_duration p95 > 30s | warning |
| ReportGenerationFail | reports{status=failed} > 2 in 1h | warning |
| TimescaleDBDiskFull | disk usage > 80% | critical |

---

## Service Discovery Audit Logs

Khi `ServiceRegistryClient` thực hiện đăng ký hoặc hủy đăng ký trên Redis, nó phải ghi nhận log có cấu trúc JSON như sau:

### 1. Log Đăng ký Thành công (register)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "analytics",
  "message": "Service node registration completed",
  "action": "register",
  "node_ip": "172.20.0.10",
  "node_port": 8006,
  "status": "success",
  "context": {
    "redis_key": "registry:service:analytics"
  }
}
```

### 2. Log Hủy Đăng ký Thành công (deregister)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "analytics",
  "message": "Service node deregistration completed",
  "action": "deregister",
  "node_ip": "172.20.0.10",
  "node_port": 8006,
  "status": "success",
  "context": {
    "redis_key": "registry:service:analytics"
  }
}
```
