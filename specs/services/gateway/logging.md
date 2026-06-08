# Logging & Observability — Gateway (Kong)

## Log Format
Kong logs ở format JSON (cấu hình qua file-log plugin hoặc tcp-log):

```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "service": "kong",
  "client_ip": "192.168.1.100",
  "method": "POST",
  "path": "/api/v1/conversations/uuid/messages",
  "status": 200,
  "latency_ms": 45,
  "upstream_latency_ms": 40,
  "kong_latency_ms": 5,
  "tenant_id": "tenant-uuid",
  "user_id": "user-uuid",
  "upstream_service": "messaging",
  "rate_limit_remaining": 195,
  "request_size": 256,
  "response_size": 1024
}
```

## Kong Prometheus Plugin Metrics (built-in)
```
# Auto-exposed at :8001/metrics
kong_http_requests_total: Counter [service, route, code, method]
kong_request_latency_ms: Histogram [service, route]
kong_upstream_latency_ms: Histogram [service]
kong_kong_latency_ms: Histogram [service] // Kong processing time
kong_bandwidth_bytes: Counter [service, direction] // ingress/egress
kong_connections_active: Gauge []

# Rate limiting plugin
kong_rate_limiting_total: Counter [service, status] // allowed/rejected
```

## Health Endpoints
```
GET /status          → Kong node status (admin API)
GET /health          → Custom health route (no auth)
GET :8001/metrics    → Prometheus metrics (admin API)
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| HighErrorRate | 5xx responses > 5% in 5m | critical |
| HighLatency | kong_latency p95 > 500ms (Kong overhead) | warning |
| RateLimitSpike | rate_limiting{status=rejected} > 100 in 5m | info |
| UpstreamDown | upstream 503 responses > 10 in 1m | critical |
| HighConnections | connections_active > 5000 | warning |
| HighGatewayFetchFailures | sum(rate(gateway_security_rbac_fetch_failures_total[5m])) > 5 | critical |

## Dynamic Policy Resolution Security Logs

### Permission Resolution Log Format
```json
{
  "timestamp": "2026-06-06T11:30:00.123Z",
  "level": "info",
  "message": "Dynamic policy resolution completed",
  "tenant_id": "tenant-uuid",
  "user_id": "user-uuid",
  "roles": ["admin", "user"],
  "permissions": ["analytics:metrics:read", "analytics:reports:read"],
  "cache_status": "local_worker_hit", // local_worker_hit, redis_hit, fallback_api_hit
  "signature_generated": true
}
```

### Zero-Trust Security Metrics
```
gateway_security_signature_generated_total: Counter [tenant_id, service]
gateway_security_rbac_cache_hit_total: Counter [tenant_id, cache_layer] // cache_layer: local_worker, redis, fallback
gateway_security_rbac_fetch_failures_total: Counter [tenant_id, source] // source: redis, fallback_tcs
```

