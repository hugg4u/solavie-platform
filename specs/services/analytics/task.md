# Task Checklist — ANALYTICS Service

## Overview
This document tracks the implementation checklist for **ANALYTICS Service** based on the system specifications.

### Technical Stack & Configuration
- **Language:** Java 21
- **Framework:** Spring Boot 3
- **Database:** PostgreSQL 16 + TimescaleDB extension
- **Queue:** Kafka

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/analytics/requirements.md)
- [Design](file:///specs/solavie-system/services/analytics/design.md)
- [Logging](file:///specs/solavie-system/services/analytics/logging.md)
- [Business Logic](file:///specs/solavie-system/services/analytics/business-logic.md)

---

## Tasks Checklist

### Task 1: 1: Metrics Collection
**Acceptance Criteria Implementation:**
- [ ] AC 1.1: THE Analytics_Service SHALL thu thập engagement metrics: likes, comments, shares, reach, clicks
- [ ] AC 1.2: THE Analytics_Service SHALL consume events từ Kafka (messages, posts, campaigns)
- [ ] AC 1.3: THE Analytics_Service SHALL aggregate metrics per-channel, per-post, per-campaign
- [ ] AC 1.4: Metrics SHALL cập nhật trong vòng 5 phút

### Task 2: 2: Dashboard Metrics
**Acceptance Criteria Implementation:**
- [ ] AC 2.1: THE Analytics_Service SHALL cung cấp realtime metrics API
- [ ] AC 2.2: THE Analytics_Service SHALL hỗ trợ custom date range filtering
- [ ] AC 2.3: THE Analytics_Service SHALL hỗ trợ period comparison (this week vs last week)
- [ ] AC 2.4: THE Analytics_Service SHALL cung cấp per-channel và cross-channel views

### Task 3: 3: AI Insights
**Acceptance Criteria Implementation:**
- [ ] AC 3.1: THE Analytics_Service SHALL generate weekly insights report tự động (via AI Core)
- [ ] AC 3.2: Insights SHALL include: top performing content, best posting times, audience trends
- [ ] AC 3.3: THE Analytics_Service SHALL detect anomalies (sudden drops/spikes)

### Task 4: 4: Report Export
**Acceptance Criteria Implementation:**
- [ ] AC 4.1: THE Analytics_Service SHALL export reports dạng PDF và CSV
- [ ] AC 4.2: THE Analytics_Service SHALL hỗ trợ scheduled reports (weekly email)
- [ ] AC 4.3: Reports SHALL customizable per-tenant

### Task 5: Implement Business Logic Rules
**Business Validations:**
- [ ] Tổng quan vai trò: Consume events từ Kafka → lưu metrics vào TimescaleDB
- [ ] Tổng quan vai trò: Aggregate metrics (realtime + daily/weekly)
- [ ] Tổng quan vai trò: Generate AI insights (weekly report)
- [ ] Tổng quan vai trò: Export reports (PDF/CSV)
- [ ] Luồng 3: AI Weekly Insights: Messages received: {messages_received} ({messages_change}% vs last week)
- [ ] Luồng 3: AI Weekly Insights: Messages sent: {messages_sent}
- [ ] Luồng 3: AI Weekly Insights: Handoff rate: {handoff_rate}%
- [ ] Luồng 3: AI Weekly Insights: Posts published: {posts_published}
- [ ] Luồng 3: AI Weekly Insights: Top post engagement: {top_post_engagement}
- [ ] Luồng 3: AI Weekly Insights: Average response time: {avg_response_time}ms
- [ ] Luồng 3: AI Weekly Insights: New leads: {new_leads}
- [ ] Luồng 3: AI Weekly Insights: Hot leads (score>80): {hot_leads}
- [ ] Luồng 3: AI Weekly Insights: Key highlights (what went well)
- [ ] Luồng 3: AI Weekly Insights: Areas of concern (what needs attention)
- [ ] Luồng 3: AI Weekly Insights: Recommendations (specific actions to take)
- [ ] Luồng 3: AI Weekly Insights: Best posting times based on engagement data

## Verification & Testing

### Automated Tests
- [ ] Write unit tests verifying core logic of each Requirement.
- [ ] Write integration tests for API endpoints.
- [ ] Verify tenant isolation by querying data across different tenant IDs.

### Manual Verification
- [ ] Deploy service to local Docker / Kubernetes cluster.
- [ ] Perform end-to-end tests using the Gateway (Kong) routing.

## Done When

- [ ] All Acceptance Criteria for Requirements are implemented and verified.
- [ ] Unit test coverage is >80%.
- [ ] Logs are formatted as structured JSON and trace context is propagated.
- [ ] Tenant isolation (RLS / metadata filtering) is strictly enforced.

### Task: Security Integration & Dynamic RBAC (MỚI)
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `analytics`.
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`.
- [ ] Triển khai HMAC Signature Verification Guard/Interceptor sử dụng `GATEWAY_SIGNING_SECRET` để xác thực request từ Gateway.
- [ ] Triển khai cơ chế so khớp quyền hạn Dynamic RBAC in-memory O(1) hỗ trợ wildcard (`*`, `analytics:*`, `analytics:{resource}:*`).
- [ ] Thực hiện tích hợp Endpoint `/api/v1/permissions/manifest` trả về danh sách tài nguyên và quyền hạn của service.
- [ ] Bổ sung các test cases kiểm tra Signature Verification và Access Control Denied.

### Task 6: Custom MCP Server Integration
- [ ] Thiết kế endpoint SSE `GET /api/v1/analytics/mcp` sử dụng `SseEmitter` trong Spring Boot.
- [ ] Thiết kế endpoint nhận thông điệp JSON-RPC `POST /api/v1/analytics/mcp/messages`.
- [ ] Xây dựng bộ phân tích và xử lý JSON-RPC cho MCP tools.
- [ ] Đăng ký công cụ `analytics_query` với các thuộc tính: `query_type`, `start_date`, `end_date`, `campaign_id`.
- [ ] Cấu hình cơ chế tiêm `tenant_id` từ header `X-Tenant-ID` trực tiếp vào câu lệnh SQL/JPA truy vấn TimescaleDB.
- [ ] Viết các bài kiểm thử đơn vị và kiểm thử tích hợp đảm bảo cô lập tenant trên TimescaleDB.

---

## Service Discovery Client Integration (MỚI)

### Task 21: Service Discovery Client Integration
- [ ] AC 21.1: Triển khai lớp `ServiceRegistryClient` tự động lấy IP nội bộ qua kết nối UDP socket ảo.
- [ ] AC 21.2: Tích hợp `ServiceRegistryClient` vào lifecycle hook khởi động và tắt của ứng dụng (Spring Boot).
- [ ] AC 21.3: Triển khai cấu trúc JSON logs cho các sự kiện đăng ký và lỗi heartbeat lên Redis.


### Task 22: Database Migration for RAG Metrics (Giai đoạn 2)
> *User Story: Là DBA, tôi muốn bảng lưu trữ metrics chất lượng RAG được tối ưu hóa cho TimescaleDB để lưu trữ và truy vấn nhanh dữ liệu chuỗi thời gian.*

**Acceptance Criteria Implementation:**
- [ ] AC 22.1: Tạo file Flyway migration `V2__add_rag_metrics_table.sql` định nghĩa cấu trúc bảng `rag_metrics`.
- [ ] AC 22.2: Thiết lập TimescaleDB hypertable cho bảng `rag_metrics` dựa trên trường `time`.
- [ ] AC 22.3: Đánh chỉ mục (index) tối ưu trên `tenant_id`, `chatbot_action`, `rag_similarity` (với filter `rag_similarity < 0.50` cho các câu hỏi bị gap).

### Task 23: RagMetrics Kafka Consumer (Giai đoạn 2)
> *User Story: Là hệ thống, tôi muốn tiêu thụ sự kiện kết thúc hội thoại từ Kafka để cập nhật cơ sở dữ liệu.*

**Acceptance Criteria Implementation:**
- [ ] AC 23.1: Xây dựng `RagMetricsConsumer` lắng nghe topic `chatbot.conversation.completed`.
- [ ] AC 23.2: Thực hiện kiểm tra tính duy nhất (idempotency check) chống trùng lặp bằng cách check sự tồn tại của `event_id` trước khi ghi DB.
- [ ] AC 23.3: Deserialize payload JSON và gọi `RagMetricsService` để lưu trữ thông tin.

### Task 24: RagMetrics & KnowledgeGap Services (Giai đoạn 2)
> *User Story: Là hệ thống, tôi muốn có các service xử lý nghiệp vụ lưu trữ và phân tích khoảng trống tri thức.*

**Acceptance Criteria Implementation:**
- [ ] AC 24.1: Xây dựng entity `RagMetric` và repository tương ứng.
- [ ] AC 24.2: Xây dựng `RagMetricsService` tính toán các thông số hiệu năng trung bình (RAG performance).
- [ ] AC 24.3: Xây dựng `KnowledgeGapService` thực hiện native query tìm kiếm top 20 câu hỏi có similarity < 0.50 hoặc chatbot_action = handoff, sắp xếp theo tần suất xuất hiện giảm dần.
- [ ] AC 24.4: Cache kết quả Knowledge Gap trên Redis trong vòng 5 phút (TTL 300s).

### Task 25: REST Controllers & Security Integration (Giai đoạn 2)
> *User Story: Là admin, tôi muốn truy vấn danh sách Knowledge Gap và RAG Performance qua REST API an toàn.*

**Acceptance Criteria Implementation:**
- [ ] AC 25.1: Tạo các endpoint `GET /api/v1/knowledge-gaps` và `GET /api/v1/rag-performance`.
- [ ] AC 25.2: Tích hợp bộ lọc HMAC Signature verification filter để xác thực request gửi từ Gateway.
- [ ] AC 25.3: Thực hiện phân quyền kiểm tra in-memory O(1) quyền `analytics:metrics:read` (hỗ trợ wildcard).

### Task 26: Unit & Integration Tests (Giai đoạn 2)
**Acceptance Criteria Implementation:**
- [ ] AC 26.1: Viết test `RagMetricsConsumerTest` kiểm thử consumer và idempotency.
- [ ] AC 26.2: Viết test `KnowledgeGapServiceTest` kiểm thử SQL logic nhóm câu hỏi và Redis cache.
- [ ] AC 26.3: Viết test `SecurityAndControllerTest` xác thực chữ ký HMAC thành công/thất bại, và chặn truy cập trái phép.

### Task 27: MCP Tool Extension (Giai đoạn 2)
- [ ] AC 27.1: Đăng ký thêm thông số hoặc cấu hình tool `analytics_query` trong McpController để hỗ trợ truy vấn các chỉ số RAG mới.

---

## Service Discovery & Health API Tasks
- [ ] Triển khai thuật toán IP Auto-detect với 3 mức độ ưu tiên (CONTAINER_IP -> OS interfaces -> UDP fake).
- [ ] Cài đặt Lifespan Registry client với cơ chế Fail-Safe khi kết nối Redis lỗi.
- [ ] Thiết lập Graceful Shutdown (hủy đăng ký khi nhận SIGTERM/SIGINT).
- [ ] Triển khai Endpoint `/health` kiểm tra trạng thái DB và Redis.
- [ ] Cấu hình định dạng log JSON chuẩn cho các sự kiện Service Discovery.
