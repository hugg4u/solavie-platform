# Requirements — User Service (Internal Profile)

## Overview
Dịch vụ quản lý hồ sơ nghiệp vụ và trạng thái hoạt động thực tế của người dùng hệ thống (User - nhân viên vận hành, marketing, admin doanh nghiệp). Dịch vụ hoạt động theo mô hình Hybrid phối hợp với Keycloak (Identity Provider) để phân tách rõ ràng trách nhiệm giữa Xác thực và Nghiệp vụ.

## Tech Stack
- **Runtime:** Node.js 20 (NestJS Framework)
- **Database:** PostgreSQL 16 (solavie_user_db)
- **Port:** 3008
- **Port gRPC:** 50058 (cho giao tiếp nội bộ tốc độ cao)

## Requirements

### Requirement 1: Quản lý hồ sơ nghiệp vụ (User Profile Management)

**User Story:** Là nhân viên, tôi muốn cập nhật các thông tin cá nhân mở rộng để đồng nghiệp nhận biết trong hệ thống.

#### Acceptance Criteria
1. THE User_Service SHALL hỗ trợ lưu trữ các thông tin nghiệp vụ: số điện thoại, ảnh đại diện (avatar), phòng ban (department).
2. Bảng dữ liệu `users` SHALL sử dụng khóa chính là `id` kiểu dữ liệu UUID trùng khớp 100% với UUID của người dùng trên Keycloak (trích xuất từ claim `sub` trong JWT Token).
3. THE User_Service SHALL cung cấp API lấy thông tin cá nhân (`/api/v1/users/me`) và cập nhật hồ sơ (`/api/v1/users/profile`).
4. THE User_Service SHALL lưu trữ cấu hình cá nhân (theme, ngôn ngữ hiển thị) tại bảng cấu hình riêng biệt liên kết 1:1 với hồ sơ User.

### Requirement 2: Đồng bộ từ User Service lên Keycloak (US ➡️ KC)

**User Story:** Là quản trị viên doanh nghiệp (Tenant Admin), tôi muốn mọi thao tác quản lý nhân viên và cập nhật hồ sơ trên Dashboard được tự động đồng bộ lên máy chủ xác thực Keycloak.

#### Acceptance Criteria
1. THE User_Service SHALL cung cấp API mời nhân viên (`/api/v1/users/invite`).
2. Khi Tenant Admin gửi lời mời, User_Service SHALL:
   * Tạo bản ghi User mới trong bảng `users` với trạng thái `PENDING` và `tenant_id` của Admin.
   * Gọi Keycloak Admin API để tạo một tài khoản "Shadow" (chưa kích hoạt) tương ứng trên Realm của Tenant.
   * Sinh mã Token kích hoạt dùng một lần (hết hạn sau 24 giờ).
3. THE User_Service SHALL gửi email mời kèm link kích hoạt chứa mã token bảo mật thông qua dịch vụ Notification Service.
4. Khi Tenant Admin thực hiện khóa hoặc mở khóa tài khoản nhân viên trên Dashboard, User_Service SHALL gọi Keycloak Admin API tương ứng để đặt giá trị `"enabled": false` (hoặc `true`) trên Keycloak, đồng thời gửi sự kiện `token.revoked` sang Redis để thu hồi session/token ngay lập tức (< 1ms).
5. Khi nhân viên cập nhật thông tin cá nhân cơ bản (Email, Họ, Tên) trên Dashboard, User_Service SHALL gọi Keycloak Admin API tương ứng để đồng bộ thông tin lên Keycloak.
6. Trước khi gửi yêu cầu đổi Email lên Keycloak, User_Service SHALL gọi API kiểm tra chéo tính duy nhất của Email mới để tránh lỗi `409 Conflict`.
7. THE User_Service SHALL cung cấp các REST API gán và thu hồi vai trò tùy chỉnh cho người dùng (`POST /api/v1/users/:id/roles`, `DELETE /api/v1/users/:id/roles/:name`) để ánh xạ thành viên doanh nghiệp vào Realm Roles của Keycloak.
8. THE User_Service SHALL cung cấp các REST API proxy tạo và xóa vai trò tùy chỉnh (`POST /api/v1/users/roles`, `DELETE /api/v1/users/roles/:name`) để làm đầu mối cổng trung gian an toàn (Auth Proxy) cho Tenant Config Service đồng bộ Realm Roles lên Keycloak Realm `solavie`.

### Requirement 3: Cô lập đa khách thuê (Multi-tenant Isolation)

**User Story:** Là chủ doanh nghiệp (Tenant Owner), tôi muốn đảm bảo nhân viên của mình hoàn toàn được bảo mật và không bị rò rỉ dữ liệu sang doanh nghiệp khác.

