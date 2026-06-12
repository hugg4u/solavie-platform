# Design — Analytics Service

## Overview

Dịch vụ phân tích và reporting — Java 21, Spring Boot 3.2, Port 8006, PostgreSQL + TimescaleDB (analytics_db). Thu thập metrics từ tất cả Kafka events, lưu trữ time-series data (hypertable), continuous aggregates (daily_metrics), tạo báo cáo hiệu suất Agent, ROI chiến dịch, và AI performance metrics.

## Architecture

Xem **API Design** và **Kafka Events Consumed** bên dưới.

## Components and Interfaces

Xem **API Design** và **Kafka Events Consumed** bên dưới.
| Component | Technology |
|-----------|-----------|
| Runtime | Java 21 |
| Framework | Spring Boot 3.2 |
| Database | PostgreSQL 16 + TimescaleDB |
| ORM | Spring Data JPA |
| Queue | Spring Kafka (consumer) |
| Report | Apache POI (Excel), iText (PDF) |
| Build | Gradle |
| Testing | JUnit 5 + Testcontainers |

## API Design

```
GET    /api/v1/permissions/manifest     — Expose permissions manifest for this service
GET    /api/v1/metrics                  — Get metrics (filters: channel, date_range, granularity)
GET    /api/v1/metrics/realtime         — Realtime metrics (last 1h)
GET    /api/v1/metrics/compare          — Period comparison
GET    /api/v1/metrics/channels/:id     — Per-channel metrics
GET    /api/v1/insights                 — AI-generated insights
GET    /api/v1/reports                  — List generated reports
POST   /api/v1/reports/generate         — Generate report (async)
GET    /api/v1/reports/:id/download     — Download report file
GET    /api/v1/analytics/mcp            — SSE connection endpoint for MCP Server
POST   /api/v1/analytics/mcp/messages   — JSON-RPC message transport for MCP Server
```

## Data Models

```sql
-- Hypertable for time-series metrics
CREATE TABLE metrics (
    time TIMESTAMPTZ NOT NULL,
    tenant_id UUID NOT NULL,
    channel VARCHAR(20) NOT NULL,
    post_id UUID,
    metric_type VARCHAR(50) NOT NULL, -- 'likes', 'comments', 'shares', 'reach', 'clicks', 'messages'
    value BIGINT NOT NULL DEFAULT 0,
    metadata JSONB DEFAULT '{}'
);

SELECT create_hypertable('metrics', 'time');
CREATE INDEX idx_metrics_tenant ON metrics(tenant_id, time DESC);
CREATE INDEX idx_metrics_post ON metrics(post_id, time DESC) WHERE post_id IS NOT NULL;

-- Aggregated daily metrics (continuous aggregate)
CREATE MATERIALIZED VIEW daily_metrics
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS day,
    tenant_id,
    channel,
    metric_type,
    SUM(value) AS total_value,
    COUNT(*) AS event_count
FROM metrics
GROUP BY day, tenant_id, channel, metric_type;

-- Reports
CREATE TABLE reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    report_type VARCHAR(50) NOT NULL,
    date_range_start TIMESTAMPTZ NOT NULL,
    date_range_end TIMESTAMPTZ NOT NULL,
    file_path TEXT,
    status VARCHAR(20) DEFAULT 'generating',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Kafka Events Consumed

| Topic | Metric Extracted |
|-------|-----------------|
| `channel.message.received` | message_count, response_time |
| `channel.message.sent` | outbound_count |
| `content.published` | post_count per channel |
| `campaign.event.*` | campaign metrics |
| `messaging.handoff.requested` | handoff_rate |
| `crm.lead.score.changed` | lead_conversion |


## Model Context Protocol (MCP) Tools

Dịch vụ Analytics Service đóng vai trò là một MCP SSE Server (sử dụng thư viện tương thích Java/Spring Boot) đăng ký các công cụ sau:

### 1. Tool: `analytics_query`
* **Mô tả:** Truy vấn dữ liệu phân tích chi tiết của tenant về engagement, reach, hiệu suất chiến dịch hoặc phát hiện bất thường.
* **Tham số đầu vào (Schema):**
  * `query_type` (string, required, enum: `['engagement', 'reach', 'campaign_performance', 'anomaly_detection']`): Loại báo cáo cần truy vấn.
  * `start_date` (string, ISO-8601 offset date-time format, optional): Ngày bắt đầu.
  * `end_date` (string, ISO-8601 offset date-time format, optional): Ngày kết thúc.
  * `campaign_id` (string, UUID, optional): ID chiến dịch nếu muốn lọc theo chiến dịch cụ thể.
* **Bảo mật:** Tham số `tenant_id` sẽ được trích xuất từ header `X-Tenant-ID` và tự động tiêm vào câu lệnh truy vấn TimescaleDB, cấm hoàn toàn LLM sửa đổi.

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
    "service": "analytics",
    "resources": [
        {
            "name": "metrics",
            "description": "Realtime and historical metrics data",
            "actions": [
                "read"
            ]
        },
        {
            "name": "reports",
            "description": "Report generation and exports",
            "actions": [
                "read",
                "write"
            ]
        }
    ]
}
```

