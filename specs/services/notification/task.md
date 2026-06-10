# Task Checklist — NOTIFICATION Service

## Overview
This document tracks the implementation checklist for **NOTIFICATION Service** based on the system specifications.

### Technical Stack & Configuration
- **Language:** Node.js 20
- **Framework:** NestJS
- **Database:** PostgreSQL
- **Queue:** Kafka

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/notification/requirements.md)
- [Design](file:///specs/solavie-system/services/notification/design.md)
- [Logging](file:///specs/solavie-system/services/notification/logging.md)
- [Business Logic](file:///specs/solavie-system/services/notification/business-logic.md)

---

## Tasks Checklist

### Task 1: 1: Multi-channel Delivery
**Acceptance Criteria Implementation:**
- [ ] AC 1.1: THE Notification_Service SHALL hỗ trợ: Slack, email, in-app push
- [ ] AC 1.2: THE Notification_Service SHALL route notification theo user preferences
- [ ] AC 1.3: THE Notification_Service SHALL retry nếu delivery thất bại
- [ ] AC 1.4: Handoff notifications SHALL delivered trong < 3 giây

### Task 2: 2: User Preferences
**Acceptance Criteria Implementation:**
- [ ] AC 2.1: THE Notification_Service SHALL cho phép user cấu hình: channels, quiet hours, priority levels
- [ ] AC 2.2: THE Notification_Service SHALL respect quiet hours (không gửi ngoài giờ làm việc)
- [ ] AC 2.3: THE Notification_Service SHALL hỗ trợ priority levels: critical (always), high, normal, low

### Task 3: 3: Delivery Guarantee
**Acceptance Criteria Implementation:**
- [ ] AC 3.1: IF primary channel thất bại, THEN fallback sang channel khác
- [ ] AC 3.2: IF tất cả channels thất bại, THEN queue cho retry sau
- [ ] AC 3.3: THE Notification_Service SHALL log delivery status per notification

### Task 4: Implement Business Logic Rules
**Business Validations:**
- [ ] Tổng quan vai trò: Consume events từ Kafka (handoff, lead score, failures)
- [ ] Tổng quan vai trò: Resolve recipient + preferences
- [ ] Tổng quan vai trò: Deliver qua Slack/email/push (với fallback)
- [ ] Tổng quan vai trò: Track delivery status, respect quiet hours

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
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `notification`.
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`.
- [ ] Triển khai HMAC Signature Verification Guard/Interceptor sử dụng `GATEWAY_SIGNING_SECRET` để xác thực request từ Gateway.
- [ ] Triển khai cơ chế so khớp quyền hạn Dynamic RBAC in-memory O(1) hỗ trợ wildcard (`*`, `notification:*`, `notification:{resource}:*`).
- [ ] Thực hiện tích hợp Endpoint `/api/v1/permissions/manifest` trả về danh sách tài nguyên và quyền hạn của service.
- [ ] Bổ sung các test cases kiểm tra Signature Verification và Access Control Denied.

### Task 5: Custom MCP Server Integration
- [ ] Tích hợp `@modelcontextprotocol/sdk` vào dự án NestJS.
- [ ] Thiết kế endpoint SSE `GET /api/v1/notification/mcp` và endpoint nhận thông điệp `POST /api/v1/notification/mcp/messages`.
- [ ] Đăng ký công cụ `send_notification` nhận tham số: `user_id`, `title`, `message`, `channel`, `priority`.
- [ ] Triển khai cơ chế bảo mật tiêm `tenant_id` từ header và kiểm tra tính hợp lệ của user trước khi gửi.
- [ ] Viết unit tests và integration tests nhằm bảo vệ chống rò rỉ thông báo chéo giữa các tenant.

---

## Service Discovery Client Integration (MỚI)

### Task 21: Service Discovery Client Integration
- [ ] AC 21.1: Triển khai lớp `ServiceRegistryClient` tự động lấy IP nội bộ qua kết nối UDP socket ảo.
- [ ] AC 21.2: Tích hợp `ServiceRegistryClient` vào lifecycle hook khởi động và tắt của ứng dụng (NestJS).
- [ ] AC 21.3: Triển khai cấu trúc JSON logs cho các sự kiện đăng ký và lỗi heartbeat lên Redis.
