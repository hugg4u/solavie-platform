# Task Checklist — User Service

## Overview
Tài liệu này theo dõi tiến độ triển khai của **User Service** (quản lý hồ sơ nghiệp vụ và trạng thái User) dựa trên các yêu cầu đặc tả.

### Technical Stack & Configuration
- **Runtime:** Node.js 20 (NestJS Framework)
- **Database:** PostgreSQL 16
- **Port:** 3008
- **Port gRPC:** 50058

---

## Tasks Checklist

### Task 1: Thiết lập cấu trúc dự án & Cơ sở dữ liệu
> *Mục tiêu: Dựng khung mã nguồn NestJS và khởi tạo các bảng dữ liệu RLS.*
- [x] Dựng khung dự án NestJS (Port 3008) với các thư viện cần thiết (Prisma / TypeORM, gRPC, Class Validator).
- [x] Thiết lập tệp tin Migration khởi tạo database `solavie_user_db`.
  - [x] Khởi tạo bảng `users` với khóa chính UUID và trạng thái mặc định `PENDING`.
  - [x] Khởi tạo bảng `user_preferences` chứa cấu hình theme, ngôn ngữ.
- [x] Cấu hình chính sách PostgreSQL Row-Level Security (RLS) trên cột `tenant_id`.
- [x] Viết middleware thiết lập tenant context (`app.current_tenant_id`) cho mỗi request.

### Task 2: Triển khai API REST & Phân quyền Gateway
> *Mục tiêu: Cung cấp các endpoint quản lý hồ sơ cá nhân, khóa tài khoản và tích hợp phân quyền.*
- [x] Triển khai API `GET /api/v1/users/me` lấy hồ sơ User hiện tại kèm cấu hình Preferences.
- [x] Triển khai API `PUT /api/v1/users/profile` cập nhật SĐT, avatar, email, họ, tên.
  - [x] Tích hợp kiểm tra tính duy nhất của email mới trước khi cập nhật.
- [x] Triển khai API `POST /api/v1/users/:id/suspend` và `/unsuspend` để Admin khóa/mở khóa tài khoản nhân viên.
- [x] Triển khai API `PUT /api/v1/users/preferences` thay đổi theme, ngôn ngữ.
- [x] Cấu hình API Gateway (Kong) để định tuyến `/api/v1/users` về cổng `3008`.
  - [x] Đảm bảo Gateway chuyển tiếp header `X-User-Id` và `X-Tenant-Id`.

### Task 3: Triển khai Đồng bộ lên Keycloak (US ➡️ KC)
> *Mục tiêu: Xây dựng các tích hợp gọi Keycloak Admin API để đồng bộ dữ liệu ngược.*
- [x] Thiết lập kết nối Keycloak Admin Client (sử dụng mật khẩu/credentials của admin client).
- [x] Triển khai logic luồng mời nhân viên `POST /api/v1/users/invite` (gọi Keycloak Admin API tạo user disabled, lưu DB local, sinh link và đẩy email).
- [x] Triển khai logic luồng khóa/mở khóa (gọi Keycloak Admin API cập nhật trạng thái `"enabled": false/true`).
  - [x] Tích hợp gọi Keycloak API Force Logout `POST /admin/realms/solavie/users/{id}/logout` để hủy các sessions hiện tại của user bị khóa.
  - [x] Triển khai publish sự kiện `token.revoked` (kèm theo các `jti` liên quan) lên Redis để Gateway lập tức chặn đứng truy cập.
- [x] Triển khai logic luồng cập nhật thông tin (gọi Keycloak Admin API đồng bộ email, họ, tên).
- [x] Triển khai các REST API gán và thu hồi vai trò tùy chỉnh cho người dùng (`POST /api/v1/users/:id/roles`, `DELETE /api/v1/users/:id/roles/:name`) để gán vai trò của người dùng trên Keycloak Organization.
- [x] Triển khai các REST API Proxy tạo và xóa vai trò tùy chỉnh (`POST /api/v1/users/roles`, `DELETE /api/v1/users/roles/:name`) để làm Auth Proxy trung gian đồng bộ Organization-scoped Roles lên Keycloak Organization `solavie` cho Tenant Config Service gọi sang.
- [x] **[BẢO MẬT]** Tái cấu trúc cơ chế lấy Admin Token: Chuyển đổi từ Password Grant Flow (sử dụng tài khoản master admin) sang Client Credentials Flow sử dụng client chuyên dụng `user-service-client` và biến môi trường `KEYCLOAK_CLIENT_SECRET` trong realm `solavie` để tuân thủ nguyên tắc Least Privilege.

### Task 4: Triển khai giao thức gRPC nội bộ
> *Mục tiêu: Cung cấp giao thức gRPC tốc độ cao cho các service khác gọi chéo.*
- [x] Định nghĩa tệp tin proto `user.proto`.
- [x] Triển khai gRPC Server trên port `50058`.
- [x] Viết handler xử lý hàm gRPC `GetUserProfile` trả về hồ sơ nhân viên.
- [x] Viết handler xử lý hàm gRPC `ValidateUserAccess` kiểm tra vai trò nghiệp vụ.

