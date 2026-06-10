# Logging & Observability — User Service

## Log Configuration

### Format: Structured JSON
Dịch vụ User Service sử dụng thư viện logging trong NestJS (Pino hoặc Winston) cấu hình xuất định dạng log JSON chuẩn để dễ dàng thu thập và phân tích qua Loki/ELK Stack:

```json
{
  "timestamp": "2026-06-08T10:30:00.123Z",
  "level": "info",
  "service": "user-service",
  "trace_id": "abc123def456",
  "span_id": "span789",
  "tenant_id": "tenant-uuid-1234",
  "message": "User invitation processed successfully",
  "context": {
    "action": "user.invite",
    "invited_email": "employee@tenant.com",
    "role": "agent",
    "keycloak_sync_status": "success",
    "latency_ms": 120
  }
}
```

### Log Levels
| Level | Khi nào dùng | Ví dụ |
|-------|-------------|-------|
| ERROR | Kết nối DB sập, Keycloak Admin API trả về 5xx, lỗi RLS Context | `"Failed to set PostgreSQL tenant RLS context: Connection timeout"` |
| WARN | Webhook signature mismatch, Keycloak sync conflict (409), invalid credentials | `"Keycloak user creation conflict: email already exists on IDP"` |
| INFO | Mời user thành công, nhận webhook verify email, update profile, sync user | `"User updated profile: user_id=uuid, fields=[avatar_url]"` |
| DEBUG | Payload thô nhận từ webhook, tham số câu lệnh SQL thô | `"Database query executed: SELECT * FROM users WHERE tenant_id = ..."` |

### Sensitive Data Rules (Bảo mật PII)
- **KHÔNG** ghi log thô các trường thông tin nhạy cảm: Số điện thoại đầy đủ, mật khẩu tạm thời, token kích hoạt.
- Số điện thoại ghi log dưới dạng masked (ví dụ: `098****123`).
- **KHÔNG** bao giờ ghi log giá trị `GATEWAY_SIGNING_SECRET` hoặc Client Secret của Keycloak.

---

## OpenTelemetry SDK Config trong NestJS (Node.js)

Dịch vụ sử dụng `@opentelemetry/sdk-node` và `@opentelemetry/auto-instrumentations-node` để tự động thu thập trace spans từ HTTP request, Prisma/TypeORM, và gRPC server:

```typescript
// tracing.ts
import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-grpc';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-grpc';
import { PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';

const sdk = new NodeSDK({
  traceExporter: new OTLPTraceExporter({
    url: 'http://otel-collector:4317',
  }),
  metricReader: new PeriodicExportingMetricReader({
    exporter: new OTLPMetricExporter({
      url: 'http://otel-collector:4317',
    }),
    exportIntervalMillis: 15000,
  }),
  instrumentations: [getNodeAutoInstrumentations()],
});

sdk.start();

process.on('SIGTERM', () => {
  sdk.shutdown()
    .then(() => console.log('Tracing terminated'))
    .catch((error) => console.log('Error terminating tracing', error))
    .finally(() => process.exit(0));
});
```

---

## Trace Spans

```
[HTTP/gRPC Request] (root span from API Gateway)
├── [HmacGuard:verify_signature] — 0.5ms (So sánh timing-safe chữ ký số)
├── [AsyncLocalStorage:set_tenant_context] — 0.1ms
├── [PermissionsGuard:validate] — 0.2ms
└── [UserController:inviteUser] — 120ms
    ├── [PrismaClient:users:create] — 15ms (Lưu user shadow với status='PENDING')
    ├── [KeycloakAdminClient:createUser] — 85ms (Gọi HTTP API tạo user trên IDP)
    └── [NotificationClient:sendInviteEmail] — 12ms (Publish event user.invited lên Redis/Kafka)
```

---

## Prometheus Metrics

Các metrics tùy chỉnh được phơi bày tại endpoint `/metrics` thông qua package `prom-client`:

```typescript
import { Counter, Histogram } from 'prom-client';

// Thống kê HTTP request
export const httpRequestsTotal = new Counter({
  name: 'user_service_http_requests_total',
  help: 'Total HTTP requests in User Service',
  labelNames: ['method', 'handler', 'status_code', 'tenant_id'],
});

export const httpRequestDuration = new Histogram({
  name: 'user_service_http_request_duration_seconds',
  help: 'HTTP request latency distribution',
  labelNames: ['method', 'handler'],
  buckets: [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
});

// Thống kê đồng bộ Keycloak
export const keycloakSyncOperations = new Counter({
  name: 'user_service_keycloak_sync_total',
  help: 'Total sync operations with Keycloak',
  labelNames: ['direction', 'operation', 'status'], // direction: IN (KC->US), OUT (US->KC); status: success, error
});

// Thống kê Bảo mật & Zero-Trust
export const securitySignatureFailures = new Counter({
  name: 'user_service_security_signature_failures_total',
  help: 'Total HMAC signature validation failures on X-Permissions-Signature',
  labelNames: ['tenant_id'],
});

export const securityPermissionDenied = new Counter({
  name: 'user_service_security_permission_denied_total',
  help: 'Total permission denied decisions at downstream guard',
  labelNames: ['tenant_id', 'required_permission'],
});
```

---

## Health & Ready Endpoints

Dịch vụ sử dụng module `@nestjs/terminus` để cung cấp các API giám sát trạng thái:
* `GET /health` -> Trả về `200 OK` nếu ứng dụng hoạt động bình thường.
* `GET /ready` -> Trả về trạng thái sẵn sàng sau khi kiểm tra kết nối PostgreSQL và Keycloak Admin API.
* `GET /metrics` -> Xuất các chỉ số Prometheus.

---

## Alert Rules (Prometheus Alertmanager)

| Tên Alert | Điều kiện | Mức độ | Hành động khắc phục |
|-----------|-----------|--------|---------------------|
| KeycloakSyncFailures | `sum(rate(user_service_keycloak_sync_total{status="error"}[5m])) > 5` | Critical | Kiểm tra log kết nối API Keycloak Admin Client, kiểm tra credentials client |
| HighSignatureMismatch | `sum(rate(user_service_security_signature_failures_total[5m])) > 2` | Critical | Cảnh báo tấn công Header Spoofing hoặc sai cấu hình `GATEWAY_SIGNING_SECRET` giữa Gateway và User Service |
| DownstreamPermissionDenials | `sum(rate(user_service_security_permission_denied_total[5m])) > 10` | Warning | Kiểm tra phân quyền trên Keycloak/Redis của Tenant hoặc cảnh báo hành vi truy cập trái phép |
| PostgreSQLConnectionDown | Kết nối tới database `solavie_user_db` bị ngắt quãng > 30s | Critical | Kiểm tra tài nguyên DB, RLS policies, và connection pool |

---

## Service Discovery Audit Logs

Khi `ServiceRegistryClient` thực hiện đăng ký hoặc hủy đăng ký trên Redis, nó phải ghi nhận log có cấu trúc JSON như sau:

### 1. Log Đăng ký Thành công (register)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "user",
  "message": "Service node registration completed",
  "action": "register",
  "node_ip": "172.20.0.10",
  "node_port": 3008,
  "status": "success",
  "context": {
    "redis_key": "registry:service:user"
  }
}
```

### 2. Log Hủy Đăng ký Thành công (deregister)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "user",
  "message": "Service node deregistration completed",
  "action": "deregister",
  "node_ip": "172.20.0.10",
  "node_port": 3008,
  "status": "success",
  "context": {
    "redis_key": "registry:service:user"
  }
}
```
