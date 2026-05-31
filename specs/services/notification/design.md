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
POST   /api/v1/notifications/send        — Send notification (internal)
GET    /api/v1/notifications              — List user notifications (in-app)
PUT    /api/v1/notifications/:id/read     — Mark as read
PUT    /api/v1/notifications/read-all     — Mark all as read
GET    /api/v1/preferences                — Get notification preferences
PUT    /api/v1/preferences                — Update preferences
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

## Kafka Events Consumed

| Topic | Action |
|-------|--------|
| `messaging.handoff.requested` | Notify assigned agent (priority: critical) |
| `crm.lead.score.changed` | Notify assigned agent (priority: high) |
| `scheduler.post.failed` | Notify post creator (priority: high) |
| `comment.escalation` | Notify assigned agent (priority: high) |

## Delivery SLA
- Critical (handoff): < 3 seconds
- High: < 30 seconds
- Normal: < 5 minutes
- Low: batched, delivered hourly


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
