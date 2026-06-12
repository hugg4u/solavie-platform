# Business Logic & Rules — Tenant Config Service

Tài liệu này đặc tả chi tiết các quy tắc nghiệp vụ (Business Rules), quy trình xử lý, và các ràng buộc dữ liệu được áp dụng cho **Tenant Config Service** trong hệ thống Solavie Marketing Platform.

---

## 1. Cơ Chế Khởi Tạo Mặc Định (Default Config & Roles Seeding Flow)

Khi một Tenant mới được tạo lập thành công trên hệ thống (nhận sự kiện tạo Tenant/Organization từ Auth Service):
*   **Tự động tạo cấu hình mặc định:** Tenant Config Service bắt buộc phải tự động khởi tạo bộ cấu hình mặc định cho Tenant đó trong cơ sở dữ liệu `config_db` trong vòng tối đa 5 giây.
*   **Bộ giá trị mặc định:** Phải tuân thủ nghiêm ngặt các thông số ban đầu của hệ thống như: `chatbot_enabled: true`, `confidence_threshold: 0.70`, `cost_limit_usd: null` (không giới hạn), `cost_alert_threshold_percent: 80` (%), `cost_limit_policy: "notify_only"`, `session_timeout_minutes: 60`, `audit_log_retention_days: 90`, `dms_max_storage_mb: 5000`...
*   **Gieo mầm vai trò và quyền mặc định (Roles Seeding):** Đồng thời trong luồng khởi tạo này, service tự động tạo 4 vai trò mặc định (`admin`, `manager`, `agent`, `viewer`) và lưu trữ danh sách permissions tương ứng của chúng vào cơ sở dữ liệu PostgreSQL.
*   **Đồng bộ Redis Cache:** Ngay sau khi lưu PostgreSQL thành công, hệ thống chuyển đổi danh sách permissions của từng vai trò thành chuỗi CSV (đã chuẩn hóa qua sắp xếp alphabet) và lưu vào Redis cache dưới các key `tenant:{tenant_id}:role:{role_name}:permissions` (TTL: 30 ngày).
*   **Xử lý lỗi:** Nếu quá trình khởi tạo cấu hình hoặc vai trò thất bại, hệ thống thực hiện retry tối đa 3 lần. Nếu vẫn thất bại, phải publish event lỗi lên Kafka DLQ để thông báo cho System Admin xử lý thủ công.

---

## 2. Ràng Buộc Kiểm Tra Dữ Liệu Đầu Vào (Validation Rules)

Mọi yêu cầu cập nhật cấu hình (`PATCH /api/v1/config/:category`) đều phải đi qua bộ lọc validate dữ liệu nghiêm ngặt trước khi ghi nhận vào PostgreSQL:

### 2.1. Ràng Buộc Giá Trị Biên & Định Dạng
*   **Các trường số thực/số nguyên:** Phải nằm trong khoảng hợp lệ quy định (ví dụ: `confidence_threshold` $\in [0.60, 0.95]$, `manual_to_auto_timeout_hours` $\in [1, 24]$).
*   **Các trường Enum:** Chỉ chấp nhận các giá trị định nghĩa trước (ví dụ: `offline_mode_behavior` $\in \{\text{"lead\_capture"}, \text{"ai\_warning"}, \text{"offline\_msg"}\}$, `cost_limit_policy` $\in \{\text{"notify\_only"}, \text{"auto\_downgrade"}, \text{"block"}\}$).
*   **Ràng buộc kiểu Boolean:** Phải là kiểu Boolean thực tế (`true`/`false`), không chấp nhận chuỗi `"true"`/`"false"` hoặc số `1`/`0`.
*   **Tham số ngân sách LLM:** Trường `cost_limit_usd` phải là số thực $\ge 0.0$ hoặc `null`. Trường `cost_alert_threshold_percent` phải là số nguyên trong khoảng $[50, 100]$.
*   **An toàn SSE MCP Server URLs:** Trường `sse_url` của whitelist MCP Server bắt buộc phải bắt đầu bằng `http://` hoặc `https://` và kết thúc bằng `/mcp` (hoặc định dạng dẫn endpoint tương đương), đồng thời chặn các ký tự đặc biệt nguy hiểm để phòng chống tấn công SSRF (Server-Side Request Forgery) và Command Injection.

