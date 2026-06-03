# Production Readiness & Architecture Migration Guide

Tài liệu này ghi nhận các quyết định kiến trúc và hướng dẫn chuyển đổi hệ thống **Solavie Marketing Platform** từ phiên bản thử nghiệm (Local Dev / MVP) sang phiên bản sản phẩm thực tế (**Production-ready SaaS**).

---

## 1. Nâng cấp API Gateway (Kong Gateway)

### Hiện trạng (Local Dev)
*   **Chế độ:** DB-less mode (không dùng Database).
*   **Cơ chế:** Đọc cấu hình tĩnh từ tệp `kong.yml` được sinh tự động bởi container `solavie-init-gateway` mỗi khi khởi chạy.
*   **Hạn chế:** Mỗi khi thêm/bớt Realm (Tenant mới), bắt buộc phải chạy lại script sinh cấu hình và restart Kong Gateway. Điều này gây gián đoạn kết nối của toàn bộ khách hàng trên Production.

### Định hướng Production
Hoàng tử và đội ngũ phát triển cần triển khai một trong hai phương án sau:

#### Phương án A: Chuyển sang DB Mode (Khuyến nghị)
1.  **Dựng Database riêng cho Kong**: Dùng một instance PostgreSQL (hoặc một schema riêng `kong_db`) để lưu trữ cấu hình động của Kong.
2.  **Quản trị qua REST Admin API**: Khi có Tenant mới đăng ký (Onboarding):
    *   Hệ thống Provisioning Service sẽ gọi HTTP POST trực tiếp tới cổng Admin API của Kong (`:8001`) để đăng ký các Services, Routes và JWT Credential (nhúng Public Key của Realm mới) tương ứng.
    *   **Ưu điểm**: Mọi thay đổi cấu hình có hiệu lực tức thời, không cần reload hay restart Gateway, đảm bảo tính liên tục của hệ thống (High Availability).

#### Phương án B: Sử dụng Dynamic OIDC/JWT Discovery Plugin
1.  **Cấu hình Plugin**: Thay thế plugin `jwt` tĩnh bằng plugin hỗ trợ OIDC dynamic discovery (ví dụ: `kong-oidc` hoặc viết custom Lua plugin).
2.  **Cơ chế hoạt động**:
    *   Khi nhận JWT Token từ Client, plugin sẽ giải mã header của token để lấy thuộc tính `iss` (Issuer URL, ví dụ: `https://auth.solavie.com/realms/tenant-uuid`).
    *   Plugin tự động gửi request HTTP GET tới OIDC Discovery Endpoint của Realm đó: `https://auth.solavie.com/realms/tenant-uuid/.well-known/openid-configuration` để lấy danh sách Public Keys (JWKS URI) về.
    *   **Caching**: Lưu trữ các Public Keys này vào bộ nhớ cache (in-memory hoặc Redis) với TTL phù hợp để tránh việc gọi Keycloak liên tục cho mỗi request.
    *   **Ưu điểm**: Hoàn toàn tự động, Gateway tự phục hồi và tự nạp key mới của bất kỳ Realm nào mà không cần đăng ký trước thông qua Admin API.

---

## 2. Quy hoạch Dịch vụ Người dùng (User Service vs HRM)

### Hiện trạng (Local Dev)
*   `user-service` quản lý hồ sơ nghiệp vụ của nhân viên (Hybrid Profile) phục vụ cho nền tảng Marketing.

### Định hướng Production
*   **Tuyệt đối không gộp chung nghiệp vụ nhân sự chuyên sâu (HRM)** vào `user-service`.
*   **Kiến trúc đề xuất**:
    *   **`user-service`**: Giữ vai trò là dịch vụ IAM Core tinh gọn (quản lý Name, Avatar, Roles, Status hoạt động và bộ tùy chọn Preferences).
    *   **`hrm-service`**: Xây dựng thành một Microservice hoàn toàn độc lập, sở hữu cơ sở dữ liệu riêng để quản lý thông tin chấm công, lương thưởng (payroll), hợp đồng lao động, KPIs bảo mật.
    *   **Liên kết**: Hai dịch vụ liên kết với nhau lỏng lẻo thông qua mã **User UUID** (`sub` claim từ Keycloak). Khi `user-service` có sự kiện thay đổi trạng thái user (như khóa/mở khóa), nó sẽ publish sự kiện qua Redis Stream / Kafka để `hrm-service` cập nhật trạng thái tương ứng.

---

## 3. Đồng bộ cấu hình qua Event Streaming tin cậy

### Hiện trạng (Local Dev)
*   Sử dụng Redis Pub/Sub và Redis Streams đơn giản trên 1 node Redis duy nhất.

### Định hướng Production
1.  **Hạ tầng truyền tin**: Chuyển đổi từ Redis đơn lẻ sang cụm **Apache Kafka** hoặc **Redis Sentinel / Cluster** để đảm bảo không bị mất mát sự kiện (Eventual Consistency) khi chịu tải cao.
2.  **Đảm bảo Idempotency**: Thiết lập cơ chế nhận tin và xử lý sự kiện trùng lặp (Idempotent Consumer) tại các Worker để đề phòng trường hợp mạng chập chờn khiến một sự kiện bị gửi nhiều lần.
