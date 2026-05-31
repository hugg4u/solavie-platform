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
