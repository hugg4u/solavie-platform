# Requirements — Auth Service (Keycloak)

## Overview
Dịch vụ xác thực và phân quyền tập trung — Keycloak. OAuth2/OIDC provider, multi-tenant realms, RBAC, JWT token management, user federation.

## Tech Stack
- **Platform:** Keycloak 24+
- **Database:** PostgreSQL (keycloak_db)
- **Mode:** Production mode (optimized)
- **Port:** 8080

## Requirements

### Requirement 1: OAuth2 / OIDC Provider

**User Story:** Là user, tôi muốn đăng nhập an toàn và nhận JWT token.

#### Acceptance Criteria
1. THE Auth_Service SHALL cung cấp OAuth2 Authorization Code flow cho Dashboard
2. THE Auth_Service SHALL phát hành JWT access token (short-lived, 15 min)
3. THE Auth_Service SHALL phát hành refresh token (long-lived, 30 days)
4. THE Auth_Service SHALL expose OIDC discovery endpoint per realm
5. JWT claims SHALL bao gồm: sub, tenant_id, roles, email, name

### Requirement 2: Multi-tenant Realms

**User Story:** Là platform admin, tôi muốn mỗi tenant có realm riêng biệt.

#### Acceptance Criteria
1. THE Auth_Service SHALL tạo 1 Keycloak realm per tenant
2. THE Auth_Service SHALL cách ly users, roles, clients giữa các realms
3. THE Auth_Service SHALL hỗ trợ tạo realm mới khi onboard tenant
4. THE Auth_Service SHALL hỗ trợ custom branding per realm (login page)

### Requirement 3: Role-Based Access Control (RBAC)

**User Story:** Là admin, tôi muốn phân quyền chi tiết cho từng user.

#### Acceptance Criteria
1. THE Auth_Service SHALL hỗ trợ roles: Admin, Manager, Agent, Viewer
2. Admin: full access tất cả features
3. Manager: manage content, campaigns, analytics, approve posts
4. Agent: inbox, reply messages, view contacts
5. Viewer: read-only access to dashboards and reports
6. THE Auth_Service SHALL include roles trong JWT token claims

### Requirement 4: User Management

**User Story:** Là admin, tôi muốn quản lý users trong tổ chức.

#### Acceptance Criteria
1. THE Auth_Service SHALL hỗ trợ CRUD users per realm
2. THE Auth_Service SHALL hỗ trợ invite user via email
3. THE Auth_Service SHALL hỗ trợ password reset flow
4. THE Auth_Service SHALL hỗ trợ disable/enable user accounts
5. THE Auth_Service SHALL áp dụng chính sách mật khẩu (độ dài tối thiểu `auth_password_min_length` từ 6-30 ký tự, độ phức tạp) được đồng bộ từ cấu hình bảo mật của Tenant Config Service
6. THE Auth_Service (Keycloak) SHALL chỉ quản lý các thông tin xác thực cốt lõi (UUID, Email, Password, Active Status), trong khi các thông tin nghiệp vụ phong phú của User (SĐT, avatar, phòng ban) SHALL được lưu trữ và quản lý độc lập tại **User Service**, liên kết 1:1 qua User UUID (`sub` claim).
7. THE Auth_Service (Keycloak) SHALL cung cấp các REST API quản trị (Keycloak Admin APIs) để cho phép **User Service** cập nhật thông tin (khóa/mở khóa tài khoản, cập nhật email/họ tên) từ Dashboard ngược lên.
8. THE Auth_Service (Keycloak) SHALL được cấu hình Custom Event Listener SPI để tự động xuất bản (publish) sự kiện thay đổi trạng thái người dùng (Verify Email, Lock Account, Update Profile) sang Redis channel/Kafka topic `auth.user.events` phục vụ đồng bộ dữ liệu xuống Backend.

### Requirement 5: Token Security

**User Story:** Là security engineer, tôi muốn tokens được quản lý an toàn.

