# Design Document — Marketing Platform (System-Level)

## Overview

Hệ thống Marketing Platform đa kênh — **18 services** + 6 infrastructure components, giao tiếp qua event-driven architecture (Kafka) kết hợp sync communication (REST + gRPC). Polyglot microservices: Python (AI), Node.js (I/O), Java (reliability).

**4 services bổ sung so với thiết kế ban đầu:**
- **Tenant Config** (Port 3006): Quản lý tập trung cấu hình hệ thống với hot-reload < 5s
- **DMS** (Port 3007): Document Management — virtual folder tree, version control, quota, malware scan
- **Link Shortener** (Port 3009): Rút gọn URL chiến dịch, theo dõi click, A/B Testing
- **Media Processor** (Port 8008): Xử lý ảnh/video bất đồng bộ qua Celery workers

## Tech Stack Tổng Quan

| Layer | Technology | Mục đích |
|-------|-----------|----------|
| Gateway | Kong | API routing, rate limiting, OIDC, SSL |
| Auth | Keycloak 26.1.2 | OAuth2, OIDC, RBAC, Keycloak Organizations |
| Frontend | Next.js 14 + TypeScript | Web dashboard, SSR, realtime |
| Message Queue | Apache Kafka | Event-driven async communication |
| Cache | Redis 7 | Caching, pub/sub, sessions, embedding cache |
| Database | PostgreSQL 16 (per-service) | Primary data store |
| Vector DB | Qdrant | RAG embeddings, hybrid search |
| Object Storage | MinIO (S3-compatible) | Media, documents |
| Observability | Prometheus + Grafana + Jaeger + Loki | Full observability stack |
| Deployment | Docker Compose → Kubernetes | Container orchestration |
| CI/CD | GitHub Actions + ArgoCD | Build, test, deploy |
| Secret Management | HashiCorp Vault | Secrets, tokens, keys |

## Service Registry

| # | Service | Language | Framework | Port | Database |
|---|---------|----------|-----------|------|----------|
| 1 | Gateway | - | Kong 3.7 | 8000/8001 | - (DB-less, kong.yml) |
| 2 | Auth | Java | Keycloak 26.1.2 | 8080 | keycloak_db |
| 3 | Channel Connector | Node.js 20 | NestJS | 3001 | channel_connector_db |
| 4 | Messaging | Node.js 20 | NestJS | 3002 | messaging_db |
| 5 | Chatbot | Python 3.12 | FastAPI + LangGraph | 8001/50051(gRPC) | chatbot_db |
| 6 | Content | Python 3.12 | FastAPI | 8002 | content_db |
| 7 | Scheduler | Java 21 | Spring Boot 3 + Quartz | 8003 | scheduler_db |
| 8 | Knowledge Base | Python 3.12 | FastAPI | 8004 | knowledge_db + Qdrant |
| 9 | AI Core | Python 3.12 | FastAPI + gRPC | 8005/50052(gRPC) | ai_core_db |
| 10 | Analytics | Java 21 | Spring Boot 3 | 8006 | analytics_db (TimescaleDB) |
| 11 | CRM | Node.js 20 | NestJS | 3003 | crm_db |
| 12 | Campaign | Java 21 | Spring Boot 3 | 8007 | campaign_db |
| 13 | Notification | Node.js 20 | NestJS | 3004 | notification_db |
| 14 | Comment Manager | Node.js 20 | NestJS | 3005 | comment_db |
| 15 | Tenant Config | Node.js 20 | NestJS | 3006 | config_db |
| 16 | DMS | Node.js 20 | NestJS | 3007 | dms_db |
| 17 | Link Shortener | Node.js 20 | Fastify | 3009 | shortener_db |
| 18 | Media Processor | Python 3.12 | FastAPI + Celery | 8008 | - (stateless, Redis broker) |

## Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        Dashboard["Dashboard (Next.js)"]
        Customer["Customer Browser\n(short link redirect)"]
    end

    subgraph "Gateway Layer"
        Kong["Kong API Gateway"]
    end

    subgraph "Auth Layer"
        Keycloak["Keycloak"]
    end

    subgraph "Node.js Services"
        CC["Channel Connector :3001"]
        MSG["Messaging :3002"]
        CRM["CRM :3003\n(Deal Pipeline, Survey,\nROI, Proposal, O&M)"]
        NOTIF["Notification :3004"]
        COMMENT["Comment Manager :3005"]
        TCFG["Tenant Config :3006\n(Hot Reload, gRPC)"]
        DMS["DMS :3007\n(Virtual Folder, Versions,\nQuota, Malware Scan)"]
        LSHORT["Link Shortener :3009\n(Circuit Breaker, A/B)"]
    end

    subgraph "Python Services"
        CB["Chatbot :8001\n(LangGraph, Guardrails,\nLead Capture, Breakpoints)"]
        CONTENT["Content :8002"]
        KB["Knowledge Base :8004"]
        AI["AI Core :8005"]
        MPROC["Media Processor :8008\n(Celery, Image/Video)"]
    end

    subgraph "Java Services"
        SCHED["Scheduler :8003\n(Quartz)"]
        ANALYTICS["Analytics :8006\n(TimescaleDB)"]
        CAMPAIGN["Campaign :8007"]
    end

    subgraph "Infrastructure"
        Kafka["Apache Kafka"]
        Redis["Redis\n(cache, pub/sub, Celery broker)"]
        PG["PostgreSQL (per-service)"]
        Qdrant["Qdrant"]
        MinIO["MinIO\n(uploads + processed)"]
    end

    subgraph "External"
        FB["Facebook API"]
        ZALO["Zalo OA API"]
        TIKTOK["TikTok API"]
        LLM["LLM Providers"]
        HelioScope["HelioScope/OpenSolar API"]
    end

    Dashboard -->|HTTPS/WSS| Kong
    Customer -->|GET /{short_code}| Kong
    Kong -->|OIDC| Keycloak
    Kong --> CC & MSG & CRM & NOTIF & COMMENT & CONTENT & SCHED & ANALYTICS & CAMPAIGN
    Kong --> TCFG & DMS & LSHORT & MPROC

    MSG -->|gRPC| CB
    CB -->|gRPC| AI
    CB & CONTENT --> KB
    AI --> LLM
    CC --> FB & ZALO & TIKTOK
    CRM -->|ROI 3rd party| AI
    AI --> HelioScope

    CC -->|publish| Kafka
    MSG & CRM & ANALYTICS & NOTIF & COMMENT -->|consume| Kafka
    SCHED & CONTENT & CAMPAIGN -->|publish| Kafka
    DMS -->|dms.file.uploaded| Kafka
    Kafka -->|media.process.requested| MPROC
    MPROC -->|media.job.completed/failed| Kafka

    TCFG -->|SETEX + PUBLISH config.updates| Redis
    Redis -->|SUBSCRIBE config.updates| CB & CRM & DMS & CONTENT

    All -->|metrics| Prometheus
    All --> PG
    KB --> Qdrant
    All --> Redis
    CONTENT & KB & DMS & CRM --> MinIO
    MPROC --> MinIO
