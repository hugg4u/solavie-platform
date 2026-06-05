# Design — Comment Manager Service

## Overview

Dịch vụ quản lý bình luận trên Facebook/TikTok — Node.js 20, NestJS, Port 3005, PostgreSQL (comment_db). Phân loại bình luận (spam/negative/question/praise/neutral) qua AI Core, tự động ẩn spam (>= 0.85), escalate negative (>= 0.60), auto-reply FAQ (>= 0.70).

## Architecture

Xem **Classification Flow** bên dưới.

## Components and Interfaces

Xem **API Design**, **Kafka Events**, và **Classification Flow** bên dưới.
| Component | Technology |
|-----------|-----------|
| Runtime | Node.js 20 |
| Framework | NestJS 10 |
| Language | TypeScript 5 |
| Database | PostgreSQL 16 |
| ORM | Prisma |
| Queue | KafkaJS |
| AI | AI Core (REST client) |
| Testing | Jest |

## API Design

```
GET    /api/v1/comments                  — List comments (filterable: post_id, classification, channel)
GET    /api/v1/comments/:id              — Get comment detail
PUT    /api/v1/comments/:id/classify     — Override classification
POST   /api/v1/comments/:id/reply        — Manual reply to comment
PUT    /api/v1/comments/:id/hide         — Hide comment
PUT    /api/v1/comments/:id/unhide       — Unhide comment
GET    /api/v1/comments/stats            — Classification stats (accuracy, volume by type)
GET    /api/v1/comments/mcp              — SSE connection endpoint for MCP Server
POST   /api/v1/comments/mcp/messages     — JSON-RPC message transport for MCP Server
```

## Data Models

```sql
CREATE TABLE comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    post_id UUID NOT NULL,
    channel VARCHAR(20) NOT NULL,
    platform_comment_id VARCHAR(255) NOT NULL,
    author_id VARCHAR(255) NOT NULL,
    author_name VARCHAR(255),
    content TEXT NOT NULL,
    classification VARCHAR(20), -- 'spam', 'negative', 'question', 'praise', 'neutral'
    classification_confidence FLOAT,
    is_override BOOLEAN DEFAULT FALSE,
    is_hidden BOOLEAN DEFAULT FALSE,
    auto_reply_sent BOOLEAN DEFAULT FALSE,
    auto_reply_text TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE classification_overrides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    comment_id UUID NOT NULL REFERENCES comments(id),
    tenant_id UUID NOT NULL,
    original_classification VARCHAR(20) NOT NULL,
    new_classification VARCHAR(20) NOT NULL,
    overridden_by UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_comments_post ON comments(post_id, created_at DESC);
CREATE INDEX idx_comments_tenant ON comments(tenant_id, classification, created_at DESC);
CREATE INDEX idx_overrides_tenant ON classification_overrides(tenant_id, created_at DESC);
```

## Kafka Events

### Consumed: `channel.comment.received`
→ Classify + auto-action

### Published: `comment.escalation`
```json
{
  "tenant_id": "uuid",
  "comment_id": "uuid",
  "post_id": "uuid",
  "classification": "negative",
  "content": "string",
  "author_name": "string"
}
```

## Classification Flow

```mermaid
graph TD
    NEW[New Comment] --> CLASSIFY[AI Core: Classify]
    CLASSIFY --> SPAM{Spam?}
    SPAM -->|Yes| HIDE[Auto-hide]
    SPAM -->|No| NEG{Negative?}
    NEG -->|Yes| ESCALATE[Escalate → Notification]
    NEG -->|No| QUESTION{Question?}
    QUESTION -->|Yes| REPLY[Auto-reply via AI Core]
    QUESTION -->|No| PRAISE{Praise?}
    PRAISE -->|Yes| LIKE[Auto-like]
    PRAISE -->|No| STORE[Store as neutral]
```


## Model Context Protocol (MCP) Tools

Dịch vụ Comment Manager Service đóng vai trò là một MCP SSE Server đăng ký các công cụ sau:

### 1. Tool: `hide_comment`
* **Mô tả:** Ẩn hoặc hiện bình luận cụ thể trên nền tảng mạng xã hội nhằm kiểm duyệt nội dung.
* **Tham số đầu vào (Schema):**
  * `comment_id` (string, UUID, required): ID của bình luận cần kiểm duyệt trong hệ thống.
  * `is_hidden` (boolean, optional, mặc định là true): Chỉ định ẩn (`true`) hoặc hiện (`false`).
  * `reason` (string, optional): Lý do ẩn (ví dụ: 'spam', 'negative', 'harassment').
* **Bảo mật:** Tham số `tenant_id` sẽ được tự động tiêm từ header `X-Tenant-ID` vào tham số thực thi hàm nghiệp vụ nhằm đảm bảo an toàn truy vấn và cập nhật trên database Prisma, cấm LLM tự sửa đổi.

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

## Security & Gateway Integration
- Dịch vụ được triển khai stateless phía sau Kong API Gateway.
- Gateway chịu trách nhiệm validate JWT token từ Keycloak, xác thực client scope `comment-manager`, và inject header `X-Tenant-ID` vào request.
- Dịch vụ tin tưởng hoàn toàn vào các header được Gateway inject để thực hiện logic nghiệp vụ và cô lập dữ liệu.
