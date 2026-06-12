# Design — Notification Service

## Overview

Dịch vụ thông báo đa kênh — Node.js 20, NestJS, Port 3004, PostgreSQL (notification_db). Dispatch thông báo qua Web Push (FCM), Email (Nodemailer + SendGrid/SES), SMS/Zalo khi có handoff/error. SLA: Critical (handoff) < 3s, High < 30s, Normal < 5 phút. Consume Kafka events từ messaging.handoff.requested, crm.lead.score.changed, scheduler.post.failed, comment.escalation.

## Architecture

Xem **API Design** và **Kafka Events Consumed** bên dưới.

## Components and Interfaces

Xem **API Design** và **Kafka Events Consumed** bên dưới.
| Component | Technology |
|-----------|-----------|
| Runtime | Node.js 20 |
| Framework | NestJS 10 |
| Language | TypeScript 5 |
| Database | PostgreSQL 16 |
| ORM | Prisma |
| Queue | KafkaJS (consumer) |
| Email | Nodemailer + SendGrid/SES |
| Slack | @slack/web-api |
| Push | Firebase Cloud Messaging (FCM) |
| Testing | Jest |

## API Design

```
GET    /api/v1/permissions/manifest     — Expose permissions manifest for this service
POST   /api/v1/notifications/send        — Send notification (internal)
GET    /api/v1/notifications              — List user notifications (in-app)
PUT    /api/v1/notifications/:id/read     — Mark as read
PUT    /api/v1/notifications/read-all     — Mark all as read
GET    /api/v1/preferences                — Get notification preferences
PUT    /api/v1/preferences                — Update preferences
GET    /api/v1/notification/mcp           — SSE connection endpoint for MCP Server
POST   /api/v1/notification/mcp/messages  — JSON-RPC message transport for MCP Server
```

## Data Models

```sql
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    type VARCHAR(50) NOT NULL, -- 'handoff', 'lead_score', 'publish_failed', 'escalation'
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    priority VARCHAR(20) DEFAULT 'normal',
    channels_attempted TEXT[] DEFAULT '{}',
    delivery_status VARCHAR(20) DEFAULT 'pending',
    read_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE notification_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL UNIQUE,
    channels JSONB DEFAULT '{"email": true, "slack": true, "push": true}',
    quiet_hours JSONB DEFAULT '{"start": "22:00", "end": "08:00", "timezone": "Asia/Ho_Chi_Minh"}',
    priority_filter VARCHAR(20) DEFAULT 'normal', -- minimum priority to receive
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_notif_user ON notifications(user_id, read_at NULLS FIRST, created_at DESC);
CREATE INDEX idx_notif_tenant ON notifications(tenant_id, created_at DESC);
```

## Kafka Events Consumed (Luồng 5 - MỚI)
 
 | Topic | Action |
 |-------|--------|
 | `messaging.handoff.requested` | Notify assigned agent (priority: critical) |
 | `crm.lead.score.changed` | Notify assigned agent (priority: high) |
 | `scheduler.post.failed` | Notify post creator (priority: high) |
 | `comment.escalation` | Notify assigned agent (priority: high) |
 | `notification.send` | Gửi thông báo bất đồng bộ qua Email/SMS/Push cho người dùng |
 
 ### Payload của `notification.send` (Luồng 5):
 ```json
 {
   "event_id": "uuid-v4",
   "tenant_id": "uuid-v4",
   "user_id": "uuid-v4",
   "type": "EMAIL", // EMAIL | SMS | PUSH
   "template": "post_publish_failed",
   "parameters": {
     "schedule_id": "uuid-v4",
     "post_id": "uuid-v4",
     "error": "Reason details"
   },
   "timestamp": "ISO-8601 timestamp"
 }
 ```

## Delivery SLA
- Critical (handoff): < 3 seconds
- High: < 30 seconds
- Normal: < 5 minutes
- Low: batched, delivered hourly


## Model Context Protocol (MCP) Tools

Dịch vụ Notification Service đóng vai trò là một MCP SSE Server đăng ký các công cụ sau:

