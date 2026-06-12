# Requirements — Messaging Service

## Overview
Dịch vụ quản lý hộp thư hợp nhất (unified inbox), conversation lifecycle, message routing (bot/human), realtime delivery qua WebSocket.

## Tech Stack
- **Language:** Node.js 20
- **Framework:** NestJS
- **Database:** PostgreSQL (messaging_db)
- **Queue:** Kafka (consumer + producer)
- **Realtime:** WebSocket + Redis Pub/Sub
- **gRPC:** Client (gọi Chatbot Service)

## Requirements

### Requirement 1: Unified Inbox

**User Story:** Là agent, tôi muốn xem tất cả tin nhắn từ mọi kênh trong 1 inbox.

#### Acceptance Criteria
1. THE Messaging_Service SHALL tổng hợp messages từ tất cả channels vào unified inbox per-tenant
2. THE Messaging_Service SHALL lưu toàn bộ conversation history với metadata
3. THE Messaging_Service SHALL hỗ trợ pagination, filtering (by channel, status, assigned agent)
4. THE Messaging_Service SHALL hiển thị unread count per conversation

### Requirement 2: Message Routing

**User Story:** Là hệ thống, tôi cần route message đến bot hoặc agent tùy conversation mode.

#### Acceptance Criteria
1. WHEN message mới đến và conversation mode = "auto", THE Messaging_Service SHALL gọi Chatbot_Service qua gRPC
2. WHEN message mới đến và conversation mode = "manual", THE Messaging_Service SHALL push realtime cho assigned agent
3. WHEN Chatbot trả về action = HANDOFF, THE Messaging_Service SHALL chuyển conversation sang mode "manual"
4. THE Messaging_Service SHALL cho phép agent chuyển conversation về mode "auto"

### Requirement 3: Realtime Delivery

**User Story:** Là agent, tôi muốn thấy tin nhắn mới ngay lập tức.

#### Acceptance Criteria
1. THE Messaging_Service SHALL push messages qua WebSocket khi có tin mới
2. THE Messaging_Service SHALL dùng Redis Pub/Sub để broadcast across instances
3. WHEN agent gửi reply, THE Messaging_Service SHALL forward đến Channel_Connector
4. THE Messaging_Service SHALL hỗ trợ typing indicators

### Requirement 4: Conversation Management

**User Story:** Là agent, tôi muốn quản lý conversations (assign, close, reopen).

#### Acceptance Criteria
1. THE Messaging_Service SHALL hỗ trợ assign conversation cho agent
2. THE Messaging_Service SHALL hỗ trợ conversation status: open, pending, closed
3. THE Messaging_Service SHALL auto-close conversations sau 24h không hoạt động
4. WHEN conversation được assign, THE Messaging_Service SHALL notify agent qua Notification_Service

### Requirement 5: MCP Server Integration

**User Story:** Là hệ thống AI Core Agent, tôi muốn gọi các công cụ nghiệp vụ của Messaging Service trực tiếp thông qua giao thức MCP để gửi tin nhắn hoặc chuyển hướng hội thoại tự động.

#### Acceptance Criteria
1. THE Messaging_Service SHALL expose một endpoint HTTP/SSE tương thích giao thức Model Context Protocol (MCP) tại `/api/v1/messaging/mcp`.
2. THE Messaging_Service SHALL cung cấp công cụ `send_message` để gửi tin nhắn của bot hoặc hệ thống đến cuộc hội thoại cụ thể.
3. THE Messaging_Service SHALL cung cấp công cụ `handoff_to_agent` để chuyển hướng cuộc hội thoại sang chế độ thủ công (manual) và gán cho Agent phù hợp.
4. THE Messaging_Service SHALL thực thi ràng buộc bảo mật đa thuê (Multi-tenancy Isolation): chỉ chấp nhận kết nối mang header `X-Tenant-ID` hợp lệ và tự động áp dụng `tenant_id` này cho mọi thao tác truy vấn cơ sở dữ liệu và gọi công cụ.


### Requirement: Zero-Trust Access Control & Permission Manifest

**User Story:** Là Tenant Admin, tôi muốn xem danh sách quyền hạn mà dịch vụ `messaging` hỗ trợ để thiết lập vai trò tùy chỉnh trên Dashboard và đảm bảo bảo mật Zero-Trust downstream.

#### Acceptance Criteria
1. THE MESSAGING_Service SHALL cung cấp API manifest tại `GET /api/v1/permissions/manifest` trả về danh sách tài nguyên (resources) và hành động (actions) được hỗ trợ.
2. THE MESSAGING_Service SHALL thực hiện kiểm tra chữ ký số HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET` để xác thực request được gửi trực tiếp từ API Gateway tin cậy.
3. THE MESSAGING_Service SHALL thực hiện kiểm tra quyền in-memory O(1) dựa trên HTTP Header `X-User-Permissions` truyền từ Gateway. Định dạng quyền của dịch vụ tuân theo cấu trúc `messaging:{resource}:{action}` hỗ trợ ký tự đại diện `*` (Super Admin), `messaging:*` (Toàn quyền trên service), và `messaging:{resource}:*` (Toàn quyền trên tài nguyên).

## Security & Access Control
- **Authentication & Authorization:** APIs và SSE endpoints của Messaging Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `messaging`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Messaging Service.
- **Tenant Isolation:** Dữ liệu Messaging và các phiên kết nối MCP **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.

---

## Service Discovery (Self-Registration)

**User Story:** Là một developer, tôi muốn service của mình tự động đăng ký và duy trì heartbeat trên Redis Registry khi khởi động để Gateway có thể định tuyến động chính xác mà không phụ thuộc vào hạ tầng.

### Acceptance Criteria
1. THE Messaging Service SHALL tự động phát hiện IP nội bộ của card mạng chính khi khởi động bằng cơ chế socket UDP ảo.
2. THE Messaging Service SHALL đăng ký địa chỉ `IP:Port` của mình vào Redis Set `registry:service:messaging` khi startup.
3. THE Messaging Service SHALL gửi tin nhắn sống (heartbeat) định kỳ mỗi 5 giây lên Redis key `registry:service:messaging:node:{ip}:{port}` với TTL là 15 giây.
4. THE Messaging Service SHALL dọn dẹp (hủy đăng ký) thông tin của mình trên Redis Set `registry:service:messaging` và xóa key TTL khi nhận tín hiệu shutdown (`SIGTERM`/`SIGINT`).
