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
- [ ] Dựng khung dự án NestJS (Port 3008) với các thư viện cần thiết (Prisma / TypeORM, gRPC, Class Validator).
- [ ] Thiết lập tệp tin Migration khởi tạo database `solavie_user_db`.
  - [ ] Khởi tạo bảng `users` với khóa chính UUID và trạng thái mặc định `PENDING`.
  - [ ] Khởi tạo bảng `user_preferences` chứa cấu hình theme, ngôn ngữ.
- [ ] Cấu hình chính sách PostgreSQL Row-Level Security (RLS) trên cột `tenant_id`.
- [ ] Viết middleware thiết lập tenant context (`app.current_tenant_id`) cho mỗi request.

### Task 2: Triển khai API REST & Phân quyền Gateway
> *Mục tiêu: Cung cấp các endpoint quản lý hồ sơ cá nhân, khóa tài khoản và tích hợp phân quyền.*
- [ ] Triển khai API `GET /api/v1/users/me` lấy hồ sơ User hiện tại kèm cấu hình Preferences.
- [ ] Triển khai API `PUT /api/v1/users/profile` cập nhật SĐT, avatar, email, họ, tên.
  - [ ] Tích hợp kiểm tra tính duy nhất của email mới trước khi cập nhật.
- [ ] Triển khai API `POST /api/v1/users/:id/suspend` và `/unsuspend` để Admin khóa/mở khóa tài khoản nhân viên.
- [ ] Triển khai API `PUT /api/v1/users/preferences` thay đổi theme, ngôn ngữ.
- [ ] Cấu hình API Gateway (Kong) để định tuyến `/api/v1/users` về cổng `3008`.
  - [ ] Đảm bảo Gateway chuyển tiếp header `X-User-Id` và `X-Tenant-Id`.

### Task 3: Triển khai Đồng bộ lên Keycloak (US ➡️ KC)
> *Mục tiêu: Xây dựng các tích hợp gọi Keycloak Admin API để đồng bộ dữ liệu ngược.*
- [ ] Thiết lập kết nối Keycloak Admin Client (sử dụng mật khẩu/credentials của admin client).
- [ ] Triển khai logic luồng mời nhân viên `POST /api/v1/users/invite` (gọi Keycloak Admin API tạo user disabled, lưu DB local, sinh link và đẩy email).
- [ ] Triển khai logic luồng khóa/mở khóa (gọi Keycloak Admin API cập nhật trạng thái `"enabled": false/true`).
  - [ ] Tích hợp gọi Keycloak API Force Logout `POST /admin/realms/{realm}/users/{id}/logout` để hủy các sessions hiện tại của user bị khóa.
  - [ ] Triển khai publish sự kiện `token.revoked` (kèm theo các `jti` liên quan) lên Redis để Gateway lập tức chặn đứng truy cập.
- [ ] Triển khai logic luồng cập nhật thông tin (gọi Keycloak Admin API đồng bộ email, họ, tên).

### Task 4: Triển khai giao thức gRPC nội bộ
> *Mục tiêu: Cung cấp giao thức gRPC tốc độ cao cho các service khác gọi chéo.*
- [ ] Định nghĩa tệp tin proto `user.proto`.
- [ ] Triển khai gRPC Server trên port `50058`.
- [ ] Viết handler xử lý hàm gRPC `GetUserProfile` trả về hồ sơ nhân viên.
- [ ] Viết handler xử lý hàm gRPC `ValidateUserAccess` kiểm tra vai trò nghiệp vụ.

### Task 5: Triển khai Đồng bộ từ Keycloak xuống (KC ➡️ US)
> *Mục tiêu: Lắng nghe sự kiện của Keycloak để cập nhật trạng thái User.*
- [ ] Xây dựng Webhook Endpoint (`POST /api/v1/users/events`) để nhận sự kiện từ Keycloak Event Listener.
  - [ ] Triển khai xác thực chữ ký Webhook Signature (HMAC-SHA256) trên User Service.
- [ ] Triển khai xử lý sự kiện `user.verified` ➡️ Cập nhật trạng thái sang `ACTIVE`.
- [ ] Triển khai xử lý sự kiện `user.disabled` ➡️ Cập nhật trạng thái sang `SUSPENDED`.
- [ ] Triển khai xử lý sự kiện `user.email_updated` ➡️ Cập nhật email cục bộ.
- [ ] Triển khai xử lý sự kiện `user.deleted` ➡️ Thực hiện xóa mềm (Soft Delete) hồ sơ User.
- [ ] Triển khai cơ chế **Lazy Synchronization** (Tự kích hoạt User sang `ACTIVE` khi nhận JWT Token hợp lệ lần đầu nếu trạng thái DB đang là `PENDING`).

---

## Verification & Testing

### Automated Tests
- [ ] Viết Unit test cho các Controller và Service nghiệp vụ (độ phủ >80%).
- [ ] Viết Integration test xác minh chính sách RLS ngăn chặn rò rỉ chéo tenant dữ liệu.
- [ ] Viết Integration test giả lập luồng mời nhân viên và kích hoạt tài khoản.

### Manual Verification
- [ ] Khởi chạy container `solavie-user-service` kết nối chung mạng Docker.
- [ ] Sử dụng pgAdmin truy cập `solavie_user_db` kiểm tra sự tồn tại của các bảng.
- [ ] Gọi API invite qua Postman/cURL xác minh email kích hoạt gửi thành công.
