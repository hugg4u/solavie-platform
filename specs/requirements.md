# Requirements Document

## Introduction

Nền tảng Marketing đa kênh (Facebook, Zalo, TikTok) tích hợp AI tự động hóa, xây dựng trên kiến trúc microservices. Hệ thống hỗ trợ doanh nghiệp quản lý tin nhắn, chatbot AI, tạo nội dung, lên lịch đăng bài, phân tích dữ liệu, quản lý khách hàng và chiến dịch marketing — tất cả từ một dashboard duy nhất. Hệ thống hỗ trợ multi-tenant và chatbot đa ngôn ngữ.

Giai đoạn 1 (MVP): Phục vụ trực tiếp cho hoạt động kinh doanh điện mặt trời, pin lưu trữ và sạc xe điện của Solavie.
Giai đoạn 2 (SaaS): Đóng gói thành dịch vụ bán cho các doanh nghiệp lắp đặt điện mặt trời và mở rộng sang F&B, bán lẻ, bất động sản.

## Glossary

- **Platform**: Hệ thống Marketing Platform tổng thể
- **Gateway**: Kong API Gateway — điểm vào duy nhất cho tất cả API requests
- **Auth_Service**: Keycloak — dịch vụ xác thực, phân quyền
- **Channel_Connector**: Dịch vụ kết nối Facebook/Zalo/TikTok
- **Messaging_Service**: Dịch vụ quản lý hộp thư hợp nhất
- **Chatbot_Service**: Dịch vụ chatbot AI (LangGraph + RAG)
- **Content_Service**: Dịch vụ quản lý & tạo nội dung AI
- **Scheduler_Service**: Dịch vụ lên lịch đăng bài & automation
- **Knowledge_Base**: Dịch vụ RAG pipeline & embedding
- **AI_Core**: Dịch vụ LLM Router & token optimization & MCP Host Gateway
- **Analytics_Service**: Dịch vụ phân tích & reporting (TimescaleDB)
- **CRM_Service**: Dịch vụ quản lý khách hàng, lead scoring, Deal Pipeline, O&M Ticketing
- **Campaign_Service**: Dịch vụ quản lý chiến dịch & A/B testing
- **Notification_Service**: Dịch vụ thông báo đa kênh
- **Comment_Manager**: Dịch vụ quản lý bình luận
- **Tenant_Config**: Dịch vụ cấu hình tập trung với hot-reload
- **DMS**: Document Management Service — quản lý tệp tin, thư mục ảo, quota
- **Link_Shortener**: Dịch vụ rút gọn URL & theo dõi click
- **Media_Processor**: Dịch vụ xử lý ảnh/video (Celery workers)
- **Tenant**: Một tổ chức/doanh nghiệp sử dụng hệ thống
- **Human_Agent**: Nhân viên hỗ trợ khách hàng
- **Handoff**: Chuyển hội thoại từ bot sang nhân viên
- **Confidence_Score**: Điểm tin cậy chatbot (0-1), < 0.7 → handoff
- **Deal**: Cơ hội bán hàng Solar qua 6 giai đoạn
- **Site_Survey**: Khảo sát mái nhà thực địa
- **O&M_Ticket**: Phiếu hỗ trợ vận hành & bảo trì sau bán hàng
- **MCP**: Model Context Protocol — giao thức kết nối AI với tools bên ngoài
- **RAG**: Retrieval-Augmented Generation — truy xuất tri thức nội bộ
- **NLI**: Natural Language Inference — kiểm tra tính xác thực câu trả lời AI
- **Semantic_Router**: Bộ định tuyến ngữ nghĩa — lọc câu hỏi không phù hợp

## Requirements

### Requirement 1: API Gateway và Routing

**User Story:** Là một developer, tôi muốn có một API Gateway tập trung, để tất cả requests được xử lý thống nhất và bảo mật.

