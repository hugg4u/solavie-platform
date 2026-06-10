# Logging & Observability — Tenant Config Service

Tài liệu này đặc tả cấu hình logging, giám sát hiệu năng (metrics), phân vết (tracing), và các quy tắc cảnh báo (alerting) được áp dụng cho **Tenant Config Service**.

---

## 1. Cấu Hình Log (Log Configuration)

### 1.1. Định dạng JSON chuẩn (Structured JSON)
Dịch vụ Tenant Config Service sử dụng logger chuẩn của NestJS (tích hợp thư viện Pino) xuất log ở định dạng cấu trúc JSON để phục vụ lưu trữ tập trung tại Loki/ELK Stack:

```json
{
  "timestamp": "2026-06-08T11:45:00.123Z",
  "level": "info",
  "service": "tenant-config-service",
  "trace_id": "xyz789abc012",
  "span_id": "span123",
  "tenant_id": "tenant-uuid-1234",
  "message": "Config hot reload triggered successfully",
  "context": {
    "action": "config.update",
    "category": "ai_kb",
    "updated_fields": ["confidence_threshold"],
    "redis_sync": "success",
    "latency_ms": 35
  }
}
```

### 1.2. Phân Cấp Mức Log (Log Levels)
| Cấp Log | Khi Nào Sử Dụng | Ví Dụ Nghiệp Vụ |
|:---|:---|:---|
| **`error`** | Kết nối PostgreSQL/Redis bị ngắt, lỗi cú pháp SQL, hoặc lỗi khi ghi đè cache permissions. | `"Failed to publish config updates to Redis channel: Connection timed out"` |
| **`warn`** | Validation cấu hình thất bại (422), signature HMAC không khớp (403), hoặc lỗi ghi Redis cache (báo HTTP 207). | `"Config validation failed: confidence_threshold (0.55) is below minimum of 0.60"` |
| **`info`** | Lưu cấu hình thành công, hot reload thành công, tạo default config cho tenant mới, hoặc đồng bộ vai trò thành công. | `"Default config provisioned successfully for tenant: tenant-uuid-5678"` |
| **`debug`** | Chi tiết payload nhận được, tham số thô câu lệnh SQL, hoặc sự kiện gRPC request. | `"gRPC GetAllConfig called: tenant_id=tenant-uuid-1234"` |

### 1.3. Quy Tắc Che Giấu Dữ Liệu Nhạy Cảm (Sensitive Data Redaction)
*   **KHÔNG** bao giờ ghi log giá trị thô của các trường nhạy cảm: `api_key`, `secret`, `password`, `token`, `webhook_secret` (ví dụ: API Key OpenAI của tenant).
*   Mọi giá trị nhạy cảm trước khi ghi log hoặc ghi vào bảng `config_audit_logs` bắt buộc phải được che giấu bằng chuỗi định dạng `[REDACTED]`.
*   **KHÔNG** ghi log giá trị biến môi trường `GATEWAY_SIGNING_SECRET`.

---

## 2. Phân Vết Hệ Thống (OpenTelemetry Tracing)

Dịch vụ sử dụng OpenTelemetry Node SDK tự động trích xuất ngữ cảnh và liên kết phân vết (Trace Context Propagation) xuyên suốt các request từ API Gateway:

```
[HTTP Request: PATCH /api/v1/config/ai_kb] (Span gốc trích xuất từ Gateway)
├── [HmacGuard:verify_signature] — 0.4ms (So sánh timing-safe chữ ký số)
├── [PermissionsGuard:validate] — 0.2ms
└── [ConfigController:patchConfig] — 45ms
    ├── [PrismaClient:tenant_configs:update] — 12ms (Lưu database PostgreSQL)
    ├── [RedisClient:set] — 5ms (Ghi đè cấu hình vào Redis Cache)
    ├── [RedisClient:publish] — 3ms (Bắn event config.updates tới Redis Pub/Sub)
    └── [ConfigAuditLogService:log] — 8ms (Ghi nhận log kiểm toán)
```

---

## 3. Chỉ Số Giám Sát (Prometheus Metrics)

