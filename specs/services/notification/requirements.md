# Requirements — Notification Service

## Overview
Dịch vụ thông báo đa kênh — Slack, email, in-app push. Delivery guarantee, user preferences, priority routing, quiet hours.

## Tech Stack
- **Language:** Node.js 20
- **Framework:** NestJS
- **Database:** PostgreSQL (notification_db)
- **Queue:** Kafka (consumer)

## Requirements

### Requirement 1: Multi-channel Delivery

#### Acceptance Criteria
1. THE Notification_Service SHALL hỗ trợ: Slack, email, in-app push
2. THE Notification_Service SHALL route notification theo user preferences
3. THE Notification_Service SHALL retry nếu delivery thất bại
4. Handoff notifications SHALL delivered trong < 3 giây

### Requirement 2: User Preferences

#### Acceptance Criteria
1. THE Notification_Service SHALL cho phép user cấu hình: channels, quiet hours, priority levels
2. THE Notification_Service SHALL respect quiet hours (không gửi ngoài giờ làm việc)
3. THE Notification_Service SHALL hỗ trợ priority levels: critical (always), high, normal, low

### Requirement 3: Delivery Guarantee

#### Acceptance Criteria
1. IF primary channel thất bại, THEN fallback sang channel khác
2. IF tất cả channels thất bại, THEN queue cho retry sau
3. THE Notification_Service SHALL log delivery status per notification

### Requirement 4: MCP Server Integration

**User Story:** Là hệ thống AI Core Agent, tôi muốn tự động gửi thông báo trực tiếp đến Agent hoặc người quản lý trên các kênh in-app, Slack hoặc Email thông qua giao thức MCP.

#### Acceptance Criteria
1. THE Notification_Service SHALL expose một endpoint HTTP/SSE tương thích Model Context Protocol (MCP) tại `/api/v1/notification/mcp`.
2. THE Notification_Service SHALL cung cấp công cụ `send_notification` để gửi thông báo.
3. THE Notification_Service SHALL thực thi bảo mật đa thuê (Multi-tenancy Isolation): chỉ chấp nhận kết nối mang header `X-Tenant-ID` và tự động tiêm giá trị này để bảo vệ dữ liệu trong cơ sở dữ liệu và cấm gửi thông báo chéo giữa các tenant.


### Requirement: Zero-Trust Access Control & Permission Manifest

**User Story:** Là Tenant Admin, tôi muốn xem danh sách quyền hạn mà dịch vụ `notification` hỗ trợ để thiết lập vai trò tùy chỉnh trên Dashboard và đảm bảo bảo mật Zero-Trust downstream.

#### Acceptance Criteria
1. THE NOTIFICATION_Service SHALL cung cấp API manifest tại `GET /api/v1/permissions/manifest` trả về danh sách tài nguyên (resources) và hành động (actions) được hỗ trợ.
2. THE NOTIFICATION_Service SHALL thực hiện kiểm tra chữ ký số HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET` để xác thực request được gửi trực tiếp từ API Gateway tin cậy.
3. THE NOTIFICATION_Service SHALL thực hiện kiểm tra quyền in-memory O(1) dựa trên HTTP Header `X-User-Permissions` truyền từ Gateway. Định dạng quyền của dịch vụ tuân theo cấu trúc `notification:{resource}:{action}` hỗ trợ ký tự đại diện `*` (Super Admin), `notification:*` (Toàn quyền trên service), và `notification:{resource}:*` (Toàn quyền trên tài nguyên).

## Security & Access Control
- **Authentication & Authorization:** APIs và SSE endpoints của Notification Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `notification`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Notification Service.
- **Tenant Isolation:** Dữ liệu Notification và các phiên kết nối MCP **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.

---

## Service Discovery (Self-Registration)

**User Story:** Là một developer, tôi muốn service của mình tự động đăng ký và duy trì heartbeat trên Redis Registry khi khởi động để Gateway có thể định tuyến động chính xác mà không phụ thuộc vào hạ tầng.

### Acceptance Criteria
1. THE Notification Service SHALL tự động phát hiện IP nội bộ của card mạng chính khi khởi động bằng cơ chế socket UDP ảo.
2. THE Notification Service SHALL đăng ký địa chỉ `IP:Port` của mình vào Redis Set `registry:service:notification` khi startup.
3. THE Notification Service SHALL gửi tin nhắn sống (heartbeat) định kỳ mỗi 5 giây lên Redis key `registry:service:notification:node:{ip}:{port}` với TTL là 15 giây.
4. THE Notification Service SHALL dọn dẹp (hủy đăng ký) thông tin của mình trên Redis Set `registry:service:notification` và xóa key TTL khi nhận tín hiệu shutdown (`SIGTERM`/`SIGINT`).
