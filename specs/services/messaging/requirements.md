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

## Security & Access Control
- **Authentication & Authorization:** APIs của Messaging Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `messaging`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Messaging Service.
- **Tenant Isolation:** Dữ liệu Messaging **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.