#### Acceptance Criteria
1. THE Gateway SHALL route tất cả incoming API requests đến đúng microservice dựa trên URL path prefix
2. THE Gateway SHALL thực hiện SSL/TLS termination cho tất cả incoming connections
3. THE Gateway SHALL áp dụng rate limiting per-tenant dựa trên Header X-Tenant-ID, sử dụng Redis lưu trạng thái
4. WHEN request không có valid JWT Bearer token, THE Gateway SHALL trả về HTTP 401 Unauthorized
5. WHEN rate limit bị vượt quá, THE Gateway SHALL trả về HTTP 429 Too Many Requests kèm header Retry-After
6. THE Gateway SHALL tích hợp với Keycloak qua OIDC plugin để xác thực JWT
7. THE Gateway SHALL trích xuất claims từ JWT đã xác minh (tenant_id, sub, roles), tự động phân giải chúng thành danh sách quyền hạn động theo quy chuẩn `{service}:{resource}:{action}` thông qua 2 lớp cache (Redis và Kong Shared Memory) kết hợp API Fallback gọi tới Tenant Config Service. Đối với phân giải Wildcard: Gateway SHALL tự động gán quyền wildcard `*` cho vai trò `admin` nội bộ của tenant (giới hạn trong phạm vi tenant của họ bằng `X-Tenant-ID` ở downstream); đối với vai trò `system` hoặc `system_admin`, Gateway SHALL chỉ tự động gán quyền wildcard `*` và cho phép bypass khi và chỉ khi `tenant_id` trùng khớp với ID của Realm Master (`solavie-system-master`), ngược lại Gateway SHALL từ chối gán wildcard và trả về lỗi `403 Forbidden` ngay lập tức để ngăn chặn Privilege Escalation. Cuối cùng, Gateway SHALL ký số danh sách quyền này bằng HMAC-SHA256 sử dụng khóa bí mật chung và inject thành các headers bảo mật: X-Tenant-ID, X-User-ID, X-User-Permissions (chuỗi CSV) và X-Permissions-Signature trước khi forward tới downstream services.
8. IF downstream service unavailable hoặc timeout, THEN THE Gateway SHALL trả về HTTP 503 Service Unavailable
9. THE Gateway SHALL hỗ trợ WebSocket upgrade cho Dashboard realtime connections
10. THE Gateway SHALL vận hành ở chế độ DB-less (kong.yml) để đảm bảo stateless deployment

### Requirement 2: Authentication và Authorization

**User Story:** Là một admin, tôi muốn hệ thống xác thực và phân quyền tập trung, linh hoạt và bảo mật.

#### Acceptance Criteria
1. THE Auth_Service SHALL cung cấp OAuth2 Authorization Code Flow cho Dashboard và Client Credentials Flow cho service-to-service
2. THE Auth_Service SHALL phát hành JWT Access Token (TTL 15 phút) và Refresh Token (TTL 7 ngày) chứa claims: tenant_id, user_id, roles
3. THE Auth_Service SHALL hỗ trợ RBAC với 4 roles mặc định: Admin, Manager, Agent, Viewer
4. THE Auth_Service SHALL cho phép Tenant Admin tạo custom roles và gán permissions từ danh mục có sẵn (Dynamic RBAC). Danh mục này được tổng hợp động từ các API Manifest (`GET /api/v1/permissions/manifest`) của các microservices đang chạy.
5. THE Auth_Service SHALL hỗ trợ multi-tenant isolation qua Keycloak realm per tenant
6. IF user truy cập resource không thuộc tenant mình, THEN THE Auth_Service SHALL trả về HTTP 403 Forbidden
7. WHEN Tenant Admin thay đổi permissions của một Role, THE Auth_Service SHALL thu hồi ngay lập tức cached session liên quan trên Redis trong vòng < 1 giây để Gateway cập nhật.
8. WHEN Super Admin tạo Tenant mới, THE Auth_Service SHALL tự động khởi tạo Realm Keycloak, thiết lập default roles và tạo tài khoản Admin đầu tiên
9. THE Auth_Service SHALL gửi email kích hoạt tài khoản với token dùng một lần, hết hạn sau 24 giờ
10. THE Downstream Services SHALL xác thực chữ ký HMAC trên header X-Permissions-Signature bằng shared secret và thực hiện kiểm tra quyền in-memory O(1) dựa trên convention {service}:{resource}:{action}.
11. THE Dashboard SHALL tự động làm mới Access Token qua Refresh Token khi token còn < 30 giây hiệu lực (Silent Refresh)
12. THE Auth_Service SHALL tự động đăng xuất và hủy phiên khi người dùng không hoạt động quá thời gian cấu hình session_timeout_minutes

### Requirement 3: Event-Driven Architecture

**User Story:** Là một architect, tôi muốn các services giao tiếp bất đồng bộ qua events với đảm bảo độ tin cậy cao.

