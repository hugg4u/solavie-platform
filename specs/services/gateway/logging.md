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


## Giai đoạn 4 — Logging & Metrics cho Cache & Circuit Breaker (MỚI)

### 1. Log sự kiện thay đổi trạng thái Circuit Breaker
Khi Circuit Breaker chuyển đổi trạng thái (CLOSED -> OPEN -> HALF-OPEN -> CLOSED), Gateway sẽ ghi nhận log có cấu trúc để hệ thống giám sát (Elasticsearch/Fluentd) có thể bắt được sự kiện và gửi cảnh báo:

```json
{
  "timestamp": "2026-06-08T15:30:00.123Z",
  "level": "warn",
  "category": "gateway.circuit_breaker",
  "message": "Circuit Breaker state changed",
  "service": "tenant-config",
  "previous_state": "CLOSED",
  "new_state": "OPEN",
  "failure_count": 5,
  "reason": "Consecutive timeouts/errors calling Tenant Config Service"
}
```

### 2. Các chỉ số đo lường hiệu năng mới (Prometheus Metrics)
```
# Theo dõi tỉ lệ Hit/Miss của L1 Cache (ngx.shared.DICT) và L2 Cache (Redis)
gateway_cache_requests_total: Counter [cache_layer, status] // cache_layer: l1_dict, l2_redis; status: hit, miss

# Theo dõi trạng thái hiện tại của Circuit Breaker
gateway_circuit_breaker_state: Gauge [service] // value: 0 (CLOSED), 1 (OPEN), 2 (HALF-OPEN)

# Theo dõi số lần kích hoạt ngắt mạch
gateway_circuit_breaker_trips_total: Counter [service]
```

### 3. Log sự kiện cập nhật Upstream Targets (Sync Daemon)
Khi Registry Sync Daemon thực hiện thêm hoặc bớt các Target IP của Upstream trên Kong, nó phải ghi nhận log có cấu trúc để phục vụ giám sát:

```json
{
  "timestamp": "2026-06-09T17:45:00.123Z",
  "level": "info",
  "service": "kong-registry-sync",
  "message": "Upstream target updated",
  "upstream": "ai-core-upstream",
  "action": "add_target", // add_target, remove_target, sync_complete
  "target": "172.20.0.10:8000",
  "status": "success",
  "context": {
    "redis_nodes_count": 2,
    "kong_targets_count": 2
  }
}
```

```