```

## Components and Interfaces

Các communication patterns giữa 18 services được mô tả qua Protocol Matrix và Kafka Topics bên dưới.

### Protocol Matrix

| From → To | Protocol | Lý do |
|-----------|----------|-------|
| Dashboard → Kong | HTTPS + WebSocket | Security + realtime |
| Kong → Services | REST (HTTP/JSON) | Standard, OpenAPI |
| Messaging → Chatbot | gRPC (Protobuf) | Hot path, < 50ms |
| Chatbot → AI Core | gRPC (Protobuf) | Hot path, streaming |
| Services → Tenant Config | gRPC (Protobuf) | Config query on cache miss |
| Channel Connector → Messaging | Kafka | Async, decoupled |
| Any → Notification | Kafka | Fire-and-forget |
| Messaging → Dashboard | Redis Pub/Sub + WS | Realtime |
| Scheduler → Channel Connector | Kafka | Scheduled events |
| Analytics ← All | Kafka (consume) | Event sourcing |
| DMS → Media Processor | Kafka (media.process.requested) | Async media processing |
| Media Processor → DMS/Content | Kafka (media.job.completed) | Processing result notification |
| Tenant Config → All Services | Redis Pub/Sub (config.updates) | Hot reload < 5s |
| CRM → DMS | REST | Upload survey photos, save proposal PDF |

### Kafka Topics

| Topic | Producer | Consumer(s) | Schema |
|-------|----------|-------------|--------|
| `channel.message.received` | Channel Connector | Messaging, Analytics, CRM | MessageEvent |
| `channel.message.sent` | Channel Connector | Analytics | MessageSentEvent |
| `channel.comment.received` | Channel Connector | Comment Manager, Analytics | CommentEvent |
| `messaging.conversation.created` | Messaging | CRM | ConversationEvent |
| `messaging.handoff.requested` | Messaging/Chatbot | Notification | HandoffEvent |
| `content.approved` | Content | Scheduler | ContentEvent |
| `content.published` | Content | Analytics, Campaign | PublishEvent |
| `scheduler.post.due` | Scheduler | Channel Connector | ScheduleEvent |
| `scheduler.post.failed` | Scheduler | Notification | FailureEvent |
| `crm.lead.score.changed` | CRM | Notification | LeadScoreEvent |
| `crm.deal.stage.changed` | CRM | Analytics, Notification | DealStageEvent |
| `crm.ticket.created` | CRM | Notification | TicketEvent |
| `crm.ticket.closed` | CRM | Notification (CSAT) | TicketClosedEvent |
| `campaign.event.*` | Campaign | Analytics, Link Shortener | CampaignEvent |
| `comment.escalation` | Comment Manager | Notification | EscalationEvent |
| `dms.file.uploaded` | DMS | Media Processor, Knowledge Base | DmsFileEvent |
| `dms.file.malware_detected` | DMS | Notification | MalwareEvent |
| `dms.quota.warning` | DMS | Notification | QuotaWarningEvent |
| `media.process.requested` | DMS, Content | Media Processor | MediaJobEvent |
| `media.job.completed` | Media Processor | DMS, Content | MediaJobResultEvent |
| `media.job.failed` | Media Processor | Notification | MediaJobFailedEvent |

### Audit Topic

| Topic | Producer | Consumer(s) | Schema |
|-------|----------|-------------|--------|
| `audit.events` | All services | Audit consumer (Analytics/Observability) | AuditEvent |

### gRPC Services (Shared Protobuf)

```protobuf
// proto/chatbot.proto
service ChatbotService {
  rpc ProcessMessage(ChatRequest) returns (ChatResponse);
  rpc StreamResponse(ChatRequest) returns (stream ChatChunk);
}