### 2. Zero-Trust HMAC Signature Verification
Dịch vụ kiểm tra và xác thực chữ ký signature trên mỗi request tại lớp Guard/Interceptor của Spring Boot (Java):
1. Trích xuất `X-Tenant-ID`, `X-User-ID`, `X-User-Permissions` và `X-Permissions-Signature` từ headers.
2. Tính toán signature mong đợi:
   `expected_sig = HMAC_SHA256(GATEWAY_SIGNING_SECRET, X-Tenant-ID + ":" + X-User-ID + ":" + X-User-Permissions)`
3. So sánh `X-Permissions-Signature` với `expected_sig`. Nếu không khớp, trả về ngay lập tức mã lỗi `403 Forbidden` (Signature Mismatch).
4. So khớp in-memory O(1): parse `X-User-Permissions` thành một Set và đối chiếu với quyền yêu cầu của endpoint (ví dụ: `analytics:metrics:read`).
   - Hỗ trợ wildcard: `*` (Super Admin bypass), `analytics:*` (Service bypass), và `analytics:metrics:*` (Resource bypass).

## Security & Gateway Integration
- Dịch vụ được triển khai stateless phía sau Kong API Gateway.
- Gateway chịu trách nhiệm validate JWT token từ Keycloak, xác thực client scope `analytics`, và inject header `X-Tenant-ID` vào request.
- Dịch vụ tin tưởng hoàn toàn vào các header được Gateway inject để thực hiện logic nghiệp vụ và cô lập dữ liệu.

---

## Service Discovery Integration Design

Dịch vụ Analytics tích hợp lớp `ServiceRegistryClient` chạy song song với ứng dụng chính để hỗ trợ phát hiện dịch vụ động:

### 1. Kiến trúc Client
* **Cơ chế:**
  * **Startup Event:** Khi tiến trình của dịch vụ khởi động, client thực thi lệnh `SADD` để thêm IP:Port của node hiện tại vào Redis Set: `registry:service:analytics`.
  * **Heartbeat Thread/Task:** Chạy định kỳ mỗi 5 giây để thực hiện:
    * Ghi đè khóa sự sống: `SETEX registry:service:analytics:node:{ip}:{port} 15 "alive"`.
    * Đảm bảo IP vẫn tồn tại trong Set: `SADD registry:service:analytics {ip}:{port}`.
  * **Shutdown Event:** Khi nhận tín hiệu tắt tiến trình (`SIGTERM`/`SIGINT`), client thực hiện dọn dẹp:
    * Xóa IP khỏi Set: `SREM registry:service:analytics {ip}:{port}`.
    * Xóa khóa sống: `DEL registry:service:analytics:node:{ip}:{port}`.

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
