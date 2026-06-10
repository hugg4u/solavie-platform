# Requirements — Scheduler Service

## Overview
Dịch vụ lên lịch đăng bài và automation flows — calendar management, timezone-aware scheduling, trigger-based workflows, retry logic.

## Tech Stack
- **Language:** Java 21
- **Framework:** Spring Boot 3 + Quartz Scheduler
- **Database:** PostgreSQL (scheduler_db)
- **Queue:** Kafka (producer + consumer)

## Requirements

### Requirement 1: Post Scheduling

**User Story:** Là marketer, tôi muốn lên lịch đăng bài trên nhiều kênh.

#### Acceptance Criteria
1. THE Scheduler_Service SHALL cho phép schedule post trên 1 hoặc nhiều channels
2. THE Scheduler_Service SHALL hỗ trợ timezone per-tenant
3. WHEN đến thời điểm publish, THE Scheduler_Service SHALL trigger publish event qua Kafka
4. THE Scheduler_Service SHALL hỗ trợ recurring schedules (daily, weekly)

### Requirement 2: Calendar View

**User Story:** Là marketer, tôi muốn xem lịch đăng bài dạng calendar.

#### Acceptance Criteria
1. THE Scheduler_Service SHALL cung cấp calendar API (month/week view)
2. THE Scheduler_Service SHALL hiển thị tất cả scheduled posts với status
3. THE Scheduler_Service SHALL hỗ trợ drag-and-drop reschedule (update time)

### Requirement 3: Automation Flows

**User Story:** Là marketer, tôi muốn tạo automation workflows tự động.

#### Acceptance Criteria
1. THE Scheduler_Service SHALL hỗ trợ trigger types: schedule, event, condition
2. THE Scheduler_Service SHALL hỗ trợ actions: generate content, publish, notify
3. THE Scheduler_Service SHALL hỗ trợ enable/disable flows
4. THE Scheduler_Service SHALL log execution history per flow

### Requirement 4: Retry & Error Handling

**User Story:** Là hệ thống, tôi cần đảm bảo posts được publish dù có lỗi tạm thời.

#### Acceptance Criteria
1. IF publish thất bại, THEN retry max 3 lần với exponential backoff
2. IF tất cả retries thất bại, THEN notify user qua Notification_Service
3. THE Scheduler_Service SHALL track retry count và last error per schedule

### Requirement 5: MCP Server Integration

**User Story:** Là hệ thống AI Core Agent, tôi muốn lên lịch đăng bài hoặc đặt lịch các chiến dịch tự động thông qua giao thức MCP.

#### Acceptance Criteria
1. THE Scheduler_Service SHALL expose một endpoint HTTP/SSE tương thích Model Context Protocol (MCP) tại `/api/v1/scheduler/mcp`.
2. THE Scheduler_Service SHALL cung cấp công cụ `create_schedule` để tạo lịch trình đăng bài hoặc tự động hóa mới.
3. THE Scheduler_Service SHALL kiểm chứng bảo mật đa thuê (Multi-tenancy Isolation): chỉ chấp nhận kết nối chứa header `X-Tenant-ID` hợp lệ và tự động tiêm giá trị này để bảo vệ dữ liệu trong cơ sở dữ liệu Quartz và PostgreSQL.


### Requirement: Zero-Trust Access Control & Permission Manifest

**User Story:** Là Tenant Admin, tôi muốn xem danh sách quyền hạn mà dịch vụ `scheduler` hỗ trợ để thiết lập vai trò tùy chỉnh trên Dashboard và đảm bảo bảo mật Zero-Trust downstream.

#### Acceptance Criteria
1. THE SCHEDULER_Service SHALL cung cấp API manifest tại `GET /api/v1/permissions/manifest` trả về danh sách tài nguyên (resources) và hành động (actions) được hỗ trợ.
2. THE SCHEDULER_Service SHALL thực hiện kiểm tra chữ ký số HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET` để xác thực request được gửi trực tiếp từ API Gateway tin cậy.
3. THE SCHEDULER_Service SHALL thực hiện kiểm tra quyền in-memory O(1) dựa trên HTTP Header `X-User-Permissions` truyền từ Gateway. Định dạng quyền của dịch vụ tuân theo cấu trúc `scheduler:{resource}:{action}` hỗ trợ ký tự đại diện `*` (Super Admin), `scheduler:*` (Toàn quyền trên service), và `scheduler:{resource}:*` (Toàn quyền trên tài nguyên).

## Security & Access Control
- **Authentication & Authorization:** APIs và SSE endpoints của Scheduler Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `scheduler`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Scheduler Service.
- **Tenant Isolation:** Dữ liệu Scheduler và các phiên kết nối MCP **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.

---

## Service Discovery (Self-Registration)

**User Story:** Là một developer, tôi muốn service của mình tự động đăng ký và duy trì heartbeat trên Redis Registry khi khởi động để Gateway có thể định tuyến động chính xác mà không phụ thuộc vào hạ tầng.

### Acceptance Criteria
1. THE Scheduler Service SHALL tự động phát hiện IP nội bộ của card mạng chính khi khởi động bằng cơ chế socket UDP ảo.
2. THE Scheduler Service SHALL đăng ký địa chỉ `IP:Port` của mình vào Redis Set `registry:service:scheduler` khi startup.
3. THE Scheduler Service SHALL gửi tin nhắn sống (heartbeat) định kỳ mỗi 5 giây lên Redis key `registry:service:scheduler:node:{ip}:{port}` với TTL là 15 giây.
4. THE Scheduler Service SHALL dọn dẹp (hủy đăng ký) thông tin của mình trên Redis Set `registry:service:scheduler` và xóa key TTL khi nhận tín hiệu shutdown (`SIGTERM`/`SIGINT`).
