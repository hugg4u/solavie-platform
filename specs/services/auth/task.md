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
- [ ] AC 3.1: THE Auth_Service SHALL hỗ trợ roles: Admin, Manager, Agent, Viewer
- [ ] AC 3.2: Admin: full access tất cả features
- [ ] AC 3.3: Manager: manage content, campaigns, analytics, approve posts
- [ ] AC 3.4: Agent: inbox, reply messages, view contacts
- [ ] AC 3.5: Viewer: read-only access to dashboards and reports
- [ ] AC 3.6: THE Auth_Service SHALL include roles trong JWT token claims

### Task 4: 4: User Management
> *User Story: Là admin, tôi muốn quản lý users trong tổ chức.*

**Acceptance Criteria Implementation:**
- [ ] AC 4.1: THE Auth_Service SHALL hỗ trợ CRUD users per realm
- [ ] AC 4.2: THE Auth_Service SHALL hỗ trợ invite user via email
- [ ] AC 4.3: THE Auth_Service SHALL hỗ trợ password reset flow
- [ ] AC 4.4: THE Auth_Service SHALL hỗ trợ disable/enable user accounts
- [ ] AC 4.5: THE Auth_Service SHALL áp dụng chính sách mật khẩu (độ dài tối thiểu `auth_password_min_length` từ 6-30 ký tự, độ phức tạp) được đồng bộ từ cấu hình bảo mật của Tenant Config Service
    - [ ] AC 4.5.1: Xây dựng sync subscriber/worker lắng nghe event `config.updates` từ Tenant Config Service
    - [ ] Call Keycloak Admin API để đồng bộ `passwordPolicy` (minLength, upperCase, digit, specialChars)
    - [ ] Viết integration test kiểm thử việc thay đổi password policy động áp dụng thành công cho user mới/reset password

### Task 5: 5: Token Security
> *User Story: Là security engineer, tôi muốn tokens được quản lý an toàn.*

**Acceptance Criteria Implementation:**
- [ ] AC 5.1: THE Auth_Service SHALL sign tokens với RS256 (asymmetric keys)
- [ ] AC 5.2: THE Auth_Service SHALL hỗ trợ token revocation
- [ ] AC 5.3: THE Auth_Service SHALL giới hạn số lần đăng nhập sai (brute force protection) theo cấu hình `auth_max_login_attempts` (3-20 lần) được đồng bộ từ Tenant Config Service
    - [ ] AC 5.3.1: Đồng bộ cấu hình brute-force qua event `config.updates`
    - [ ] Call Keycloak Admin API để cập nhật `failureFactor` tương ứng với `auth_max_login_attempts`
    - [ ] Viết integration test giả lập đăng nhập sai liên tiếp để kiểm chứng tài khoản bị khóa theo đúng config
- [ ] AC 5.4: THE Auth_Service SHALL log tất cả authentication events (login, logout, failed attempts)
- [ ] AC 5.5: THE Auth_Service SHALL hỗ trợ session management (list active sessions, force logout)

## Verification & Testing

### Automated Tests
- [ ] Write unit tests verifying core logic of each Requirement.
- [ ] Write integration tests for API endpoints.
- [ ] Verify tenant isolation by querying data across different tenant IDs.

### Manual Verification
- [ ] Deploy service to local Docker / Kubernetes cluster.
- [ ] Perform end-to-end tests using the Gateway (Kong) routing.

## Done When

- [ ] All Acceptance Criteria for Requirements are implemented and verified.
- [ ] Unit test coverage is >80%.
- [ ] Logs are formatted as structured JSON and trace context is propagated.
- [ ] Tenant isolation (RLS / metadata filtering) is strictly enforced.
