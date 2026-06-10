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