#### Acceptance Criteria
1. THE Auth_Service SHALL sign tokens với RS256 (asymmetric keys)
2. THE Auth_Service SHALL hỗ trợ token revocation
3. THE Auth_Service SHALL giới hạn số lần đăng nhập sai (brute force protection) theo cấu hình `auth_max_login_attempts` (3-20 lần) được đồng bộ từ Tenant Config Service
4. THE Auth_Service SHALL cấp quyền truy cập Admin APIs cho các Backend Services nội bộ bằng Client Credentials Flow qua các client chuyên dụng (như `user-service-client`), áp dụng nguyên tắc Least Privilege (chỉ gán vai trò `manage-users` thuộc realm-management của realm tương ứng, không được gán admin của master realm).
5. THE Auth_Service SHALL log tất cả authentication events (login, logout, failed attempts)
6. THE Auth_Service SHALL hỗ trợ session management (list active sessions, force logout)

### Requirement 6: Advanced Security & Token Revocation (Hardened)

**User Story:** Là platform security architect, tôi muốn thắt chặt bảo mật session và hỗ trợ thu hồi token tức thời tại Gateway.

#### Acceptance Criteria
1. THE Auth_Service SHALL bắt buộc PKCE (Proof Key for Code Exchange) sử dụng mã hóa `S256` đối với client public (`dashboard`) để chống lại Authorization Code Interception.
2. THE Auth_Service SHALL áp dụng cơ chế Refresh Token Rotation (RTR) - vô hiệu hóa Refresh Token cũ ngay sau khi được sử dụng (`revokeRefreshToken = true`, `refreshTokenMaxReuse = 0`) để chống replay attack.
3. THE Auth_Service SHALL cấu hình chính sách OTP mặc định (TOTP, HmacSHA1, 6 digits, 30s period) cho mọi Tenant Realm được tạo ra.
4. THE API Gateway (Kong) SHALL thực hiện thu hồi token tức thời thông qua JTI Blacklisting bằng cách trích xuất claim `jti` từ Access Token và truy vấn Redis cache (`blacklist:jti:{jti}`) cho mọi API request.
5. THE Auth_Sync_Worker SHALL đồng bộ cấu hình bảo mật thông qua hàng đợi tin cậy cao Redis Streams (`config.updates.stream`) sử dụng Consumer Groups để bảo đảm không mất mát cấu hình khi worker gặp sự cố mạng hoặc khởi động lại.

### Requirement 7: Client Scopes (Least Privilege)

**User Story:** Là platform security architect, tôi muốn giới hạn quyền hạn truy cập của từng client Dashboard và API Gateway đối với từng dịch vụ backend cụ thể nhằm giảm thiểu rủi ro khi token bị xâm phạm.

#### Acceptance Criteria
1. THE Auth_Service SHALL định nghĩa các Client Scopes chuyên biệt tương ứng với các microservices nghiệp vụ của hệ thống, bao gồm: `campaign`, `crm`, `chatbot`, `content`, `messaging`, `analytics`, `ai-core`, và `tenant-config`.
2. THE Auth_Service SHALL cấu hình các Client Scopes nghiệp vụ này dưới dạng `optionalClientScopes` cho các OIDC clients bao gồm public client `dashboard` và confidential client `api-gateway`.
3. JWT Access Token phát hành cho client SHALL chứa claim `scope` (ví dụ: `"scope": "openid email profile campaign crm"`) khớp với danh sách scopes được yêu cầu hợp lệ trong luồng đăng nhập.



### Requirement: Zero-Trust Access Control & Permission Manifest

**User Story:** Là Tenant Admin, tôi muốn xem danh sách quyền hạn mà dịch vụ `auth` hỗ trợ để thiết lập vai trò tùy chỉnh trên Dashboard và đảm bảo bảo mật Zero-Trust downstream.

#### Acceptance Criteria
1. THE AUTH_Service SHALL cung cấp API manifest tại `GET /api/v1/permissions/manifest` trả về danh sách tài nguyên (resources) và hành động (actions) được hỗ trợ.
2. THE AUTH_Service SHALL thực hiện kiểm tra chữ ký số HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET` để xác thực request được gửi trực tiếp từ API Gateway tin cậy.
3. THE AUTH_Service SHALL thực hiện kiểm tra quyền in-memory O(1) dựa trên HTTP Header `X-User-Permissions` truyền từ Gateway. Định dạng quyền của dịch vụ tuân theo cấu trúc `auth:{resource}:{action}` hỗ trợ ký tự đại diện `*` (Super Admin), `auth:*` (Toàn quyền trên service), và `auth:{resource}:*` (Toàn quyền trên tài nguyên).
