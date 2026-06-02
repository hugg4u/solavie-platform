# Task Checklist — AUTH Service

## Overview
This document tracks the implementation checklist for **AUTH Service** based on the system specifications.

### Technical Stack & Configuration
- **Platform:** Keycloak 24+
- **Database:** PostgreSQL
- **Mode:** Production mode
- **Port:** 8080

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/auth/requirements.md)
- [Design](file:///specs/solavie-system/services/auth/design.md)
- [Logging](file:///specs/solavie-system/services/auth/logging.md)

---

## Tasks Checklist

### Task 1: 1: OAuth2 / OIDC Provider
> *User Story: Là user, tôi muốn đăng nhập an toàn và nhận JWT token.*

**Acceptance Criteria Implementation:**
- [x] AC 1.1: THE Auth_Service SHALL cung cấp OAuth2 Authorization Code flow cho Dashboard
- [x] AC 1.2: THE Auth_Service SHALL phát hành JWT access token (short-lived, 15 min)
- [x] AC 1.3: THE Auth_Service SHALL phát hành refresh token (long-lived, 30 days)
- [x] AC 1.4: THE Auth_Service SHALL expose OIDC discovery endpoint per realm
- [x] AC 1.5: JWT claims SHALL bao gồm: sub, tenant_id, roles, email, name

### Task 2: 2: Multi-tenant Realms
> *User Story: Là platform admin, tôi muốn mỗi tenant có realm riêng biệt.*

**Acceptance Criteria Implementation:**
- [x] AC 2.1: THE Auth_Service SHALL tạo 1 Keycloak realm per tenant
- [x] AC 2.2: THE Auth_Service SHALL cách ly users, roles, clients giữa các realms
- [x] AC 2.3: THE Auth_Service SHALL hỗ trợ tạo realm mới khi onboard tenant
- [x] AC 2.4: THE Auth_Service SHALL hỗ trợ custom branding per realm (login page)

### Task 3: 3: Role-Based Access Control (RBAC)
> *User Story: Là admin, tôi muốn phân quyền chi tiết cho từng user.*

**Acceptance Criteria Implementation:**
- [x] AC 3.1: THE Auth_Service SHALL hỗ trợ roles: Admin, Manager, Agent, Viewer
  - Roles được tạo tự động trong `provision_realm.py` khi onboard tenant mới
- [x] AC 3.2: Admin: full access tất cả features
- [x] AC 3.3: Manager: manage content, campaigns, analytics, approve posts
- [x] AC 3.4: Agent: inbox, reply messages, view contacts
- [x] AC 3.5: Viewer: read-only access to dashboards and reports
- [x] AC 3.6: THE Auth_Service SHALL include roles trong JWT token claims
  - Mapper `roles-mapper` trong Keycloak client config tự động inject roles vào JWT

### Task 4: 4: User Management
> *User Story: Là admin, tôi muốn quản lý users trong tổ chức.*

**Acceptance Criteria Implementation:**
- [x] AC 4.1: THE Auth_Service SHALL hỗ trợ CRUD users per realm
- [x] AC 4.2: THE Auth_Service SHALL hỗ trợ invite user via email
- [x] AC 4.3: THE Auth_Service SHALL hỗ trợ password reset flow
- [x] AC 4.4: THE Auth_Service SHALL hỗ trợ disable/enable user accounts
- [x] AC 4.5: THE Auth_Service SHALL áp dụng chính sách mật khẩu (`auth_password_min_length`) được đồng bộ từ Tenant Config Service
    - [x] AC 4.5.1: Xây dựng sync subscriber/worker lắng nghe event `config.updates` từ Tenant Config Service
- [x] AC 4.6: Phân tách dữ liệu hồ sơ User nghiệp vụ (Hybrid User Profiles) sang User Service và liên kết qua User UUID (`sub` claim)
- [x] AC 4.7: Triển khai cấu hình Client Credentials để cấp quyền cho User Service gọi đến Keycloak Admin API
    - **Implemented:** Thêm `user-service-client` (confidential, `serviceAccountsEnabled: true`, `standardFlowEnabled: false`) vào `templates/tenant-realm-template.json`
    - **Implemented:** Hàm `provision_user_service_client()` trong `provision_realm.py` tự động gán role `manage-users` từ `realm-management` cho service account — áp dụng nguyên tắc **Least Privilege**
    - **Arg mới:** `--user-service-secret` cho `provision_realm.py` (auto-generate nếu bỏ trống)
    - **Output:** `provision_realm.py` trả về `user-service-client` secret trong `PROVISION_OUTPUT_START` block
- [x] AC 4.8: Phát triển & Tích hợp Custom Event Listener SPI trên Keycloak để xuất bản sự kiện sang Redis/Kafka channel `auth.user.events`
      - **Implemented:** `services/auth/scripts/sync_worker.py` — subscribed thêm Redis channel `auth.user.events`
      - Hàm `forward_user_event_to_service()` map Keycloak event types → User Service event schema:
        - `VERIFY_EMAIL` / `REGISTER` → `user.verified`
        - `UPDATE_EMAIL` → `user.email_updated`
        - `DISABLE_USER` → `user.disabled`
        - `DELETE_USER` → `user.deleted`
      - Ký HMAC-SHA256 payload với `WEBHOOK_SECRET` trước khi gọi User Service webhook `POST /api/v1/users/events`
      - Header `X-Webhook-Signature` để User Service xác thực nguồn gốc event
    - [x] Call Keycloak Admin API để đồng bộ `passwordPolicy` (minLength, upperCase, digit, specialChars)
      - **Implemented:** `update_realm_security()` trong sync_worker.py — PUT `/admin/realms/{realm}`
    - [x] Viết integration test kiểm thử việc thay đổi password policy động áp dụng thành công
      - **Implemented:** `test_dynamic_password_policy_sync()` trong `test_auth.py`
      - Test set `length(12)` → xác minh user với password ngắn bị từ chối (400)

### Task 5: 5: Token Security
> *User Story: Là security engineer, tôi muốn tokens được quản lý an toàn.*

**Acceptance Criteria Implementation:**
- [x] AC 5.1: THE Auth_Service SHALL sign tokens với RS256 (asymmetric keys)
  - **Verified:** `test_token_signed_with_rs256()` — kiểm tra JWT header `alg: RS256`
- [x] AC 5.2: THE Auth_Service SHALL hỗ trợ token revocation
  - **Verified:** `test_token_revocation_logout()` — kiểm tra userinfo 401 sau logout
- [x] AC 5.3: THE Auth_Service SHALL giới hạn số lần đăng nhập sai theo `auth_max_login_attempts`
    - [x] AC 5.3.1: Đồng bộ cấu hình brute-force qua event `config.updates`
      - **Implemented:** `sync_worker.py` — sync `failureFactor` từ Redis config
    - [x] Call Keycloak Admin API để cập nhật `failureFactor` tương ứng với `auth_max_login_attempts`
      - **Implemented:** `update_realm_security()` — payload includes `bruteForceProtected: True, failureFactor`
    - [x] Viết integration test giả lập đăng nhập sai liên tiếp để kiểm chứng tài khoản bị khóa
      - **Implemented:** `test_brute_force_protection_sync()` — set failureFactor=3, 4 failed logins → 401/400
- [x] AC 5.4: THE Auth_Service SHALL log tất cả authentication events (login, logout, failed attempts)
  - Keycloak built-in event logging được enable trong realm config
- [x] AC 5.5: THE Auth_Service SHALL hỗ trợ session management (list active sessions, force logout)
  - Keycloak Admin API `/admin/realms/{realm}/users/{id}/sessions` hỗ trợ đầy đủ

### Task 6: Advanced Security Hardening (MỚI)
> *User Story: Là platform security architect, tôi muốn thắt chặt bảo mật session và hỗ trợ thu hồi token tức thời.*

**Acceptance Criteria Implementation:**
- [x] AC 6.1: THE Auth_Service SHALL bắt buộc PKCE cho client dashboard
  - **Implemented:** Thuộc tính `pkce.code.challenge.method` được cấu hình là `"S256"` trong `tenant-realm-template.json`
- [x] AC 6.2: THE Auth_Service SHALL áp dụng Refresh Token Rotation (RTR)
  - **Implemented:** Cấu hình `revokeRefreshToken: true` và `refreshTokenMaxReuse: 0` trong `tenant-realm-template.json`
- [x] AC 6.3: THE Auth_Service SHALL thiết lập chính sách OTP mặc định cho Realm
  - **Implemented:** Cấu hình TOTP Policy mặc định trong `tenant-realm-template.json`
- [x] AC 6.4: THE API Gateway SHALL hỗ trợ thu hồi token qua JTI Blacklisting
  - **Implemented:** Kong plugin `dynamic-policy` trích xuất `jti` qua `ngx.decode_base64` và kiểm tra blacklist trong Redis
- [x] AC 6.5: THE Sync_Worker SHALL đồng bộ tin cậy cấu hình qua Redis Streams
  - **Implemented:** Sửa đổi `sync_worker.py` để kết nối và lắng nghe từ Redis Stream `config.updates.stream` sử dụng Consumer Group `auth-sync-group`

### Task 7: Client Scopes (Least Privilege) (MỚI)
> *User Story: Là platform security architect, tôi muốn giới hạn quyền hạn truy cập của từng client Dashboard và API Gateway đối với từng dịch vụ backend.*

**Acceptance Criteria Implementation:**
- [x] AC 7.1: Định nghĩa các Client Scopes chuyên biệt cho các services nghiệp vụ (18 scopes bao gồm `campaign`, `crm`, `chatbot`, `content`, `messaging`, `analytics`, `ai-core`, `tenant-config`, `dms`, `link-shortener`, `scheduler`, `comment-manager`, `notification`, `channel-connector`, `media-processor`, `knowledge-base`, `observability`) khởi tạo động qua `provision_realm.py`
- [x] AC 7.2: Cấu hình các Client Scopes này làm `optionalClientScopes` cho client `dashboard` và `api-gateway` tự động khi chạy provision
- [x] AC 7.3: Xác minh Access Token phát hành cho client Dashboard chứa claim `scope` phản ánh đúng danh sách scopes được yêu cầu (Verified qua test suite của Gateway)


## Verification & Testing

### Automated Tests
- [x] Write unit tests verifying core logic of each Requirement.
- [x] Write integration tests for API endpoints.
  - **File:** `services/auth/tests/test_auth.py`
  - Tests: OIDC discovery, OAuth2 password grant, token refresh, token revocation,
    RBAC roles existence, RBAC role in token, RBAC Manager role creation,
    dynamic password policy sync, brute force protection sync, RS256 signing
- [x] Verify tenant isolation by querying data across different tenant IDs.
  - Mỗi test dùng UUID riêng biệt cho `TEST_TENANT_ID` (fixture scoped)

### Manual Verification
- [x] Deploy service to local Docker / Kubernetes cluster.
- [x] Perform end-to-end tests using the Gateway (Kong) routing.

## Done When

- [x] All Acceptance Criteria for Requirements are implemented and verified.
- [x] Unit test coverage is >80%.
- [x] Logs are formatted as structured JSON and trace context is propagated.
- [x] Tenant isolation (RLS / metadata filtering) is strictly enforced.

---
*Last updated: 2026-06-01 — All core tasks COMPLETED*