// proto/ai_core.proto
service AICore {
  rpc Complete(CompletionRequest) returns (CompletionResponse);
  rpc StreamComplete(CompletionRequest) returns (stream CompletionChunk);
  rpc Embed(EmbedRequest) returns (EmbedResponse);
  rpc RunAgent(AgentRequest) returns (AgentResponse);  // ReAct agent
}
```

### MCP Services (Custom SSE Servers)

Hệ thống tích hợp Model Context Protocol (MCP) theo mô hình Host - Client (Custom SSE Servers):
- **AI Core (MCP Host Gateway)**: Đóng vai trò là MCP Host. Khi nhận yêu cầu từ Chatbot, AI Core sẽ kết nối đến các Custom MCP SSE Servers tương ứng dựa trên cấu hình tenant để truy xuất danh sách công cụ (Tools) và thực thi chúng.
- **8 Dịch vụ Nghiệp vụ (MCP Client/SSE Servers)**: Mỗi dịch vụ đóng vai trò là một Custom MCP SSE Server độc lập cung cấp các công cụ nghiệp vụ đặc thù qua giao thức Server-Sent Events (SSE) tại endpoint `/api/v1/{service_name}/mcp`:
  1. `CRM Service` (`/api/v1/crm/mcp`): Cung cấp công cụ quản lý cơ hội bán hàng, ROI calculator, thông tin khảo sát thực địa.
  2. `Knowledge Base` (`/api/v1/knowledge/mcp`): Cung cấp công cụ tìm kiếm ngữ nghĩa, truy vấn RAG và quản lý chunks tài liệu.
  3. `Messaging Service` (`/api/v1/messaging/mcp`): Cung cấp công cụ gửi tin nhắn, lấy lịch sử hội thoại và quản lý trạng thái tin nhắn.
  4. `Analytics Service` (`/api/v1/analytics/mcp`): Cung cấp công cụ truy xuất báo cáo doanh thu, hiệu suất chatbot, tỷ lệ handoff và báo cáo chiến dịch.
  5. `Scheduler Service` (`/api/v1/scheduler/mcp`): Cung cấp công cụ quản lý hàng đợi social, lên lịch đăng bài và kiểm tra trạng thái bài đăng.
  6. `Comment Manager` (`/api/v1/comment/mcp`): Cung cấp công cụ quản lý bình luận đa kênh, lọc bình luận tiêu cực và kích hoạt luồng leo thang (escalation).
  7. `Notification Service` (`/api/v1/notification/mcp`): Cung cấp công cụ gửi thông báo khẩn cấp qua SMS, Email và Web Push.
  8. `Content Service` (`/api/v1/content/mcp`): Cung cấp công cụ tạo bài viết tự động bằng AI, tối ưu hóa bài viết (SEO) và duyệt nội dung nháp.

#### Quy trình Bảo mật & Cách ly Đa thuê (Multi-tenancy Integration)
1. **Dynamic tenant_id Injection**: Khi AI Core chuyển tiếp yêu cầu gọi công cụ (Call Tool) tới các Custom MCP SSE Servers, AI Core tự động trích xuất `tenant_id` từ JWT Claims của người dùng/chatbot và tiêm trực tiếp vào tham số gọi công cụ. Các Custom MCP SSE Servers bắt buộc phải xác thực tham số này để tránh rò rỉ dữ liệu chéo.
2. **Tenant Whitelisting**: Mỗi tenant chỉ được phép truy cập danh sách các Custom MCP Servers đã được đăng ký và phê duyệt (Whitelisted) trong dịch vụ cấu hình `Tenant Config`.
3. **Roots Security Boundary**: Các Custom MCP Servers tương tác với hệ thống tệp tin ảo (DMS) hoặc đĩa cục bộ phải được giới hạn chặt chẽ trong thư mục gốc được chỉ định dành riêng cho tenant đó (`{tenant_id}/`), cấm hoàn toàn hành vi duyệt thư mục cấp cha (Directory Traversal).

## Data Models

Mỗi service sử dụng database riêng (database-per-service pattern). Xem chi tiết data models tại spec của từng service:
- `services/crm/design.md` — contacts, crm_deals, crm_surveys, crm_proposals, crm_tickets, merge_suggestions
- `services/messaging/design.md` — conversations, messages
- `services/chatbot/design.md` — chatbot_logs, action_approvals
- `services/knowledge-base/design.md` — documents, chunks
- `services/dms/design.md` — dms_folders, dms_files, dms_file_versions
- `services/link-shortener/design.md` — shortened_links, link_clicks
- `services/media-processor/design.md` — processing_jobs
- `services/tenant-config/design.md` — tenant_configs, config_audit_logs
- `services/analytics/design.md` — metrics (TimescaleDB hypertable)
- `services/campaign/design.md` — campaigns, ab_tests, campaign_metrics

## Shared Standards (BẮT BUỘC)

Tất cả services PHẢI tuân theo các chuẩn chung định nghĩa trong `shared/standards.md`:

1. **Unified Confidence Scale** — thang điểm 0-1 thống nhất cho mọi AI decision
2. **Handoff/Escalation Standard** — triggers và terminology thống nhất
3. **Rate Limiting** — token bucket, return 429 + Retry-After
4. **Structured Errors** — format JSON chuẩn, retriable flag
5. **Audit Logging** — mọi destructive action ghi `audit.events`
6. **Saga Pattern** — distributed transactions với compensating actions
7. **Health Checks** — `/health`, `/ready`, `/metrics`
8. **Multi-tenancy** — filter tenant_id mọi layer
9. **Tracing** — W3C trace context, OpenTelemetry
10. **Global Permission Specification & Signed Headers**:
    - Tất cả các mã quyền hạn trong hệ thống phải tuân thủ convention: `{service_name}:{resource_type}:{action_name}`.
    - Hỗ trợ ký tự đại diện `*` (wildcard) ở bất kỳ cấp độ nào để bypass in-memory check tại microservice.
    - Tự động phân giải wildcard `*` tại Gateway: vai trò `admin` của tenant được gán wildcard `*` (nhưng dữ liệu bị cô lập theo tenant_id ở DB); vai trò `system` hoặc `system_admin` chỉ được gán wildcard `*` và bypass khi và chỉ khi token được phát hành mức Realm hệ thống (không thuộc Organization nào). Gateway chặn và trả về `403 Forbidden` nếu các vai trò hệ thống này được gán ở Organization của tenant thông thường (Privilege Escalation Protection).
    - Mọi microservice (downstream service) khi nhận request nội bộ từ Gateway bắt buộc phải xác thực chữ ký HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET` để chống giả mạo.
    - Mọi microservice bắt buộc phải cung cấp API manifest `GET /api/v1/permissions/manifest` liệt kê các tài nguyên và hành động mà nó hỗ trợ để Dashboard tổng hợp và render UI cấu hình động.