#### Acceptance Criteria
1. Mọi bản ghi User trong bảng `users` SHALL chứa cột `tenant_id` kiểu dữ liệu UUID.
2. Bảng `users` SHALL được bảo vệ bằng chính sách **PostgreSQL Row-Level Security (RLS)** trên cột `tenant_id`.
3. Mọi kết nối database từ User Service nghiệp vụ bắt buộc phải set context `tenant_id` dựa trên Header `X-Tenant-Id` được API Gateway (Kong) chuyển tiếp từ JWT Token.

### Requirement 4: Đồng bộ từ Keycloak xuống User Service (KC ➡️ US)

**User Story:** Là security engineer, tôi muốn khi một tài khoản bị khóa, kích hoạt hoặc thay đổi thông tin trên Keycloak thì dữ liệu nghiệp vụ ở Backend cũng được cập nhật ngay lập tức.

#### Acceptance Criteria
1. THE User_Service SHALL tích hợp một Webhook Endpoint hoặc lắng nghe hàng đợi sự kiện (Redis/Kafka) để tiếp nhận các sự kiện thay đổi danh tính từ Keycloak.
2. Khi nhận sự kiện người dùng kích hoạt tài khoản thành công (Verify Email / Set Password), User_Service SHALL cập nhật trạng thái User thành `ACTIVE` trong cơ sở dữ liệu `solavie_user_db`.
3. Khi nhận sự kiện tài khoản bị khóa (Suspended / Disabled), User_Service SHALL cập nhật trạng thái User thành `SUSPENDED` tương ứng.
4. Khi nhận sự kiện email của người dùng thay đổi từ Keycloak, User_Service SHALL cập nhật email trong database local.
5. Khi nhận sự kiện xóa tài khoản người dùng từ Keycloak, User_Service SHALL thực hiện xóa mềm (Soft Delete) hồ sơ nghiệp vụ tương ứng.
6. THE User_Service SHALL tích hợp cơ chế **Lazy Synchronization** (Tự phục hồi đồng bộ khi đăng nhập): Khi người dùng đăng nhập lần đầu tiên thành công và có JWT Token hợp lệ, nếu trạng thái DB local vẫn là `PENDING`, User_Service SHALL tự động cập nhật trạng thái User thành `ACTIVE` để dự phòng sự cố mất Webhook.
7. Endpoint Webhook nhận sự kiện từ Keycloak (`POST /api/v1/users/events`) SHALL được bảo mật bằng cơ chế **Signature Verification** (xác thực chữ ký HMAC-SHA256 với Shared Secret) để ngăn chặn các request giả mạo.


### Requirement: Zero-Trust Access Control & Permission Manifest

**User Story:** Là Tenant Admin, tôi muốn xem danh sách quyền hạn mà dịch vụ `user` hỗ trợ để thiết lập vai trò tùy chỉnh trên Dashboard và đảm bảo bảo mật Zero-Trust downstream.

#### Acceptance Criteria
1. THE USER_Service SHALL cung cấp API manifest tại `GET /api/v1/permissions/manifest` trả về danh sách tài nguyên (resources) và hành động (actions) được hỗ trợ.
2. THE USER_Service SHALL thực hiện kiểm tra chữ ký số HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET` để xác thực request được gửi trực tiếp từ API Gateway tin cậy.
3. THE USER_Service SHALL sử dụng phương pháp so sánh **Timing-Safe** (`crypto.timingSafeEqual`) khi kiểm tra chữ ký số HMAC-SHA256 để triệt tiêu nguy cơ side-channel attack. Bất kỳ request nào không khớp chữ ký SHALL bị chặn và trả về lỗi `403 Forbidden`.
4. THE USER_Service SHALL thực hiện kiểm tra quyền in-memory O(1) dựa trên HTTP Header `X-User-Permissions` truyền từ Gateway. Định dạng quyền của dịch vụ tuân theo cấu trúc `auth:{resource}:{action}` hỗ trợ ký tự đại diện `*` (Super Admin), `auth:*` (Toàn quyền trên service), và `auth:{resource}:*` (Toàn quyền trên tài nguyên).
5. Đối với vai trò `system` hoặc `system_admin`, THE USER_Service SHALL chỉ cho phép tự động gán quyền wildcard `*` và bypass kiểm tra khi và chỉ khi `tenant_id` trích xuất trùng khớp với ID của Realm Master (`solavie-system-master`). Nếu vai trò `system`/`system_admin` xuất hiện ở Realm của tenant thông thường, USER_Service SHALL chặn và trả về lỗi `403 Forbidden` để ngăn chặn Privilege Escalation.
6. THE USER_Service SHALL chặn và từ chối mọi yêu cầu tạo mới hoặc gán các vai trò thuộc danh sách từ khóa bảo lưu (`system`, `system_admin`, `super_admin`, `root`) cho người dùng thuộc tenant thông thường.