### 2.2. Phản Hồi Khi Lỗi Validation
If phát hiện bất kỳ trường cấu hình nào vi phạm ràng buộc dữ liệu, Tenant Config Service bắt buộc phải từ chối **toàn bộ** request (Atomic Request) và trả về mã lỗi `422 Unprocessable Entity` kèm danh sách chi tiết các trường vi phạm và lý do cụ thể, tuyệt đối không lưu một phần cấu hình hợp lệ.

---

## 3. Quy Trình Hot Reload Cấu Hình (Redis Pub/Sub & Kafka - Luồng 3)

Để đảm bảo các thay đổi cấu hình nghiệp vụ của Admin có hiệu lực tức thời trên toàn hệ thống mà không cần khởi động lại các microservices:

1.  **Ghi dữ liệu & Phát Event:** Khi cấu hình được lưu thành công vào PostgreSQL, Tenant Config Service phải thực hiện đồng thời ghi giá trị mới vào Redis Cache key `{tenant_id}:config:{category}` và publish event thông báo thay đổi lên Redis channel `config.updates` trong cùng một transaction nghiệp vụ bất đồng bộ.
2.  **Đẩy sự kiện bảo mật lên Kafka (Luồng 3):** Nếu cấu hình thay đổi thuộc nhóm cấu hình bảo mật (`security_comments_notif` có chứa `auth_password_min_length` hoặc `auth_max_login_attempts`) hoặc thay đổi vai trò/quyền hạn tùy chỉnh (Custom Roles/Permissions), Tenant Config Service SHALL đóng vai trò là Kafka Producer để phát sự kiện thay đổi này lên Kafka topic `config.updates`. Điều này nhằm đảm bảo tính phân phối tin nhắn tin cậy (At-least-once Delivery) để Auth Service (Sync Worker) tiêu thụ và cập nhật đồng bộ lên cấu hình Keycloak Organization.
3.  **Retry logic khi lỗi hạ tầng:**
    *   *Lỗi ghi Redis Cache:* Hệ thống retry tối đa 3 lần với backoff 1 giây. Nếu vẫn lỗi, ghi log hệ thống và trả về mã HTTP `207 Multi-Status` báo cho Client biết dữ liệu DB đã lưu nhưng cache chưa đồng bộ (Services downstream sẽ lấy cấu hình mới qua cơ chế gRPC fallback khi cache miss).
    *   *Lỗi phát tin hiệu Pub/Sub:* Retry tối đa 3 lần. Nếu lỗi, ghi nhận log warning nhưng vẫn trả về HTTP `200 OK` vì DB và Cache đã đồng bộ thành công.
    *   *Lỗi đẩy Kafka:* Hệ thống retry tối đa 3 lần với exponential backoff. Nếu vẫn thất bại, sự kiện phải được chuyển hướng vào hàng đợi DLQ (Dead-Letter Queue) để đảm bảo không mất mát dữ liệu cấu hình bảo mật và kích hoạt cảnh báo tới quản trị viên.
4.  **Mục tiêu thời gian:** Toàn bộ các dịch vụ downstream bắt buộc phải nhận diện sự kiện, invalidate memory cache và tải lại cấu hình mới từ Redis trong vòng `< 5 giây`. Toàn bộ quá trình đồng bộ chính sách bảo mật sang Keycloak qua Kafka bắt buộc phải hoàn thành dưới `10 giây`.

---

## 4. gRPC Interface & Cơ Chế Dự Phòng (gRPC Fallback)

Microservices nội bộ (như AI Core, CRM, Chatbot) truy vấn cấu hình tốc độ cao thông qua gRPC (port 50053):
*   **Thời gian phản hồi:** Latency trung bình của gRPC GetConfig / GetAllConfig bắt buộc `< 100ms`.
*   **Cơ chế dự phòng (Cache Miss & Tenant Missing):** Khi xảy ra tình huống Cache Miss trên Redis, hoặc khi microservice truy vấn cấu hình của một `tenant_id` không tồn tại trong DB, Tenant Config Service không được phép quăng lỗi làm sập luồng nghiệp vụ của dịch vụ gọi. Hệ thống bắt buộc phải trả về bộ cấu hình mặc định (Default Config) làm dữ liệu fallback an toàn.

---