Xem chi tiết: `shared/standards.md`

## Resilience Patterns

### Circuit Breaker
- Mọi sync call giữa services đều qua circuit breaker
- States: Closed → Open (after 5 failures in 30s) → Half-Open (probe after 60s)
- Fallback: graceful degradation response

### Retry Policy
- Exponential backoff: 1s, 2s, 4s (max 3 retries)
- Idempotency key cho webhook deduplication
- Dead-letter queue sau 3 retries

### Saga Pattern
- Publish post: Content → Scheduler → Channel Connector
- Compensating actions on failure (rollback)

### Audit & Consistency
- Mọi destructive action ghi `audit.events` Kafka topic
- Chatbot reply flow + Content publish flow dùng saga pattern (xem `shared/standards.md`)
- Idempotency keys cho mọi cross-service action

## Multi-tenancy Strategy

| Layer | Isolation Method |
|-------|-----------------|
| Auth | Keycloak Organizations within shared realm |
| Database | Row-level security (tenant_id column) |
| Kafka | Message header tenant_id + consumer filtering |
| Qdrant | Metadata filter (tenant_id) per collection |
| MinIO | Bucket prefix per tenant |
| Redis | Key prefix per tenant |
| MCP | Tenant Whitelisting, Dynamic tenant_id Injection, Roots Security Boundary |

## Deployment Phases

| Phase | Services | Dependencies |
|-------|----------|-------------|
| 1 | Keycloak + Kong + AI Core + Knowledge Base | PostgreSQL, Qdrant, Redis, Kafka |
| 2 | Channel Connector + Messaging + Chatbot | Phase 1 + External APIs |
| 3 | Content + Scheduler | Phase 2 |
| 4 | Analytics + CRM + Campaign | Phase 3 |
| 5 | Comment Manager + Notification + Tenant Config + DMS + Link Shortener + Media Processor | Phase 4 |

## Performance Targets

| Metric | Target | Strategy |
|--------|--------|----------|
| Chatbot E2E | < 2s | gRPC + parallel processing + streaming |
| Vector search | < 10ms p95 | int8 quantization + RAM index + 512 dims |
| Token cost/msg | < $0.005 | Model routing + context compression + caching |
| RAG accuracy | > 85% | Hybrid search + reranking |
| Embedding throughput | > 1000 docs/min | Batch embedding + async |
| Dashboard load | < 3s (4G) | SSR + code splitting + CDN |
| Notification delivery | < 3s (handoff) | Priority queue + direct push |

## Observability Stack

```
┌─────────────────────────────────────────────┐
│              Grafana Dashboards              │
├──────────┬──────────────┬───────────────────┤
│Prometheus│    Jaeger     │       Loki        │
│ (metrics)│  (tracing)   │      (logs)       │
├──────────┴──────────────┴───────────────────┤
│         OpenTelemetry Collector              │
├─────────────────────────────────────────────┤
│    All Services (instrumented)              │
└─────────────────────────────────────────────┘
```

Mỗi service expose:
- `GET /health` — liveness probe
- `GET /ready` — readiness probe
- `GET /metrics` — Prometheus metrics endpoint

## Chi tiết từng service

Xem specs riêng tại:
- `services/channel-connector/` — Node.js, NestJS
- `services/messaging/` — Node.js, NestJS
- `services/chatbot/` — Python, FastAPI + LangGraph + gRPC
- `services/content/` — Python, FastAPI
- `services/scheduler/` — Java, Spring Boot + Quartz
- `services/knowledge-base/` — Python, FastAPI + Qdrant
- `services/ai-core/` — Python, FastAPI + gRPC
- `services/analytics/` — Java, Spring Boot + TimescaleDB
- `services/crm/` — Node.js, NestJS (Solar Deal Pipeline, Site Survey, ROI Calculator, O&M Ticketing)
- `services/campaign/` — Java, Spring Boot
- `services/notification/` — Node.js, NestJS
- `services/comment-manager/` — Node.js, NestJS
- `services/tenant-config/` — Node.js, NestJS (Hot Reload, gRPC Config Reader)
- `services/dms/` — Node.js, NestJS (Virtual Folder Tree, Version Control, Quota, Malware Scan)
- `services/link-shortener/` — Node.js, Fastify (URL Shortening, Click Tracking, A/B Testing)
- `services/media-processor/` — Python, FastAPI + Celery (Image Compression, Video Transcode)


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