### Task 5: Triển khai Đồng bộ từ Keycloak xuống (KC ➡️ US)
> *Mục tiêu: Lắng nghe sự kiện của Keycloak để cập nhật trạng thái User.*
- [x] Xây dựng Webhook Endpoint (`POST /api/v1/users/events`) để nhận sự kiện từ Keycloak Event Listener.
  - [x] Triển khai xác thực chữ ký Webhook Signature (HMAC-SHA256) trên User Service.
- [x] Triển khai xử lý sự kiện `user.verified` ➡️ Cập nhật trạng thái sang `ACTIVE`.
- [x] Triển khai xử lý sự kiện `user.disabled` ➡️ Cập nhật trạng thái sang `SUSPENDED`.
- [x] Triển khai xử lý sự kiện `user.email_updated` ➡️ Cập nhật email cục bộ.
- [x] Triển khai xử lý sự kiện `user.deleted` ➡️ Thực hiện xóa mềm (Soft Delete) hồ sơ User.
- [x] Triển khai cơ chế **Lazy Synchronization** (Tự kích hoạt User sang `ACTIVE` khi nhận JWT Token hợp lệ lần đầu nếu trạng thái DB đang là `PENDING`).

---

## Verification & Testing

### Automated Tests
- [x] Viết Unit test cho các Controller và Service nghiệp vụ (độ phủ >80%).
- [x] Viết Integration test xác minh chính sách RLS ngăn chặn rò rỉ chéo tenant dữ liệu.
- [x] Viết Integration test giả lập luồng mời nhân viên và kích hoạt tài khoản.

### Manual Verification
- [x] Khởi chạy container `solavie-user-service` kết nối chung mạng Docker.
- [x] Sử dụng pgAdmin truy cập `solavie_user_db` kiểm tra sự tồn tại của các bảng.
- [x] Gọi API invite qua Postman/cURL xác minh email kích hoạt gửi thành công.


### Task: Security Integration & Dynamic RBAC (MỚI)
- [x] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `user`.
- [x] Triển khai **AsyncLocalStorage** middleware để truyền tải tenant context (`tenant_id`) an toàn qua các luồng async trong NestJS.
- [x] Tích hợp **Prisma Extension** hoặc TypeORM Subscriber tự động thực thi `SET LOCAL app.current_tenant_id` từ AsyncLocalStorage context trước mỗi query để kích hoạt RLS.
- [x] Triển khai NestJS `AuthGuard` / `HmacGuard` thực hiện xác thực chữ ký HMAC-SHA256 trên header `x-permissions-signature` bằng `GATEWAY_SIGNING_SECRET`.
  - [x] **[CRITICAL]** Sử dụng `crypto.timingSafeEqual` để so sánh chữ ký số timing-safe.
- [x] Triển khai NestJS `PermissionsGuard` phân giải quyền hạn in-memory O(1) hỗ trợ wildcard (`*`, `user:*`, `user:{resource}:*`).
  - [x] **[CRITICAL]** Bổ sung cơ chế bảo vệ chống Privilege Escalation: Chỉ cho phép tự động gán wildcard `*` cho role `system`/`system_admin` nếu `tenant_id` trùng khớp với Master Tenant ID (`solavie-system-master`).
  - [x] Chặn gán/tạo vai trò thuộc danh sách từ khóa bảo lưu (`system`, `system_admin`, `super_admin`, `root`) cho người dùng thường.
- [x] Thực hiện tích hợp Endpoint `/api/v1/permissions/manifest` trả về danh sách tài nguyên và quyền hạn của service.
- [x] Bổ sung các test cases kiểm tra Signature Verification, Master Realm check bypass, gán từ khóa bảo lưu, và Access Control Denied.

### Task: Logging & Observability (MỚI)
> *Mục tiêu: Đảm bảo khả năng giám sát chất lượng vận hành và bảo mật của dịch vụ theo tiêu chuẩn.*
- [x] Tích hợp thư viện logging (Pino hoặc Winston) xuất định dạng JSON có cấu trúc.
- [x] Thiết lập quy tắc mặt nạ hóa (Masking) thông tin nhạy cảm PII (Số điện thoại) trong logs.
- [x] Cấu hình OpenTelemetry Node SDK để tự động capture trace spans, đồng thời inject `trace_id` và `span_id` vào JSON logs.
- [x] Expose endpoint `/metrics` công bố các custom metrics (HTTP requests total, latency, signature failures, permission denials, Keycloak sync failures).
- [x] Cấu hình Prometheus Alertmanager Alerts theo định nghĩa trong tài liệu `logging.md`.

---

## Service Discovery Client Integration (MỚI)

### Task 21: Service Discovery Client Integration
- [x] AC 21.1: Triển khai lớp `ServiceRegistryClient` tự động lấy IP nội bộ qua kết nối UDP socket ảo.
- [x] AC 21.2: Tích hợp `ServiceRegistryClient` vào lifecycle hook khởi động và tắt của ứng dụng (NestJS).
- [x] AC 21.3: Triển khai cấu trúc JSON logs cho các sự kiện đăng ký và lỗi heartbeat lên Redis.
