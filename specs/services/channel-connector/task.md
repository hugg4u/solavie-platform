# Task Checklist — CHANNEL-CONNECTOR Service

## Overview
This document tracks the implementation checklist for **CHANNEL-CONNECTOR Service** based on the system specifications.

### Technical Stack & Configuration
- **Language:** Node.js 20
- **Framework:** NestJS
- **Database:** PostgreSQL
- **Queue:** Kafka

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/channel-connector/requirements.md)
- [Design](file:///specs/solavie-system/services/channel-connector/design.md)
- [Logging](file:///specs/solavie-system/services/channel-connector/logging.md)
- [Business Logic](file:///specs/solavie-system/services/channel-connector/business-logic.md)

---

## Tasks Checklist

### Task 1: 1: Webhook Receiver
> *User Story: Là hệ thống, tôi cần nhận tin nhắn từ Facebook/Zalo/TikTok qua webhooks.*

**Acceptance Criteria Implementation:**
- [ ] AC 1.1: THE Channel_Connector SHALL expose webhook endpoints cho Facebook, Zalo, TikTok
- [ ] AC 1.2: THE Channel_Connector SHALL verify webhook signatures theo chuẩn của từng platform
- [ ] AC 1.3: WHEN webhook event nhận được, THE Channel_Connector SHALL respond 200 OK trong vòng 5 giây
- [ ] AC 1.4: THE Channel_Connector SHALL handle duplicate webhooks (idempotency key)
- [ ] AC 1.5: IF signature verification thất bại, THEN trả về 403 Forbidden

### Task 2: 2: Message Normalization
> *User Story: Là messaging service, tôi cần nhận message ở format thống nhất bất kể platform nào.*

**Acceptance Criteria Implementation:**
- [ ] AC 2.1: WHEN message nhận từ bất kỳ platform, THE Channel_Connector SHALL normalize thành unified format
- [ ] AC 2.2: Unified format SHALL bao gồm: tenant_id, channel, sender_id, conversation_id, content, content_type, timestamp, metadata
- [ ] AC 2.3: THE Channel_Connector SHALL hỗ trợ content types: text, image, video, file, sticker
- [ ] AC 2.4: WHEN normalize thành công, THE Channel_Connector SHALL publish event lên Kafka topic `channel.message.received`

### Task 3: 3: Outbound Message Delivery
> *User Story: Là messaging service, tôi cần gửi reply cho khách qua đúng platform.*

**Acceptance Criteria Implementation:**
- [ ] AC 3.1: WHEN nhận request gửi message, THE Channel_Connector SHALL convert unified format sang platform-specific format
- [ ] AC 3.2: THE Channel_Connector SHALL gửi message qua API của platform tương ứng
- [ ] AC 3.3: IF gửi thất bại, THEN retry với exponential backoff (max 3 lần)
- [ ] AC 3.4: THE Channel_Connector SHALL publish event `channel.message.sent` với status (delivered/failed)

### Task 4: 4: OAuth Token Management
> *User Story: Là admin, tôi muốn kết nối page/OA mà không lo token hết hạn.*

**Acceptance Criteria Implementation:**
- [ ] AC 4.1: THE Channel_Connector SHALL lưu trữ OAuth tokens encrypted at rest
- [ ] AC 4.2: THE Channel_Connector SHALL tự động refresh tokens trước khi hết hạn
- [ ] AC 4.3: THE Channel_Connector SHALL hỗ trợ multiple channels per tenant
- [ ] AC 4.4: IF token refresh thất bại, THEN thông báo qua Notification_Service

### Task 5: 5: Circuit Breaker
> *User Story: Là hệ thống, tôi cần graceful handling khi platform API down.*

**Acceptance Criteria Implementation:**
- [ ] AC 5.1: THE Channel_Connector SHALL implement circuit breaker cho mỗi external API
- [ ] AC 5.2: WHEN circuit open, THE Channel_Connector SHALL queue messages cho retry sau
- [ ] AC 5.3: THE Channel_Connector SHALL thông báo Notification_Service khi channel bị disconnect

### Task 6: Implement Business Logic Rules
**Business Validations:**
- [ ] Tổng quan vai trò: **Nhận** tin nhắn/comment từ platforms (webhook)
- [ ] Tổng quan vai trò: **Gửi** tin nhắn/bài viết ra platforms (outbound)
- [ ] Tổng quan vai trò: **Quản lý** OAuth tokens per channel per tenant

### Task 7: Implement Structured Logging & Auditing
**Logging Requirements:**
- [ ] Sensitive Data Rules: NEVER log access_tokens hoặc refresh_tokens
- [ ] Sensitive Data Rules: Log sender_id nhưng KHÔNG log message content ở INFO
- [ ] Sensitive Data Rules: Log platform_message_id cho tracing

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
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `channel-connector`.
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`.
- [ ] Triển khai HMAC Signature Verification Guard/Interceptor sử dụng `GATEWAY_SIGNING_SECRET` để xác thực request từ Gateway.
- [ ] Triển khai cơ chế so khớp quyền hạn Dynamic RBAC in-memory O(1) hỗ trợ wildcard (`*`, `channel-connector:*`, `channel-connector:{resource}:*`).
- [ ] Thực hiện tích hợp Endpoint `/api/v1/permissions/manifest` trả về danh sách tài nguyên và quyền hạn của service.
- [ ] Bổ sung các test cases kiểm tra Signature Verification và Access Control Denied.

---

## Service Discovery Client Integration (MỚI)

### Task 21: Service Discovery Client Integration
- [ ] AC 21.1: Triển khai lớp `ServiceRegistryClient` tự động lấy IP nội bộ qua kết nối UDP socket ảo.
- [ ] AC 21.2: Tích hợp `ServiceRegistryClient` vào lifecycle hook khởi động và tắt của ứng dụng (NestJS).
- [ ] AC 21.3: Triển khai cấu trúc JSON logs cho các sự kiện đăng ký và lỗi heartbeat lên Redis.