#### Acceptance Criteria
1. THE Platform SHALL sử dụng Apache Kafka cho tất cả async communication giữa services
2. THE Platform SHALL đảm bảo at-least-once delivery với consumer acknowledgment
3. THE Platform SHALL định nghĩa và đăng ký schema (Avro/Protobuf) cho tất cả Kafka events qua Schema Registry
4. WHEN event processing thất bại sau 3 retries với exponential backoff (1s, 2s, 4s), THEN THE Platform SHALL chuyển event vào dead-letter queue
5. THE Platform SHALL hỗ trợ event replay từ dead-letter queue cho debugging và recovery, chỉ cho phép Admin thực hiện
6. THE Platform SHALL bắt buộc mọi Kafka message payload chứa trường tenant_id trong Kafka Headers để consumer thực hiện tenant filtering
7. THE Platform SHALL bắt buộc mọi Kafka message chứa idempotency_key để tránh xử lý trùng lặp
8. THE Platform SHALL truyền W3C trace context (traceparent, tracestate) trong Kafka Headers cho distributed tracing
9. THE Platform SHALL publish mọi destructive action lên Kafka topic audit.events với đầy đủ actor, action, resource, timestamp
10. THE Platform SHALL định nghĩa các Kafka topics chuẩn: channel.message.received, channel.message.sent, channel.comment.received, messaging.handoff.requested, content.approved, content.published, scheduler.post.due, scheduler.post.failed, crm.lead.score.changed, campaign.event.*, comment.escalation, audit.events

### Requirement 4: Multi-tenancy và Data Isolation

**User Story:** Là một enterprise customer, tôi muốn dữ liệu của tổ chức tôi được cách ly hoàn toàn khỏi các tenant khác ở mọi tầng.

#### Acceptance Criteria
1. THE Platform SHALL áp dụng PostgreSQL Row-Level Security (RLS) trên cột tenant_id cho tất cả bảng dữ liệu
2. THE Platform SHALL filter mọi SQL query theo tenant_id lấy từ JWT claims; query không có tenant_id SHALL bị reject
3. THE Platform SHALL cách ly Kafka routing per-tenant qua mandatory tenant_id trong Kafka Headers
4. THE Platform SHALL cách ly vector embeddings per-tenant qua Qdrant metadata filter tenant_id trên mọi Collection
5. THE Platform SHALL tổ chức MinIO/S3 theo path prefix {tenant_id}/uploads/... và chỉ truy cập qua Presigned URLs TTL 15 phút
6. THE Platform SHALL cấu trúc mọi Redis cache key theo dạng {tenant_id}:{service_name}:{key}
7. THE Platform SHALL cô lập Keycloak realm per tenant để đảm bảo identity isolation
8. IF query hoặc request không có tenant_id hợp lệ, THEN THE Platform SHALL reject và ghi security warning vào audit log
9. THE Platform SHALL ngăn chặn MCP Server của tenant này truy cập dữ liệu của tenant khác bằng cách bắt buộc whitelisting Custom MCP Servers và tự động tiêm/ghi đè `tenant_id` từ JWT xác thực vào mọi tool arguments tại AI Core.
10. THE Platform SHALL áp dụng ranh giới `Roots Security Boundary` để giới hạn quyền truy cập thư mục ảo của các Custom MCP Server.

### Requirement 5: Service Communication

**User Story:** Là một developer, tôi muốn services giao tiếp hiệu quả, đáng tin cậy và có khả năng phục hồi khi lỗi.

#### Acceptance Criteria
1. THE Platform SHALL dùng REST (OpenAPI 3.0) làm default protocol cho non-critical paths
2. THE Platform SHALL dùng gRPC (Protobuf) cho hot-path: Messaging↔Chatbot và Chatbot↔AI Core để đạt latency < 50ms
3. THE Platform SHALL maintain shared protobuf schema repository cho tất cả gRPC services
4. THE Platform SHALL implement circuit breaker cho mọi sync calls: Open sau 5 failures trong 30s, Half-Open probe sau 60s, fallback graceful degradation
5. THE Platform SHALL implement saga pattern với compensating actions cho distributed transactions (ví dụ: Content → Scheduler → Channel Connector publish flow)
6. THE Platform SHALL sử dụng idempotency keys cho mọi cross-service action để đảm bảo exactly-once semantics
7. THE Platform SHALL hỗ trợ gRPC streaming cho AI response generation
8. IF circuit breaker ở trạng thái Open, THEN THE Platform SHALL trả về cached fallback response hoặc graceful error thay vì propagate failure

