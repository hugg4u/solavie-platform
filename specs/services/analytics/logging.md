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

## Log Levels
| Level | Khi nào | Ví dụ |
|-------|---------|-------|
| ERROR | TimescaleDB write fail, Kafka consume error, report generation fail | `"TimescaleDB connection pool exhausted"` |
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
```

## Health Endpoints
```
GET /health   → {"status": "ok"}
GET /ready    → {"status": "ready", "timescaledb": "connected", "kafka": "connected"}
GET /actuator/prometheus → Prometheus metrics
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| KafkaLagHigh | consumer_lag > 5000 for 5m | warning |
| AggregationSlow | aggregation_duration p95 > 30s | warning |
| ReportGenerationFail | reports{status=failed} > 2 in 1h | warning |
| TimescaleDBDiskFull | disk usage > 80% | critical |
