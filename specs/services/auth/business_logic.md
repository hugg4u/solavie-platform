# Business Logic & Rules — Auth Service (Keycloak)

Tài liệu này đặc tả chi tiết các quy tắc nghiệp vụ (Business Rules), quy trình xử lý, và các ràng buộc dữ liệu được áp dụng cho **Auth Service (Keycloak)** trong hệ thống Solavie Marketing Platform.

---

## 1. Phân Tách Trách Nhiệm (Separation of Concerns)

Hệ thống áp dụng kiến trúc **Hybrid Identity & Profile**, phân tách triệt để giữa Xác thực (Authentication) và Nghiệp vụ (Business Profile):
*   **Auth Service (Keycloak):** Chỉ chịu trách nhiệm quản lý các thông tin danh tính cốt lõi bao gồm: `UUID` (khóa chính `sub`), `Email`, `Mật khẩu`, trạng thái kích hoạt tài khoản (`enabled`), và các Sessions hoạt động.
*   **User Service (Backend):** Lưu trữ và quản lý toàn bộ thông tin nghiệp vụ phong phú của nhân viên như: Số điện thoại, phòng ban, ảnh đại diện (avatar), và cấu hình giao diện cá nhân.
*   **Liên kết dữ liệu:** Bản ghi User nghiệp vụ tại User Service liên kết 1:1 với tài khoản Keycloak thông qua khóa ngoại `id` (UUID) khớp với claim `sub` trong JWT Access Token.

---

## 2. Mô Hình Đa Khách Thuê (Keycloak Organizations)

Để đảm bảo tính cô lập dữ liệu và khả năng mở rộng quy mô lớn (Enterprise SaaS):
*   **Realm chung:** Toàn bộ hệ thống chạy trên một Realm duy nhất là `solavie`.
*   **Keycloak Organizations:** Mỗi doanh nghiệp (Tenant) được ánh xạ thành một Organization riêng biệt bên trong Realm `solavie`.
    *   Tên định danh (alias) của Organization bắt buộc trùng với `tenant_id` (UUID) của Tenant.
    *   Mỗi người dùng (User) thuộc Tenant đó bắt buộc phải được liên kết làm thành viên (Member) của Organization tương ứng.
*   **Token Claim Injection:** Khi người dùng đăng nhập thành công, Keycloak Client Mapper sẽ tự động trích xuất thuộc tính Organization và inject các thông tin sau vào JWT Access Token:
    *   `tenant_id`: Mã UUID của doanh nghiệp.
    *   `organization`: Object chứa ID doanh nghiệp và danh sách vai trò (`roles`).

---

## 3. Quản Lý Vai Trò (Roles & Permissions Logic)

Hệ thống hỗ trợ cả vai trò mặc định của hệ thống và vai trò tùy chỉnh do khách thuê tự thiết lập:

### 3.1. Vai Trò Hệ Thống Mặc Định (Org-scoped Roles)
Mỗi Organization được khởi tạo tự động 4 vai trò mặc định:
1.  **`admin`:** Toàn quyền quản trị tài nguyên của doanh nghiệp đó.
2.  **`manager`:** Quản lý chiến dịch, nội dung, phân tích báo cáo và duyệt bài viết.
3.  **`agent`:** Tiếp nhận tin nhắn, trả lời khách hàng, tương tác hộp thư và quản lý danh bạ.
4.  **`viewer`:** Chỉ đọc (Read-only) các báo cáo và Dashboard đo lường hiệu năng.

### 3.2. Vai Trò Tùy Chỉnh (Custom Org Roles)
Tenant Admin có quyền tạo các vai trò nghiệp vụ đặc thù cho tổ chức (ví dụ: `sales_agent`, `support_lead`).
*   **Quy tắc đặt tên trên IDP:** Để tránh xung đột tên vai trò giữa các Tenant trong cùng một Realm `solavie` dùng chung, các vai trò tùy chỉnh khi đồng bộ lên Keycloak phải được đặt tên theo định dạng:
    $$\text{Name on Keycloak} = \text{tenant\_id} : \text{custom\_role\_name}$$