### Requirement 6: Observability

**User Story:** Là một DevOps engineer, tôi muốn giám sát toàn bộ hệ thống với đầy đủ metrics, traces và logs.

#### Acceptance Criteria
1. THE Platform SHALL thu thập metrics từ tất cả services qua Prometheus exporters (CPU, RAM, request rate, error rate, latency)
2. THE Platform SHALL cung cấp Grafana dashboards cho system health, business KPIs và AI performance
3. THE Platform SHALL implement distributed tracing qua Jaeger với OpenTelemetry, truyền trace context qua REST/gRPC/Kafka headers
4. THE Platform SHALL tập trung logs JSON có cấu trúc từ tất cả containers vào Loki, hiển thị trên Grafana
5. THE Platform SHALL track AI-specific metrics: chatbot E2E latency, token usage/cost per message, confidence score distribution, handoff rate, RAG accuracy
6. THE Platform SHALL expose health endpoints cho mọi service: GET /health (liveness), GET /ready (readiness), GET /metrics (Prometheus)
7. THE Platform SHALL sử dụng OpenTelemetry Collector làm trung gian thu thập và forward telemetry data

### Requirement 7: Deployment và Infrastructure

**User Story:** Là một DevOps engineer, tôi muốn hệ thống dễ deploy, scale và quản lý bí mật an toàn.

#### Acceptance Criteria
1. THE Platform SHALL cung cấp Docker Compose configuration cho môi trường dev/staging với tất cả 18 services và 6 infrastructure components
2. THE Platform SHALL cung cấp Kubernetes manifests cho production với resource limits và HPA cho Python AI services
3. THE Platform SHALL hỗ trợ canary deployment qua ArgoCD GitOps workflow
4. THE Platform SHALL deploy theo 5 phases có thứ tự dependency: Phase 1 (Keycloak+Kong+AI Core+KB), Phase 2 (Channel+Messaging+Chatbot), Phase 3 (Content+Scheduler), Phase 4 (Analytics+CRM+Campaign), Phase 5 (Comment+Notification+DMS+Config+Shortener+Media)
5. THE Platform SHALL dùng database-per-service pattern với PostgreSQL riêng cho mỗi service
6. THE Platform SHALL quản lý tất cả secrets (API keys, DB passwords, tokens) qua HashiCorp Vault
7. THE Platform SHALL cung cấp health check endpoints cho tất cả services để Kubernetes liveness/readiness probes
8. THE Platform SHALL yêu cầu tối thiểu 16 GB RAM (khuyến nghị 32 GB RAM), 8 vCPU, 150 GB NVMe SSD để vận hành ổn định

### Requirement 8: Caching và Performance

**User Story:** Là một user, tôi muốn hệ thống phản hồi nhanh và chi phí AI tối ưu.

#### Acceptance Criteria
1. THE Platform SHALL dùng Redis 7 cho caching, pub/sub, sessions và embedding cache
2. THE Platform SHALL đạt chatbot E2E response < 2 giây (từ khi nhận tin đến khi gửi trả lời)
3. THE Platform SHALL đạt vector search < 10ms p95 qua int8 quantization và RAM index trên Qdrant
4. THE Platform SHALL đạt token cost < $0.005 per message qua model routing + prompt caching + context compression
5. THE Platform SHALL áp dụng prompt caching cho system prompts và tài liệu tĩnh, giảm tối thiểu 50% input token cost
6. THE Platform SHALL đạt gRPC hot-path latency (Messaging↔Chatbot↔AI Core) < 50ms p95
7. THE Platform SHALL đạt Dashboard load time < 3 giây trên kết nối 4G qua SSR + code splitting + CDN
8. THE Platform SHALL đạt Notification delivery < 3 giây cho handoff alerts qua priority queue

### Requirement 9: Object Storage và Document Management

**User Story:** Là một user, tôi muốn upload, quản lý và chia sẻ media files và tài liệu một cách bảo mật.

