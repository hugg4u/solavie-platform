# Task Checklist — MESSAGING Service

## Overview
This document tracks the implementation checklist for **MESSAGING Service** based on the system specifications.

### Technical Stack & Configuration
- **Language:** Node.js 20
- **Framework:** NestJS
- **Database:** PostgreSQL
- **Queue:** Kafka
- **Realtime:** WebSocket + Redis Pub/Sub
- **gRPC:** Client

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/messaging/requirements.md)
- [Design](file:///specs/solavie-system/services/messaging/design.md)
- [Logging](file:///specs/solavie-system/services/messaging/logging.md)
- [Business Logic](file:///specs/solavie-system/services/messaging/business-logic.md)

---

## Tasks Checklist

### Task 1: 1: Unified Inbox
> *User Story: Là agent, tôi muốn xem tất cả tin nhắn từ mọi kênh trong 1 inbox.*

**Acceptance Criteria Implementation:**
- [ ] AC 1.1: THE Messaging_Service SHALL tổng hợp messages từ tất cả channels vào unified inbox per-tenant
- [ ] AC 1.2: THE Messaging_Service SHALL lưu toàn bộ conversation history với metadata
- [ ] AC 1.3: THE Messaging_Service SHALL hỗ trợ pagination, filtering (by channel, status, assigned agent)
- [ ] AC 1.4: THE Messaging_Service SHALL hiển thị unread count per conversation

### Task 2: 2: Message Routing
> *User Story: Là hệ thống, tôi cần route message đến bot hoặc agent tùy conversation mode.*

**Acceptance Criteria Implementation:**
- [ ] AC 2.1: WHEN message mới đến và conversation mode = "auto", THE Messaging_Service SHALL gọi Chatbot_Service qua gRPC
- [ ] AC 2.2: WHEN message mới đến và conversation mode = "manual", THE Messaging_Service SHALL push realtime cho assigned agent
- [ ] AC 2.3: WHEN Chatbot trả về action = HANDOFF, THE Messaging_Service SHALL chuyển conversation sang mode "manual"
- [ ] AC 2.4: THE Messaging_Service SHALL cho phép agent chuyển conversation về mode "auto"

### Task 3: 3: Realtime Delivery
> *User Story: Là agent, tôi muốn thấy tin nhắn mới ngay lập tức.*

**Acceptance Criteria Implementation:**
- [ ] AC 3.1: THE Messaging_Service SHALL push messages qua WebSocket khi có tin mới
- [ ] AC 3.2: THE Messaging_Service SHALL dùng Redis Pub/Sub để broadcast across instances
- [ ] AC 3.3: WHEN agent gửi reply, THE Messaging_Service SHALL forward đến Channel_Connector
- [ ] AC 3.4: THE Messaging_Service SHALL hỗ trợ typing indicators

### Task 4: 4: Conversation Management
> *User Story: Là agent, tôi muốn quản lý conversations (assign, close, reopen).*

**Acceptance Criteria Implementation:**
- [ ] AC 4.1: THE Messaging_Service SHALL hỗ trợ assign conversation cho agent
- [ ] AC 4.2: THE Messaging_Service SHALL hỗ trợ conversation status: open, pending, closed
- [ ] AC 4.3: THE Messaging_Service SHALL auto-close conversations sau 24h không hoạt động
- [ ] AC 4.4: WHEN conversation được assign, THE Messaging_Service SHALL notify agent qua Notification_Service

### Task 5: Implement Business Logic Rules
**Business Validations:**
- [ ] Tổng quan vai trò: Consume messages từ Kafka (đã normalize bởi Channel Connector)
- [ ] Tổng quan vai trò: Lưu vào DB, gắn vào conversation đúng
- [ ] Tổng quan vai trò: Route: gọi Chatbot (auto) hoặc push cho Agent (manual)
- [ ] Tổng quan vai trò: Nhận reply từ Agent → forward cho Channel Connector
- [ ] Tổng quan vai trò: Push realtime qua WebSocket

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
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `messaging`.
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`.
- [ ] Triển khai HMAC Signature Verification Guard/Interceptor sử dụng `GATEWAY_SIGNING_SECRET` để xác thực request từ Gateway.
- [ ] Triển khai cơ chế so khớp quyền hạn Dynamic RBAC in-memory O(1) hỗ trợ wildcard (`*`, `messaging:*`, `messaging:{resource}:*`).
- [ ] Thực hiện tích hợp Endpoint `/api/v1/permissions/manifest` trả về danh sách tài nguyên và quyền hạn của service.
- [ ] Bổ sung các test cases kiểm tra Signature Verification và Access Control Denied.

### Task 6: Custom MCP Server Integration
- [ ] Khởi tạo thư viện `@modelcontextprotocol/sdk` và tích hợp vào dự án NestJS.
- [ ] Định nghĩa Controller cho các MCP endpoints: `GET /api/v1/messaging/mcp` (SSE stream) và `POST /api/v1/messaging/mcp/messages` (JSON-RPC handler).
- [ ] Đăng ký công cụ `send_message` với schema validation (Zod) cho `conversation_id`, `content`, `content_type`.
- [ ] Đăng ký công cụ `handoff_to_agent` với schema validation (Zod) cho `conversation_id`, `reason`.
- [ ] Thiết lập logic tiêm `tenant_id` từ header `X-Tenant-ID` vào tham số của công cụ và áp dụng cơ chế cô lập trong cơ sở dữ liệu.
- [ ] Viết unit tests và integration tests kiểm thử tính chính xác của các công cụ MCP và kiểm soát truy cập chéo giữa các tenant.