*   **Bảo vệ Client Credentials:** Auth Service tuyệt đối không mở cổng Keycloak Admin APIs trực tiếp cho các dịch vụ cấu hình hay Client Dashboard. Client Credentials có quyền quản trị realm (`user-service-client`) chỉ được cấp cho **User Service** đóng vai trò là **Auth Proxy** duy nhất.
*   **Quy trình đồng bộ (Phương án A):**
    1.  Tenant Admin tạo Custom Role tại **Tenant Config Service**.
    2.  Tenant Config Service lưu thông tin phân quyền cục bộ, sau đó gọi REST API của **User Service** (kèm chữ ký HMAC-SHA256 tin cậy) để yêu cầu tạo Realm Role tương ứng trên Keycloak.
    3.  User Service kiểm tra tính hợp lệ và gọi Keycloak Admin API để đồng bộ vai trò.

---

## 4. Chính Sách Bảo Mật Động (Dynamic Security Policies)

Chính sách bảo mật tài khoản được cấu hình động bởi Tenant Admin và đồng bộ sang Keycloak Realm thông qua **Auth Sync Worker** (chạy ngầm lắng nghe Redis Streams `config.updates.stream`):

### 4.1. Chính Sách Mật Khẩu (Password Policy)
*   Tham số cấu hình: `auth_password_min_length` (giá trị từ 6 đến 30 ký tự).
*   Công thức mapping cấu hình Keycloak:
    `length(auth_password_min_length) and upperCase(1) and digits(1) and specialChars(1)`
*   Mọi yêu cầu đăng ký hoặc đổi mật khẩu không thỏa mãn chính sách này sẽ bị Keycloak từ chối ngay lập tức.

### 4.2. Khóa Tài Khoản (Brute Force Protection)
*   Tham số cấu hình: `auth_max_login_attempts` (giá trị từ 3 đến 20 lần nhập sai).
*   Quy tắc áp dụng:
    *   Bật thuộc tính `bruteForceProtected = true`.
    *   Đặt tham số `failureFactor = auth_max_login_attempts`.
    *   Đặt thời gian khóa tài khoản tạm thời mặc định là 15 phút.

---

## 5. Đồng Bộ Sự Kiện Thay Đổi Danh Tính (User Events SPI)

Để ngăn ngừa tình trạng không đồng bộ dữ liệu giữa Identity Provider và Database Backend:
*   Auth Service cấu hình **Custom Event Listener SPI** để theo dõi các sự kiện vòng đời tài khoản.
*   Khi xảy ra sự kiện, SPI sẽ tự động gửi sự kiện vào Redis channel `auth.user.events` với các quy tắc ánh xạ sau:

| Loại Sự Kiện Keycloak | Event Type Mapping | Ý Nghĩa Nghiệp Vụ |
|:---|:---|:---|
| `REGISTER` / `VERIFY_EMAIL` | `user.verified` | Nhân viên kích hoạt tài khoản thành công $\rightarrow$ Cập nhật trạng thái local thành `ACTIVE`. |
| `UPDATE_EMAIL` | `user.email_updated` | Thay đổi email liên lạc chính $\rightarrow$ Cập nhật email trong hồ sơ Backend. |
| `DISABLE_USER` | `user.disabled` | Khóa tài khoản nhân viên $\rightarrow$ Cập nhật trạng thái thành `SUSPENDED` và thu hồi toàn bộ sessions. |
| `DELETE_USER` | `user.deleted` | Xóa vĩnh viễn tài khoản $\rightarrow$ Thực hiện xóa mềm (Soft Delete) hồ sơ nghiệp vụ. |

---

## 6. Bảo Mật Zero-Trust và Ngăn Chặn Privilege Escalation

*   **Xác thực API Gateway:** Mọi yêu cầu truy xuất Endpoint quản trị hoặc manifest (`/api/v1/permissions/manifest`) phải đi kèm chữ ký số HMAC-SHA256 trên header `X-Permissions-Signature`.
*   **Bảo vệ vai trò đặc quyền:**
    *   Hệ thống sở hữu danh sách các vai trò hệ thống bảo lưu nghiêm ngặt: `['system', 'system_admin', 'super_admin', 'root']`.
    *   **Quy tắc chặn đứng leo thang đặc quyền (Privilege Escalation):** Vai trò `system` hoặc `system_admin` chỉ được tự động gán quyền wildcard `*` và bỏ qua kiểm tra an toàn khi và chỉ khi `tenant_id` đi kèm trùng khớp với Realm Master của Platform (`solavie-system-master`). Mọi nỗ lực gửi token chứa vai trò này từ tenant thông thường đều bị hệ thống chặn đứng với lỗi `403 Forbidden`.