### 1. Tool: `send_notification`
* **Mô tả:** Gửi thông báo đến người nhận chỉ định qua in-app, Slack hoặc Email.
* **Tham số đầu vào (Schema):**
  * `user_id` (string, UUID, required): ID của người dùng hệ thống nhận thông báo.
  * `title` (string, required): Tiêu đề thông báo.
  * `message` (string, required): Nội dung thông báo.
  * `channel` (string, optional, enum: `['in-app', 'slack', 'email']`): Kênh gửi ưu tiên.
  * `priority` (string, optional, enum: `['critical', 'high', 'normal', 'low']`): Độ ưu tiên.
* **Bảo mật:** Tham số `tenant_id` sẽ được tự động tiêm từ header `X-Tenant-ID` vào tham số thực thi hàm nghiệp vụ nhằm đảm bảo an toàn truy vấn và ghi nhận vào cơ sở dữ liệu Prisma của tenant, tránh rò rỉ dữ liệu chéo.

## Correctness Properties

### Property 1: Tenant Isolation
**Validates: Requirements 4.1**
Moi query va operation phai filter theo tenant_id tu JWT claims. Khong co cross-tenant data leakage o bat ky tang nao (DB, Kafka, Redis, Qdrant, MinIO).

### Property 2: Idempotency
**Validates: Requirements 3.1**
Moi write operation phai co idempotency key de tranh duplicate processing khi retry. Kafka consumer phai idempotent.

### Property 3: At-least-once Delivery
**Validates: Requirements 3.1**
Kafka events phai duoc xu ly it nhat mot lan. Sau 3 retries voi exponential backoff (1s, 2s, 4s), event chuyen vao dead-letter queue.

### Property 4: Circuit Breaker Correctness
**Validates: Requirements 5.1**
Sync calls toi external services phai qua circuit breaker. Open sau 5 failures trong 30s, Half-Open probe sau 60s.

### Property 5: Data Consistency
**Validates: Requirements 3.1**
Distributed transactions dung Saga pattern voi compensating actions khi rollback. Moi destructive action ghi audit.events Kafka topic.
## Error Handling

| Scenario | Strategy |
|----------|----------|
| External API timeout | Retry t?i da 3 l?n v?i exponential backoff (1s, 2s, 4s); sau d� tr? v? l?i c� c?u tr�c |
| Database connection error | Circuit breaker + fallback response; alert qua Alertmanager |
| Kafka publish failure | Retry 3 l?n; n?u v?n th?t b?i ghi v�o dead-letter queue |
| Invalid tenant_id | Reject ngay v?i HTTP 403 + ghi security warning v�o audit log |
| Validation error | Tr? v? HTTP 422 v?i danh s�ch field errors chi ti?t |
| Unhandled exception | Log structured JSON v?i trace_id; tr? v? HTTP 500 v?i error_id d? debug |

## Testing Strategy

| Layer | Tool | Coverage Target |
|-------|------|----------------|
| Unit Tests | Jest (Node.js) / pytest (Python) / JUnit 5 (Java) | > 80% business logic |
| Integration Tests | Testcontainers (PostgreSQL, Redis, Kafka) | Happy path + error paths |
| Contract Tests | Pact (consumer-driven) cho gRPC interfaces | Chatbot?AI Core, Messaging?Chatbot |
| Property-Based Tests | fast-check (JS) / Hypothesis (Python) | Tenant isolation, idempotency |
| Load Tests | k6 | Chatbot E2E < 2s t?i 100 concurrent users |


## Zero-Trust HMAC Guard & Permission Manifest

### 1. Permission Manifest API
`GET /api/v1/permissions/manifest`
Trả về JSON chứa danh sách các tài nguyên và hành động được định nghĩa cho service này:
```json
{
    "service": "notification",
    "resources": [
        {
            "name": "notifications",
            "description": "Alerts and push notifications",
            "actions": [
                "send"
            ]
        },
        {
            "name": "preferences",
            "description": "Notification preferences",
            "actions": [
                "write"
            ]
        }
    ]
}
```