Dịch vụ phơi bày các chỉ số đo lường hiệu năng tại endpoint `/metrics` thông qua package `prom-client`:

*   **`tenant_config_http_requests_total`** (Counter): Thống kê tổng số lượng REST API requests.
    *   *Labels:* `method`, `handler`, `status_code`, `tenant_id`
*   **`tenant_config_http_request_duration_seconds`** (Histogram): Phân bố thời gian phản hồi API.
    *   *Labels:* `method`, `handler`
*   **`tenant_config_redis_operations_total`** (Counter): Đo lường hoạt động đồng bộ Cache và Pub/Sub.
    *   *Labels:* `operation` (`set`, `get`, `publish`), `status` (`success`, `error`)
*   **`tenant_config_security_signature_failures_total`** (Counter): Thống kê số lần lỗi chữ ký HMAC do Gateway gửi sang.
    *   *Labels:* `tenant_id`
*   **`tenant_config_security_permission_denied_total`** (Counter): Số lần từ chối truy cập do thiếu quyền.
    *   *Labels:* `tenant_id`, `required_permission`

---

## 4. Endpoint Kiểm Tra Sức Khỏe (Health & Ready Endpoints)

*   `GET /health` $\rightarrow$ Trả về `200 OK` nếu tiến trình Node.js đang chạy bình thường.
*   `GET /ready` $\rightarrow$ Trả về trạng thái sẵn sàng phục vụ khi và chỉ khi kết nối PostgreSQL (`config_db`) và Redis cache hoạt động thông suốt.
*   `GET /metrics` $\rightarrow$ Xuất các chỉ số Prometheus.

---

## 5. Quy Tắc Cảnh Báo (Alert Rules)

| Tên Cảnh Báo (Alert Name) | Điều Kiện Kích Hoạt | Mức Độ | Hành Động Khắc Phục |
|:---|:---|:---|:---|
| **`RedisSyncFailures`** | `sum(rate(tenant_config_redis_operations_total{status="error"}[5m])) > 3` | Critical | Kiểm tra log kết nối Redis Cluster, tài nguyên bộ nhớ Redis, và độ trễ mạng. |
| **`HighSignatureMismatch`** | `sum(rate(tenant_config_security_signature_failures_total[5m])) > 2` | Critical | Cảnh báo giả mạo request hoặc cấu hình sai lệch `GATEWAY_SIGNING_SECRET` giữa Kong Gateway và Tenant Config. |
| **`PostgreSQLConnectionDown`** | Kết nối tới database `config_db` bị gián đoạn liên tục quá 30s. | Critical | Kiểm tra log PostgreSQL, kết nối mạng trong cụm Docker/Kubernetes và connection pool. |
| **`DownstreamPermissionDenials`** | `sum(rate(tenant_config_security_permission_denied_total[5m])) > 10` | Warning | Cảnh báo người dùng thực hiện truy cập trái phép hoặc cấu hình quyền trên Keycloak/Redis bị sai lệch. |
| **`DefaultConfigProvisionFail`** | Lắng nghe event tạo tenant mới nhưng lưu default config vào DB gặp lỗi > 3 lần. | Critical | Kiểm tra tính nhất quán dữ liệu của bảng `tenant_configs` và các Kafka topics. |

---

## Service Discovery Audit Logs

Khi `ServiceRegistryClient` thực hiện đăng ký hoặc hủy đăng ký trên Redis, nó phải ghi nhận log có cấu trúc JSON như sau:

### 1. Log Đăng ký Thành công (register)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "tenant-config",
  "message": "Service node registration completed",
  "action": "register",
  "node_ip": "172.20.0.10",
  "node_port": 3006,
  "status": "success",
  "context": {
    "redis_key": "registry:service:tenant-config"
  }
}
```

### 2. Log Hủy Đăng ký Thành công (deregister)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "tenant-config",
  "message": "Service node deregistration completed",
  "action": "deregister",
  "node_ip": "172.20.0.10",
  "node_port": 3006,
  "status": "success",
  "context": {
    "redis_key": "registry:service:tenant-config"
  }
}
```
