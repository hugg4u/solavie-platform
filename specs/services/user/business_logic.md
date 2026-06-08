# Business Logic & Rules — User Service

Tài liệu này đặc tả chi tiết các quy tắc nghiệp vụ (Business Rules), quy trình xử lý, và các ràng buộc dữ liệu được áp dụng cho **User Service** trong hệ thống Solavie Marketing Platform.

---

## 1. Vai Trò Auth Proxy và Quản Trị Keycloak (Downstream Proxy)

User Service giữ vai trò độc quyền nắm giữ Client Credentials có quyền quản trị realm (`user-service-client`). 
*   **Bảo vệ thông tin bảo mật:** Để tránh rò rỉ admin credentials, mọi dịch vụ khác (như Tenant Config Service) khi cần tương tác với cấu hình vai trò hay định danh trên Keycloak bắt buộc phải gọi thông qua các API Proxy của User Service.
*   **Xác thực nội bộ:** Các yêu cầu Proxy tạo/xóa vai trò (`POST /api/v1/users/roles`, `DELETE /api/v1/users/roles/:name`) phải đi kèm chữ ký HMAC-SHA256 hợp lệ ký bằng `GATEWAY_SIGNING_SECRET`.
*   **Ánh xạ tên vai trò:** Khi tạo vai trò tùy chỉnh trên Keycloak, User Service tự động thêm prefix `tenant_id:` vào tên vai trò để cô lập danh không gian vai trò giữa các tenant sử dụng chung một Realm.

---

## 2. Quy Trình Mời và Kích Hoạt Nhân Viên (Invitation & Activation Flow)

Quy trình mời nhân viên mới tham gia doanh nghiệp được thực hiện bất đồng bộ đảm bảo an toàn danh tính:

1.  **Giai đoạn Khởi tạo:**
    *   Tenant Admin gửi yêu cầu mời qua REST API.
    *   User Service tạo bản ghi nhân viên trong bảng `users` với trạng thái mặc định là `PENDING` và lưu ID doanh nghiệp `tenant_id` của admin.
    *   User Service thay mặt gọi Keycloak Admin API để tạo một tài khoản "Shadow" (trạng thái `"enabled": false`) với Email được mời. Nhận về Keycloak User UUID và lưu khớp vào khóa chính `id` của bảng `users`.
2.  **Giao tiếp & Kích hoạt:**
    *   User Service sinh một Token kích hoạt dùng một lần có thời gian hết hạn nghiêm ngặt (TTL 24 giờ).
    *   Gửi sự kiện `user.invited` (chứa email, link kích hoạt kèm token) sang Notification Service để gửi mail cho nhân viên.
    *   Nhân viên nhấp vào link, thiết lập mật khẩu trên Keycloak giao diện. Keycloak kích hoạt tài khoản và xác minh email.
3.  **Lazy Synchronization (Tự phục hồi đồng bộ):**
    *   Trong trường hợp Webhook từ Keycloak gửi về User Service bị trễ hoặc thất lạc do sự cố mạng, hệ thống áp dụng cơ chế tự phục hồi: Khi người dùng đăng nhập lần đầu tiên thành công và gửi request kèm JWT hợp lệ đến User Service, nếu trạng thái của User trong cơ sở dữ liệu local vẫn là `PENDING`, User Service sẽ tự động cập nhật trạng thái User thành `ACTIVE` ngay lập tức để không cản trở trải nghiệm của người dùng.

---

## 3. Quy Trình Khóa và Mở Khóa Tài Khoản (User Suspension Flow)

Khi Tenant Admin thực hiện khóa (suspend) hoặc mở khóa (unsuspend) một nhân viên:

*   **Vô hiệu hóa trên Keycloak:** User Service gọi Keycloak Admin API để đặt giá trị `"enabled": false` (hoặc `true` khi mở khóa) trên tài khoản người dùng chỉ định.
*   **Hủy bỏ Sessions:** User Service gọi Keycloak Admin API gửi yêu cầu Force Logout (`POST /admin/realms/{realm}/users/{id}/logout`) để hủy lập tức các token/session đang hoạt động của user đó trên Keycloak.
*   **Thu hồi tức thời tại Gateway (JTI Blacklisting):** User Service trích xuất các mã token đang hoạt động (nếu có lưu cache) hoặc publish sự kiện `token.revoked` (kèm UUID người dùng và danh sách `jti`) lên Redis cache để API Gateway (Kong) ngay lập tức từ chối mọi yêu cầu mang token cũ trong vòng `< 1ms`.
*   **Cập nhật DB nghiệp vụ:** User Service cập nhật trạng thái cột `status` trong bảng `users` thành `SUSPENDED` (hoặc `ACTIVE`).

---

## 4. Bảo Mật Zero-Trust & Chống Leo Thang Đặc Quyền (Privilege Escalation)

User Service thực thi mô hình an toàn thông tin Zero-Trust thông qua NestJS Guards:

### 4.1. Xác Thực Chữ Ký Số Timing-Safe
*   Mọi HTTP Request từ API Gateway chuyển tiếp đến phải có đầy đủ các headers: `x-tenant-id`, `x-user-id`, `x-user-permissions`, và `x-permissions-signature`.
*   Guard tính toán chữ ký số mong đợi từ payload bằng thuật toán HMAC-SHA256 với khóa `GATEWAY_SIGNING_SECRET`.
*   **Chống tấn công Side-channel (Timing Attacks):** Việc so sánh chữ ký nhận được và chữ ký mong đợi bắt buộc phải sử dụng phương thức so sánh an toàn thời gian `crypto.timingSafeEqual`. Nếu độ dài chữ ký không khớp hoặc giá trị không trùng khớp 100%, hệ thống từ chối ngay với lỗi `403 Forbidden`.

### 4.2. Khớp Quyền Hạn In-Memory O(1)
*   Phân giải chuỗi CSV `x-user-permissions` thành một Set trong memory để tối ưu hóa tốc độ tra cứu quyền.
*   Hỗ trợ cú pháp wildcard: `*` (Super Admin bypass), `user:*` (Service bypass), và `user:{resource}:*` (Resource bypass).

### 4.3. Ngăn Chặn Leo Thang Đặc Quyền (Privilege Escalation)
*   Hệ thống sở hữu danh sách các vai trò hệ thống bảo lưu nghiêm ngặt: `['system', 'system_admin', 'super_admin', 'root']`.
*   **Quy tắc kiểm tra Master Realm:** Đối với các request mang vai trò đặc quyền `system` hoặc `system_admin`, hệ thống chỉ cho phép gán quyền wildcard `*` và bỏ qua kiểm tra khi và chỉ khi `tenant_id` của request trùng khớp hoàn toàn với Realm Master (`solavie-system-master`).
*   Nếu vai trò bảo lưu này xuất hiện trong token thuộc Realm của một Tenant thông thường, User Service sẽ lập tức chặn request và trả về lỗi `403 Forbidden` để ngăn chặn hacker tự gán quyền admin hệ thống.
*   Đồng thời, hệ thống từ chối mọi yêu cầu tạo mới hoặc gán các vai trò tùy chỉnh trùng với danh sách từ khóa bảo lưu cho người dùng thông thường của tenant.
