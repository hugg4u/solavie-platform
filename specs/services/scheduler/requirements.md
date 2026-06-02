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

## Security & Access Control
- **Authentication & Authorization:** APIs của Scheduler Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `scheduler`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Scheduler Service.
- **Tenant Isolation:** Dữ liệu Scheduler **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.
