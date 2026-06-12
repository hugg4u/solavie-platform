# Task Checklist — SCHEDULER Service

## Overview
This document tracks the implementation checklist for **SCHEDULER Service** based on the system specifications.

### Technical Stack & Configuration
- **Language:** Java 21
- **Framework:** Spring Boot 3 + Quartz Scheduler
- **Database:** PostgreSQL
- **Queue:** Kafka

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/scheduler/requirements.md)
- [Design](file:///specs/solavie-system/services/scheduler/design.md)
- [Logging](file:///specs/solavie-system/services/scheduler/logging.md)
- [Business Logic](file:///specs/solavie-system/services/scheduler/business-logic.md)

---

## Tasks Checklist

### Task 1: 1: Post Scheduling
> *User Story: Là marketer, tôi muốn lên lịch đăng bài trên nhiều kênh.*

**Acceptance Criteria Implementation:**
- [ ] AC 1.1: THE Scheduler_Service SHALL cho phép schedule post trên 1 hoặc nhiều channels
- [ ] AC 1.2: THE Scheduler_Service SHALL hỗ trợ timezone per-tenant
- [ ] AC 1.3: WHEN đến thời điểm publish, THE Scheduler_Service SHALL đóng vai trò Kafka Producer phát sự kiện yêu cầu đăng bài tới Kafka topic `scheduler.post.due` (Luồng 4).
- [ ] AC 1.4: THE Scheduler_Service SHALL hỗ trợ recurring schedules (daily, weekly)
- [ ] AC 1.5: THE Scheduler_Service SHALL đóng vai trò Kafka Consumer lắng nghe các topics `content.published` và `scheduler.post.failed` (Luồng 4) để cập nhật trạng thái xuất bản bài viết tương ứng.

### Task 2: 2: Calendar View
> *User Story: Là marketer, tôi muốn xem lịch đăng bài dạng calendar.*

**Acceptance Criteria Implementation:**
- [ ] AC 2.1: THE Scheduler_Service SHALL cung cấp calendar API (month/week view)
- [ ] AC 2.2: THE Scheduler_Service SHALL hiển thị tất cả scheduled posts với status
- [ ] AC 2.3: THE Scheduler_Service SHALL hỗ trợ drag-and-drop reschedule (update time)

### Task 3: 3: Automation Flows
> *User Story: Là marketer, tôi muốn tạo automation workflows tự động.*

**Acceptance Criteria Implementation:**
- [ ] AC 3.1: THE Scheduler_Service SHALL hỗ trợ trigger types: schedule, event, condition
- [ ] AC 3.2: THE Scheduler_Service SHALL hỗ trợ actions: generate content, publish, notify
- [ ] AC 3.3: THE Scheduler_Service SHALL hỗ trợ enable/disable flows
- [ ] AC 3.4: THE Scheduler_Service SHALL log execution history per flow

### Task 4: 4: Retry & Error Handling
> *User Story: Là hệ thống, tôi cần đảm bảo posts được publish dù có lỗi tạm thời.*

**Acceptance Criteria Implementation:**
- [ ] AC 4.1: IF publish thất bại, THEN retry max 3 lần với exponential backoff
- [ ] AC 4.2: IF tất cả retries thất bại, THEN notify user qua Notification_Service
- [ ] AC 4.3: THE Scheduler_Service SHALL track retry count và last error per schedule

### Task 5: Implement Business Logic Rules
**Business Validations:**
- [ ] Tổng quan vai trò: Nhận content đã approved → lên lịch publish
- [ ] Tổng quan vai trò: Khi đến giờ → trigger Channel Connector publish
- [ ] Tổng quan vai trò: Quản lý automation workflows (trigger → action chains)
- [ ] Tổng quan vai trò: Retry logic khi publish fail
- [ ] Luồng 3: Automation Flows: schedule: Cron expression (e.g., "every Monday 9am")
- [ ] Luồng 3: Automation Flows: event: Kafka event (e.g., "new lead score > 80")
- [ ] Luồng 3: Automation Flows: condition: Data condition (e.g., "inbox unread > 50")
- [ ] Luồng 3: Automation Flows: generate_content: Call Content Service AI generate
- [ ] Luồng 3: Automation Flows: publish_post: Schedule a post
- [ ] Luồng 3: Automation Flows: send_notification: Notify team
- [ ] Luồng 3: Automation Flows: update_crm: Tag contacts
- [ ] Timezone Handling: Tất cả thời gian trong DB lưu UTC.
- [ ] Timezone Handling: Khi hiển thị cho user → convert sang tenant timezone.
- [ ] Timezone Handling: Khi user tạo schedule → convert từ tenant timezone sang UTC.

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
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `scheduler`.
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`.
- [ ] Triển khai HMAC Signature Verification Guard/Interceptor sử dụng `GATEWAY_SIGNING_SECRET` để xác thực request từ Gateway.
- [ ] Triển khai cơ chế so khớp quyền hạn Dynamic RBAC in-memory O(1) hỗ trợ wildcard (`*`, `scheduler:*`, `scheduler:{resource}:*`).
- [ ] Thực hiện tích hợp Endpoint `/api/v1/permissions/manifest` trả về danh sách tài nguyên và quyền hạn của service.
- [ ] Bổ sung các test cases kiểm tra Signature Verification và Access Control Denied.

### Task 6: Custom MCP Server Integration
- [ ] Thiết kế các MCP endpoints `GET /api/v1/scheduler/mcp` (SSE stream) và `POST /api/v1/scheduler/mcp/messages` (JSON-RPC handler) sử dụng Spring WebFlux/SseEmitter.
- [ ] Đăng ký công cụ `create_schedule` với các thuộc tính đầu vào: `post_id`, `scheduled_at`, `channel_ids`, `recurrence`.
- [ ] Tích hợp cơ chế bảo mật tiêm `tenant_id` từ request header trực tiếp vào các Quartz Job và DB models.
- [ ] Viết các test case tự động để xác nhận cô lập tenant khi đặt lịch.

---

## Service Discovery Client Integration (MỚI)

### Task 21: Service Discovery Client Integration
- [ ] AC 21.1: Triển khai lớp `ServiceRegistryClient` tự động lấy IP nội bộ qua kết nối UDP socket ảo.
- [ ] AC 21.2: Tích hợp `ServiceRegistryClient` vào lifecycle hook khởi động và tắt của ứng dụng (Spring Boot).
- [ ] AC 21.3: Triển khai cấu trúc JSON logs cho các sự kiện đăng ký và lỗi heartbeat lên Redis.


---

## Service Discovery & Health API Tasks
- [ ] Triển khai thuật toán IP Auto-detect với 3 mức độ ưu tiên (CONTAINER_IP -> OS interfaces -> UDP fake).
- [ ] Cài đặt Lifespan Registry client với cơ chế Fail-Safe khi kết nối Redis lỗi.
- [ ] Thiết lập Graceful Shutdown (hủy đăng ký khi nhận SIGTERM/SIGINT).
- [ ] Triển khai Endpoint `/health` kiểm tra trạng thái DB và Redis.
- [ ] Cấu hình định dạng log JSON chuẩn cho các sự kiện Service Discovery.