#### Acceptance Criteria
1. THE Platform SHALL dùng MinIO (S3-compatible) cho tất cả media files và documents
2. THE Platform SHALL generate Presigned URLs với TTL 15 phút cho secure access thay vì expose direct URLs
3. THE Platform SHALL tổ chức files theo path prefix per-tenant: {tenant_id}/uploads/...
4. THE Platform SHALL hỗ trợ resumable upload cho files > 10MB
5. THE Platform SHALL kiểm tra và chặn tệp tin chứa mã độc trước khi lưu vào MinIO
6. THE Platform SHALL giới hạn kích thước: tối đa 50MB cho documents, 100MB cho video
7. THE Platform SHALL kiểm tra quota lưu trữ của Tenant trước khi cho phép upload; từ chối nếu vượt giới hạn
8. THE Platform SHALL hỗ trợ quản lý thư mục ảo dạng cây (virtual folder tree) per-tenant
9. THE Platform SHALL xử lý media qua Celery workers: nén ảnh, tạo thumbnail, transcode video sang định dạng chuẩn mạng xã hội

### Requirement 10: Frontend Dashboard

**User Story:** Là một user, tôi muốn giao diện web trực quan, realtime và phù hợp với vai trò của mình.

#### Acceptance Criteria
1. THE Dashboard SHALL cung cấp unified interface cho tất cả features: Inbox, CRM, Content, Scheduler, Analytics, Campaign, Settings
2. THE Dashboard SHALL hiển thị realtime updates qua WebSocket: tin nhắn mới, typing indicator, handoff alerts, notifications
3. THE Dashboard SHALL responsive với breakpoint tối thiểu 768px (tablet)
4. THE Dashboard SHALL ẩn/hiện features và data dựa trên RBAC roles của user đang đăng nhập
5. THE Dashboard SHALL load < 3 giây trên kết nối 4G qua Next.js 14 SSR + code splitting + CDN
6. THE Dashboard SHALL cung cấp Kanban Board cho Solar Deal Pipeline với 6 giai đoạn
7. THE Dashboard SHALL cung cấp Calendar View (tuần/tháng) cho Scheduler với drag-and-drop
8. THE Dashboard SHALL hiển thị tag kênh nguồn (Facebook/Zalo/TikTok) rõ ràng trên mỗi tin nhắn trong Inbox

### Requirement 11: Tenant Configuration Management

**User Story:** Là một admin, tôi muốn cấu hình hệ thống linh hoạt mà không cần restart services.

#### Acceptance Criteria
1. THE Tenant_Config SHALL cung cấp REST API CRUD cho tất cả cấu hình của Tenant
2. WHEN admin lưu thay đổi cấu hình, THE Tenant_Config SHALL đồng bộ tham số mới xuống tất cả services đang chạy trong < 5 giây qua Redis Pub/Sub (hot-reload)
3. THE Tenant_Config SHALL lưu cấu hình vào DB đồng thời ghi vào Redis cache key {tenant_id}:config:{category}
4. THE Tenant_Config SHALL cung cấp gRPC interface cho services truy vấn nhanh khi cache miss
5. THE Tenant_Config SHALL hỗ trợ cấu hình động cho: chatbot (bật/tắt, system prompt, confidence threshold, AI vision), chat routing (giờ làm việc, handoff algorithm, timeout), content (approval workflow, quality threshold), CRM (lead scoring rules, hot lead threshold), security (data masking, session timeout, audit retention)

### Requirement 12: Missing Services — DMS, Link Shortener, Media Processor

**User Story:** Là một user, tôi muốn quản lý tài liệu, theo dõi hiệu quả link marketing và xử lý media tự động.

#### Acceptance Criteria
1. THE DMS SHALL quản lý tệp tin với virtual folder tree, version control (tối đa 5 phiên bản/file), quota per-tenant
2. THE DMS SHALL hỗ trợ access mode: Public (CDN link cố định) và Private (Presigned URL TTL 15 phút)
3. THE Link_Shortener SHALL rút gọn URL chiến dịch và theo dõi lượt click với metadata: IP, user agent, country, timestamp
4. THE Link_Shortener SHALL hỗ trợ A/B Testing labels (A/B) cho campaign variants
5. THE Media_Processor SHALL xử lý ảnh (nén, thumbnail) và video (transcode sang định dạng chuẩn) qua Celery async workers
6. THE Media_Processor SHALL giới hạn video tối đa 100MB và ghi đệm SSD thay vì RAM để tránh OOM