### 2. Zero-Trust HMAC Signature Verification
Dịch vụ kiểm tra và xác thực chữ ký signature trên mỗi request tại lớp Guard/Interceptor của Node.js / NestJS:
1. Trích xuất `X-Tenant-ID`, `X-User-ID`, `X-User-Permissions` và `X-Permissions-Signature` từ headers.
2. Tính toán signature mong đợi:
   `expected_sig = HMAC_SHA256(GATEWAY_SIGNING_SECRET, X-Tenant-ID + ":" + X-User-ID + ":" + X-User-Permissions)`
3. So sánh `X-Permissions-Signature` với `expected_sig`. Nếu không khớp, trả về ngay lập tức mã lỗi `403 Forbidden` (Signature Mismatch).
4. So khớp in-memory O(1): parse `X-User-Permissions` thành một Set và đối chiếu với quyền yêu cầu của endpoint (ví dụ: `notification:notifications:send`).
   - Hỗ trợ wildcard: `*` (Super Admin bypass), `notification:*` (Service bypass), và `notification:notifications:*` (Resource bypass).

## Security & Gateway Integration
- Dịch vụ được triển khai stateless phía sau Kong API Gateway.
- Gateway chịu trách nhiệm validate JWT token từ Keycloak, xác thực client scope `notification`, và inject header `X-Tenant-ID` vào request.
- Dịch vụ tin tưởng hoàn toàn vào các header được Gateway inject để thực hiện logic nghiệp vụ và cô lập dữ liệu.

---

## Service Discovery Integration Design

Dịch vụ Notification tích hợp lớp `ServiceRegistryClient` chạy song song với ứng dụng chính để hỗ trợ phát hiện dịch vụ động:

### 1. Kiến trúc Client
* **Cơ chế:**
  * **Startup Event:** Khi tiến trình của dịch vụ khởi động, client thực thi lệnh `SADD` để thêm IP:Port của node hiện tại vào Redis Set: `registry:service:notification`.
  * **Heartbeat Thread/Task:** Chạy định kỳ mỗi 5 giây để thực hiện:
    * Ghi đè khóa sự sống: `SETEX registry:service:notification:node:{ip}:{port} 15 "alive"`.
    * Đảm bảo IP vẫn tồn tại trong Set: `SADD registry:service:notification {ip}:{port}`.
  * **Shutdown Event:** Khi nhận tín hiệu tắt tiến trình (`SIGTERM`/`SIGINT`), client thực hiện dọn dẹp:
    * Xóa IP khỏi Set: `SREM registry:service:notification {ip}:{port}`.
    * Xóa khóa sống: `DEL registry:service:notification:node:{ip}:{port}`.

### 2. Tích hợp theo Tech Stack
* **NestJS (Node.js):** Sử dụng các lifecycle hooks `OnModuleInit` và `OnApplicationShutdown` kết hợp thư viện `ioredis` và `setInterval` cho heartbeat.
* **FastAPI (Python):** Sử dụng lifespan event handlers của FastAPI kết hợp `asyncio.create_task` và `redis-py`.
* **Spring Boot (Java):** Sử dụng annotation `@PostConstruct` và `@PreDestroy` kết hợp `ScheduledExecutorService` và `Jedis`/`Lettuce`.


---

## Registry Client & Health Endpoint Design (Tối ưu hóa)
*   **Giải thuật phát hiện IP:**
    1. Lấy biến môi trường `CONTAINER_IP`.
    2. Nếu trống, quét các interface card mạng vật lý của OS để tìm IP IPv4 hợp lệ.
    3. Fallback: Tạo kết nối UDP fake đến `8.8.8.8:53`.
*   **Health Check Endpoint:**
    *   Endpoint: `/health`
    *   Response: `{"status": "UP", "timestamp": "ISO-8601", "details": {"database": "UP", "redis": "UP"}}`
    *   Kiểm tra kết nối Database và Redis. Trả về HTTP 200 nếu khỏe mạnh, HTTP 503 nếu lỗi kết nối cốt lõi.
