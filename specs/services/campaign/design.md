# Design — Campaign Service

## Overview

Dịch vụ quản lý chiến dịch marketing — Java 21, Spring Boot 3.2, Port 8007, PostgreSQL (campaign_db). Hỗ trợ Broadcasting (gửi tin hàng loạt đến Segment), A/B Testing (2 phiên bản content với statistical significance), và phân tích hiệu quả chiến dịch.

## Architecture

Xem **API Design** và **Kafka Events** bên dưới.

## Components and Interfaces

Xem **API Design** và **Kafka Events** bên dưới.
| Component | Technology |
|-----------|-----------|
| Runtime | Java 21 |
| Framework | Spring Boot 3.2 |
| Database | PostgreSQL 16 |
| ORM | Spring Data JPA |
| Queue | Spring Kafka |
| Statistics | Apache Commons Math (for A/B testing significance) |
| Build | Gradle |
| Testing | JUnit 5 + Testcontainers |

## API Design

```
GET    /api/v1/permissions/manifest     — Expose permissions manifest for this service
POST   /api/v1/campaigns                 — Create campaign
GET    /api/v1/campaigns                 — List campaigns (filterable)
GET    /api/v1/campaigns/:id             — Get campaign detail
PUT    /api/v1/campaigns/:id             — Update campaign
PUT    /api/v1/campaigns/:id/status      — Change lifecycle status
DELETE /api/v1/campaigns/:id             — Delete campaign (draft only)

POST   /api/v1/campaigns/:id/ab-test     — Create A/B test
GET    /api/v1/campaigns/:id/ab-test     — Get A/B test results
POST   /api/v1/campaigns/:id/ab-test/conclude — Force conclude test

GET    /api/v1/campaigns/:id/performance — Performance metrics
GET    /api/v1/campaigns/:id/report      — Generate performance report
```

## Data Models

```sql
CREATE TABLE campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    channels TEXT[] NOT NULL,
    goals JSONB DEFAULT '{}', -- {"reach": 10000, "engagement_rate": 0.05}
    start_date TIMESTAMPTZ,
    end_date TIMESTAMPTZ,
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE campaign_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id),
    post_id UUID NOT NULL,
    variant VARCHAR(10), -- 'A', 'B', 'C' (for A/B testing)
    traffic_percentage INT DEFAULT 100,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ab_tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id),
    tenant_id UUID NOT NULL,
    status VARCHAR(20) DEFAULT 'running', -- 'running', 'concluded'
    winner_variant VARCHAR(10),
    confidence_level FLOAT,
    concluded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE campaign_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id),
    tenant_id UUID NOT NULL,
    date DATE NOT NULL,
    reach BIGINT DEFAULT 0,
    impressions BIGINT DEFAULT 0,
    engagement BIGINT DEFAULT 0,
    clicks BIGINT DEFAULT 0,
    conversions BIGINT DEFAULT 0,
    spend DECIMAL(10,2) DEFAULT 0
);

CREATE INDEX idx_campaigns_tenant ON campaigns(tenant_id, status);
CREATE INDEX idx_metrics_campaign ON campaign_metrics(campaign_id, date DESC);
```

## Kafka Events Published
- `campaign.started` — Campaign activated
- `campaign.completed` — Campaign ended
- `campaign.ab_test.concluded` — A/B test winner selected


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
    "service": "campaign",
    "resources": [
        {
            "name": "campaigns",
            "description": "Marketing campaigns",
            "actions": [
                "create",
                "read",
                "update",
                "delete"
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
4. So khớp in-memory O(1): parse `X-User-Permissions` thành một Set và đối chiếu với quyền yêu cầu của endpoint (ví dụ: `campaign:campaigns:create`).
   - Hỗ trợ wildcard: `*` (Super Admin bypass), `campaign:*` (Service bypass), và `campaign:campaigns:*` (Resource bypass).

## Security & Gateway Integration
- Dịch vụ được triển khai stateless phía sau Kong API Gateway.
- Gateway chịu trách nhiệm validate JWT token từ Keycloak, xác thực client scope `campaign`, và inject header `X-Tenant-ID` vào request.
- Dịch vụ tin tưởng hoàn toàn vào các header được Gateway inject để thực hiện logic nghiệp vụ và cô lập dữ liệu.
