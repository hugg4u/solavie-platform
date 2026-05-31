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
GET    /api/v1/metrics                  — Get metrics (filters: channel, date_range, granularity)
GET    /api/v1/metrics/realtime         — Realtime metrics (last 1h)
GET    /api/v1/metrics/compare          — Period comparison
GET    /api/v1/metrics/channels/:id     — Per-channel metrics
GET    /api/v1/insights                 — AI-generated insights
GET    /api/v1/reports                  — List generated reports
POST   /api/v1/reports/generate         — Generate report (async)
GET    /api/v1/reports/:id/download     — Download report file
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
