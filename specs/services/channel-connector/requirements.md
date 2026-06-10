# Requirements — Channel Connector Service

## Overview
Dịch vụ kết nối các kênh Facebook, Zalo, TikTok — nhận/gửi tin nhắn qua webhooks, normalize message format, quản lý OAuth tokens.

## Tech Stack
- **Language:** Node.js 20
- **Framework:** NestJS
- **Database:** PostgreSQL (channel_connector_db)
- **Queue:** Kafka (producer)

## Requirements

### Requirement 1: Webhook Receiver

**User Story:** Là hệ thống, tôi cần nhận tin nhắn từ Facebook/Zalo/TikTok qua webhooks.

#### Acceptance Criteria
1. THE Channel_Connector SHALL expose webhook endpoints cho Facebook, Zalo, TikTok
2. THE Channel_Connector SHALL verify webhook signatures theo chuẩn của từng platform
3. WHEN webhook event nhận được, THE Channel_Connector SHALL respond 200 OK trong vòng 5 giây
4. THE Channel_Connector SHALL handle duplicate webhooks (idempotency key)
5. IF signature verification thất bại, THEN trả về 403 Forbidden

### Requirement 2: Message Normalization

**User Story:** Là messaging service, tôi cần nhận message ở format thống nhất bất kể platform nào.

#### Acceptance Criteria
1. WHEN message nhận từ bất kỳ platform, THE Channel_Connector SHALL normalize thành unified format
2. Unified format SHALL bao gồm: tenant_id, channel, sender_id, conversation_id, content, content_type, timestamp, metadata
3. THE Channel_Connector SHALL hỗ trợ content types: text, image, video, file, sticker
4. WHEN normalize thành công, THE Channel_Connector SHALL publish event lên Kafka topic `channel.message.received`

### Requirement 3: Outbound Message Delivery

**User Story:** Là messaging service, tôi cần gửi reply cho khách qua đúng platform.

#### Acceptance Criteria
1. WHEN nhận request gửi message, THE Channel_Connector SHALL convert unified format sang platform-specific format
2. THE Channel_Connector SHALL gửi message qua API của platform tương ứng
3. IF gửi thất bại, THEN retry với exponential backoff (max 3 lần)
4. THE Channel_Connector SHALL publish event `channel.message.sent` với status (delivered/failed)

### Requirement 4: OAuth Token Management

**User Story:** Là admin, tôi muốn kết nối page/OA mà không lo token hết hạn.

#### Acceptance Criteria
1. THE Channel_Connector SHALL lưu trữ OAuth tokens encrypted at rest
2. THE Channel_Connector SHALL tự động refresh tokens trước khi hết hạn
3. THE Channel_Connector SHALL hỗ trợ multiple channels per tenant
4. IF token refresh thất bại, THEN thông báo qua Notification_Service

### Requirement 5: Circuit Breaker

**User Story:** Là hệ thống, tôi cần graceful handling khi platform API down.

#### Acceptance Criteria
1. THE Channel_Connector SHALL implement circuit breaker cho mỗi external API
2. WHEN circuit open, THE Channel_Connector SHALL queue messages cho retry sau
3. THE Channel_Connector SHALL thông báo Notification_Service khi channel bị disconnect


### Requirement: Zero-Trust Access Control & Permission Manifest

**User Story:** Là Tenant Admin, tôi muốn xem danh sách quyền hạn mà dịch vụ `channel-connector` hỗ trợ để thiết lập vai trò tùy chỉnh trên Dashboard và đảm bảo bảo mật Zero-Trust downstream.

#### Acceptance Criteria
1. THE CHANNEL_CONNECTOR_Service SHALL cung cấp API manifest tại `GET /api/v1/permissions/manifest` trả về danh sách tài nguyên (resources) và hành động (actions) được hỗ trợ.
2. THE CHANNEL_CONNECTOR_Service SHALL thực hiện kiểm tra chữ ký số HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET` để xác thực request được gửi trực tiếp từ API Gateway tin cậy.
3. THE CHANNEL_CONNECTOR_Service SHALL thực hiện kiểm tra quyền in-memory O(1) dựa trên HTTP Header `X-User-Permissions` truyền từ Gateway. Định dạng quyền của dịch vụ tuân theo cấu trúc `channel-connector:{resource}:{action}` hỗ trợ ký tự đại diện `*` (Super Admin), `channel-connector:*` (Toàn quyền trên service), và `channel-connector:{resource}:*` (Toàn quyền trên tài nguyên).

## Security & Access Control
- **Authentication & Authorization:** APIs của Channel Connector Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `channel-connector`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Channel Connector Service.
- **Tenant Isolation:** Dữ liệu Channel Connector **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.

---

## Service Discovery (Self-Registration)

**User Story:** Là một developer, tôi muốn service của mình tự động đăng ký và duy trì heartbeat trên Redis Registry khi khởi động để Gateway có thể định tuyến động chính xác mà không phụ thuộc vào hạ tầng.

### Acceptance Criteria
1. THE Channel Connector Service SHALL tự động phát hiện IP nội bộ của card mạng chính khi khởi động bằng cơ chế socket UDP ảo.
2. THE Channel Connector Service SHALL đăng ký địa chỉ `IP:Port` của mình vào Redis Set `registry:service:channel-connector` khi startup.
3. THE Channel Connector Service SHALL gửi tin nhắn sống (heartbeat) định kỳ mỗi 5 giây lên Redis key `registry:service:channel-connector:node:{ip}:{port}` với TTL là 15 giây.
4. THE Channel Connector Service SHALL dọn dẹp (hủy đăng ký) thông tin của mình trên Redis Set `registry:service:channel-connector` và xóa key TTL khi nhận tín hiệu shutdown (`SIGTERM`/`SIGINT`).
