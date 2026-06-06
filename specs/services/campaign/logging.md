# Logging & Observability — Campaign Service

## Log Format: Structured JSON
```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "info",
  "service": "campaign",
  "trace_id": "abc123",
  "tenant_id": "tenant-uuid",
  "message": "A/B test concluded",
  "context": {
    "campaign_id": "camp-uuid",
    "test_id": "test-uuid",
    "winner": "variant_A",
    "confidence_level": 0.96,
    "sample_size": 1500
  }
}
```

## Log Levels
| Level | Khi nào | Ví dụ |
|-------|---------|-------|
| ERROR | Security shared secret configuration missing | `"GATEWAY_SIGNING_SECRET is not configured"` |
| ERROR | Campaign activation fail, metrics collection error | `"Campaign start failed: no posts linked"` |
| WARN | Signature validation failure, permission denied, unauthorized access attempt | `"HMAC signature verification failed: signature mismatch"` |
| WARN | A/B test inconclusive, low sample size | `"A/B test: insufficient data after 7 days"` |
| INFO | Campaign created/started/paused/completed, A/B test concluded | `"Campaign 'Summer Sale' completed"` |
| DEBUG | Statistical calculations, variant distribution, metric aggregation | `"Chi-square p-value: 0.032"` |

## Prometheus Metrics (Spring Boot Actuator)
```java
campaigns_active: Gauge [tenant_id]
campaigns_created_total: Counter [tenant_id]
campaigns_status_changes_total: Counter [from_status, to_status]
ab_tests_running: Gauge []
ab_tests_concluded_total: Counter [result] // winner_found/inconclusive
campaign_metrics_collected_total: Counter [metric_type]
```


// Zero-Trust Security Metrics
campaign_security_signature_failures_total: Counter [tenant_id, client_ip]
campaign_security_permission_denied_total: Counter [tenant_id, required_permission]

## Health Endpoints
```
GET /health   → {"status": "ok"}
GET /ready    → {"status": "ready", "postgres": "connected", "kafka": "connected"}
GET /actuator/prometheus → Prometheus metrics
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| HighSignatureFailures | sum(rate(campaign_security_signature_failures_total[5m])) > 5 | critical (potential spoofing attempt or key mismatch) |
| HighPermissionDenied | sum(rate(campaign_security_permission_denied_total[5m])) > 10 | warning (user accessing forbidden resources) |
| CampaignStuck | active campaign no metrics for > 24h | warning |
| ABTestTooLong | ab_test running > 14 days | info |
