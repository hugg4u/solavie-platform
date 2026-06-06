# Requirements — Campaign Service

## Overview
Dịch vụ quản lý chiến dịch marketing — multi-post campaigns, A/B testing, statistical significance detection, lifecycle management, performance tracking.

## Tech Stack
- **Language:** Java 21
- **Framework:** Spring Boot 3
- **Database:** PostgreSQL (campaign_db)
- **Queue:** Kafka (producer)

## Requirements

### Requirement 1: Campaign Management

#### Acceptance Criteria
1. THE Campaign_Service SHALL cho phép tạo campaign gồm nhiều posts trên nhiều channels
2. THE Campaign_Service SHALL hỗ trợ lifecycle: Draft → Active → Paused → Completed
3. THE Campaign_Service SHALL track performance metrics per-campaign
4. THE Campaign_Service SHALL hỗ trợ campaign goals (reach, engagement, conversion targets)

### Requirement 2: A/B Testing

#### Acceptance Criteria
1. THE Campaign_Service SHALL hỗ trợ A/B testing với >= 2 variants
2. THE Campaign_Service SHALL distribute traffic evenly across variants
3. WHEN statistical significance đạt (p < 0.05), THE Campaign_Service SHALL auto-select winner
4. THE Campaign_Service SHALL report variant performance comparison

### Requirement 3: Performance Tracking

#### Acceptance Criteria
1. THE Campaign_Service SHALL track: reach, engagement rate, click-through, conversion
2. THE Campaign_Service SHALL generate performance summary khi campaign kết thúc
3. THE Campaign_Service SHALL compare performance vs campaign goals


### Requirement: Zero-Trust Access Control & Permission Manifest

**User Story:** Là Tenant Admin, tôi muốn xem danh sách quyền hạn mà dịch vụ `campaign` hỗ trợ để thiết lập vai trò tùy chỉnh trên Dashboard và đảm bảo bảo mật Zero-Trust downstream.

#### Acceptance Criteria
1. THE CAMPAIGN_Service SHALL cung cấp API manifest tại `GET /api/v1/permissions/manifest` trả về danh sách tài nguyên (resources) và hành động (actions) được hỗ trợ.
2. THE CAMPAIGN_Service SHALL thực hiện kiểm tra chữ ký số HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET` để xác thực request được gửi trực tiếp từ API Gateway tin cậy.
3. THE CAMPAIGN_Service SHALL thực hiện kiểm tra quyền in-memory O(1) dựa trên HTTP Header `X-User-Permissions` truyền từ Gateway. Định dạng quyền của dịch vụ tuân theo cấu trúc `campaign:{resource}:{action}` hỗ trợ ký tự đại diện `*` (Super Admin), `campaign:*` (Toàn quyền trên service), và `campaign:{resource}:*` (Toàn quyền trên tài nguyên).

## Security & Access Control
- **Authentication & Authorization:** APIs của Campaign Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `campaign`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Campaign Service.
- **Tenant Isolation:** Dữ liệu Campaign **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.