## 5. Phân Tách Vai Trò Cấu Hợp Đồng & Hạn Mức Gói Cước
*   **Cô lập quyền hạn:** Admin của Tenant chỉ được phép chỉnh sửa các cấu hình nghiệp vụ nội bộ (BYOK API keys, prompts, thresholds, custom roles).
*   **Khóa cấu hình gói cước:** Tenant Admin tuyệt đối không được phép chỉnh sửa hạng gói cước (Subscription Tier) hay các hạn mức thô của hệ thống từ Dashboard.
*   **System Admin Control:** Việc thay đổi gói cước và hạn mức tài nguyên đi kèm (`System Tiers & Limits`) chỉ được thực hiện bởi System Admin thông qua các API an toàn được bảo vệ bởi role `system_admin`.
*   **Đồng bộ tức thời:** Khi System Admin cập nhật hạn mức gói cước, Tenant Config Service cập nhật Redis cache key `tier:{tier_name}:limits` and publish tin hiệu lên `system.limits.updates` để các downstream services áp dụng chính sách Rate Limiting mới trong vòng `< 5 giây`.

---

## 6. Quản Lý Vai Trò Tùy Chỉnh Gián Tiếp Qua Auth Proxy (Phương án A)

Khi Tenant Admin thực hiện cấu hình vai trò (Custom Roles) và phân quyền chi tiết (Permissions):

*   **Không gọi Keycloak trực tiếp:** Để bảo mật admin credentials, Tenant Config Service không được phép tích hợp client credentials của Keycloak. Mọi hành động đồng bộ vai trò lên máy chủ danh tính Keycloak bắt buộc phải được gửi gián tiếp qua **User Service** đóng vai trò là **Auth Proxy**.
*   **Quy trình đồng bộ tạo/xóa vai trò:**
    1.  Tenant Config Service lưu định nghĩa vai trò và danh sách quyền hạn (Permissions) tương ứng vào PostgreSQL (`roles` và `role_permissions`).
    2.  Tenant Config Service tạo request gọi sang REST API của User Service (`POST /api/v1/users/roles` khi tạo hoặc `DELETE /api/v1/users/roles/:name` khi xóa) kèm chữ ký số HMAC-SHA256 ký bằng `GATEWAY_SIGNING_SECRET`.
    3.  User Service verify chữ ký và thực hiện gọi Keycloak Admin API để đồng bộ Organization Role.
*   **Ghi đè cache phân quyền:** Khi danh sách quyền hạn của một vai trò (mặc định hay tùy chỉnh) được cập nhật thành công, Tenant Config Service cập nhật/ghi đè danh sách permissions dạng CSV (bắt buộc phải được sắp xếp theo bảng chữ cái alphabet tăng dần để chuẩn hóa) vào Redis cache key `tenant:{tenant_id}:role:{role_name}:permissions` với TTL dài hạn (30 ngày), đồng thời phát sự kiện invalidation lên kênh Redis Pub/Sub `config.updates` để API Gateway xóa bộ nhớ đệm trong vòng `< 5 giây`.
*   **Ràng buộc bảo vệ vai trò hệ thống:**
    *   Chặn mọi yêu cầu sửa đổi hoặc xóa đối với các vai trò mặc định: `admin`, `manager`, `agent`, `viewer`.
    *   Chặn mọi yêu cầu tạo mới hoặc đổi tên vai trò tùy chỉnh trùng với danh sách từ khóa bảo lưu của hệ thống: `['system', 'system_admin', 'super_admin', 'root']` (không phân biệt hoa thường) để loại trừ nguy cơ leo thang đặc quyền.

---

## Business Logic — Service Self-Registration

### 1. Logic Đăng ký (Startup Hook)
* BƯỚC 1: Gọi hàm `_get_internal_ip()` sử dụng socket UDP giả lập kết nối tới `8.8.8.8:80` để lấy IP nội bộ của container.
* BƯỚC 2: Định nghĩa chuỗi node dạng `{ip}:{port}`.
* BƯỚC 3: Thực hiện pipeline ghi vào Redis:
  * `SADD registry:service:tenant-config "{ip}:{port}"`
  * `SETEX registry:service:tenant-config:node:{ip}:{port} 15 "alive"`
* BƯỚC 4: Bắt đầu chạy vòng lặp heartbeat (mỗi 5 giây) để gửi lại gói tin `SETEX` và `SADD` để làm mới TTL.

### 2. Logic Hủy đăng ký (Shutdown Hook)
* BƯỚC 1: Dừng vòng lặp heartbeat.
* BƯỚC 2: Thực hiện pipeline dọn dẹp Redis:
  * `SREM registry:service:tenant-config "{ip}:{port}"`
  * `DEL registry:service:tenant-config:node:{ip}:{port}"`
