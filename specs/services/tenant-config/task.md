# Task Checklist — TENANT-CONFIG Service

## Overview
Tài liệu này theo dõi tiến độ triển khai và kiểm thử các tính năng của dịch vụ **TENANT-CONFIG Service** theo đặc tả yêu cầu kỹ thuật.

### Technical Stack & Configuration
- **Language:** Node.js 20
- **Framework:** NestJS 10
- **Port:** 3006 (REST) / 50053 (gRPC)
- **Database:** PostgreSQL
- **Cache:** Redis

### Reference Specifications
- [Requirements](file:///d:/workspace/project/solavie-system/specs/services/tenant-config/requirements.md)
- [Design](file:///d:/workspace/project/solavie-system/specs/services/tenant-config/design.md)

---

## Tasks Checklist

### Task 1: REST API CRUD Cấu hình
> *User Story: Là một Tenant Admin, tôi muốn xem và chỉnh sửa cấu hình hệ thống từ Dashboard mà không cần can thiệp kỹ thuật.*
- [ ] AC 1.1: Cung cấp REST API `GET /api/v1/config/:category` trả về cấu hình hiện tại của Tenant theo từng nhóm: `ai_kb`, `chat_routing`, `content_scheduler`, `crm_campaign`, `security_comments_notif`.
- [ ] AC 1.2: Cung cấp REST API `PATCH /api/v1/config/:category` cho phép cập nhật một phần cấu hình (partial update).
- [ ] AC 1.3: Cung cấp REST API `GET /api/v1/config` trả về toàn bộ cấu hình gộp của Tenant dưới dạng một JSON object lồng nhau.
- [ ] AC 1.4: Tích hợp middleware/guard kiểm tra tính hợp lệ của JWT Bearer token, trả về HTTP 401 nếu token không hợp lệ hoặc hết hạn.
- [ ] AC 1.5: Phân quyền API PATCH: Chỉ người dùng có vai trò Admin mới được phép thực thi, trả về HTTP 403 cho các vai trò khác. GET request mở cho tất cả vai trò của tenant.
- [ ] AC 1.6: Áp dụng Tenant Isolation: Trích xuất `tenant_id` từ JWT, cô lập dữ liệu hoàn toàn dựa trên trường này.

### Task 2: Validation Schema
> *User Story: Là một Tenant Admin, tôi muốn hệ thống kiểm tra tính hợp lệ của giá trị cấu hình trước khi lưu.*
- [ ] AC 2.1: Triển khai NestJS `ValidationPipe` với class-validator để kiểm tra kiểu dữ liệu và giá trị biên của cấu hình.
- [ ] AC 2.2: Validate giới hạn của các trường số thực, số nguyên, enum trong 5 categories (ví dụ: `confidence_threshold` trong khoảng `[0.60, 0.95]`, `offline_mode_behavior` thuộc enum hợp lệ, `cost_limit_usd` >= 0.0 hoặc null, `cost_alert_threshold_percent` từ [50, 100], `cost_limit_policy` thuộc enum ['notify_only', 'auto_downgrade', 'block']).
- [ ] AC 2.3: Validate định dạng whitelist Custom MCP SSE Servers (`sse_url` phải có schema http/https hợp lệ, phòng tránh SSRF).
- [ ] AC 2.4: Trả về HTTP 422 kèm danh sách chi tiết các lỗi validation nếu phát hiện giá trị không hợp lệ.
- [ ] AC 2.5: Ràng buộc kiểu Boolean: Kiểm tra strict true/false, không chấp nhận chuỗi `"true"`/`"false"` hoặc số `1`/`0`.

### Task 3: Hot Reload qua Redis Pub/Sub & Kafka
> *User Story: Là một Tenant Admin, tôi muốn thay đổi cấu hình có hiệu lực ngay lập tức trên toàn hệ thống.*
- [ ] AC 3.1: Đồng bộ hóa ghi dữ liệu: Trong cùng một transaction nghiệp vụ, thực hiện ghi giá trị mới vào Redis Cache và gọi Redis client `PUBLISH` lên kênh `config.updates`.
- [ ] AC 3.2: Đảm bảo thời gian lan truyền cấu hình xuống downstream memory của các service khác trong vòng < 5 giây.
- [ ] AC 3.3: Định nghĩa cấu trúc payload của event `config.updates` gồm: `tenant_id`, `category`, `updated_fields`, `updated_at`.
- [ ] AC 3.4: Xử lý lỗi Redis Cache: Retry tối đa 3 lần với backoff 1s; nếu lỗi tiếp diễn, ghi nhận log lỗi hệ thống và trả về HTTP 207 (Multi-Status).
- [ ] AC 3.5: Xử lý lỗi Pub/Sub: Retry tối đa 3 lần; nếu lỗi, ghi nhận hệ thống nhưng vẫn trả về HTTP 200 (vì DB đã lưu thành công).
- [ ] AC 3.6: Đóng vai trò là Kafka Producer phát sự kiện cấu hình bảo mật hoặc vai trò lên Kafka topic `config.updates` khi có thay đổi liên quan đến xác thực/phân quyền (Luồng 3).
- [ ] AC 3.7: Xử lý lỗi phát Kafka: thực hiện retry tối đa 3 lần với exponential backoff và chuyển hướng tin nhắn lỗi sang DLQ nếu thất bại hoàn toàn để tránh mất mát dữ liệu cấu hình bảo mật.

### Task 4: gRPC Config Reader
> *User Story: Là một microservice nội bộ, tôi muốn truy vấn cấu hình nhanh qua gRPC khi Redis cache miss.*
- [ ] AC 4.1: Định nghĩa file protobuf `tenant_config.proto` với dịch vụ `GetConfig` và `GetAllConfig`.
- [ ] AC 4.2: Tối ưu hóa hiệu năng phản hồi gRPC đảm bảo latency trung bình < 100ms.
- [ ] AC 4.3: Triển khai gRPC Interceptor để xác thực cuộc gọi nội bộ (Service-to-Service) qua JWT Client Credentials token.
- [ ] AC 4.4: Trả về bộ cấu hình mặc định (default config) nếu `tenant_id` truy vấn không tồn tại trong DB, tránh quăng lỗi làm sập downstream flow.

### Task 5: Default Config & Default Roles Initialization khi Tenant mới
> *User Story: Là một Super Admin, tôi muốn Tenant mới được tạo với bộ cấu hình và các vai trò mặc định hợp lý.*
- [ ] AC 5.1: Đăng ký lắng nghe sự kiện tạo tenant mới từ hệ thống (qua Kafka/RabbitMQ hoặc nội bộ).
- [ ] AC 5.2: Triển khai luồng tự động ghi bản ghi default config vào PostgreSQL cho tenant mới với các giá trị quy định sẵn (`chatbot_enabled: true`, `confidence_threshold: 0.70`, `cost_limit_usd: null`, `cost_alert_threshold_percent: 80`, `cost_limit_policy: notify_only` ...).
- [ ] AC 5.3: Triển khai luồng gieo mầm (seed) 4 vai trò mặc định (`admin`, `manager`, `agent`, `viewer`) cùng phân quyền mặc định tương ứng vào bảng `roles` và `role_permissions` của PostgreSQL.
- [ ] AC 5.4: Đồng bộ danh sách quyền mặc định của 4 vai trò này lên Redis cache key `tenant:{tenant_id}:role:{role_name}:permissions` (được sắp xếp alphabet tăng dần).
- [ ] AC 5.5: Giới hạn thời gian tạo mặc định hoàn tất trong vòng < 5 giây từ khi nhận sự kiện.
- [ ] AC 5.6: Thiết lập cơ chế retry 3 lần nếu tạo default config hoặc vai trò lỗi, gửi alert tới quản trị viên qua Kafka DLQ hoặc Alertmanager.

### Task 6: Audit Log Thay đổi Cấu hình
> *User Story: Là một Tenant Admin, tôi muốn xem lịch sử thay đổi cấu hình.*
- [ ] AC 6.1: Tự động ghi nhận log thay đổi vào bảng `config_audit_logs` khi có cập nhật cấu hình thành công (lưu rõ user thực hiện, category, trường thay đổi, giá trị cũ/mới).
- [ ] AC 6.2: Cung cấp API `GET /api/v1/config/audit-log` (phân trang tối đa 50 items/page, sắp xếp theo thời gian mới nhất).
- [ ] AC 6.3: Thiết lập background cron job định kỳ chạy hàng ngày để dọn dẹp các log cũ vượt quá hạn định `audit_log_retention_days` của tenant.
- [ ] AC 6.4: Triển khai module che giấu dữ liệu nhạy cảm (`[REDACTED]`) đối với các trường bí mật như API Keys, passwords trước khi ghi vào log DB.

### Task 7: Cấu hình Chatbot & AI (ai_kb)
- [ ] AC 7.1: Cho phép cấu hình các API keys của LLM Providers, thực hiện mã hóa đối xứng AES-256-GCM sử dụng `ENCRYPTION_KEY` trước khi lưu vào DB.
- [ ] AC 7.2: Quản lý whitelist các SSE MCP Server, kiểm tra định dạng và validate an toàn đầu vào cho `sse_url` để chặn tấn công SSRF.
- [ ] AC 7.3: Cho phép cấu hình hạn mức chi phí LLM (`cost_limit_usd`), ngưỡng cảnh báo (`cost_alert_threshold_percent`) và chính sách xử lý (`cost_limit_policy`) trong `ai_kb` category, tự động kích hoạt đồng bộ qua Redis và Pub/Sub.

### Task 8: Cấu hình Chat Routing & Giờ làm việc (chat_routing)
- [ ] AC 8.1: Cho phép cấu hình object `working_hours` kiểm soát khung giờ làm việc chi tiết của từng ngày trong tuần.
- [ ] AC 8.2: Hỗ trợ cấu hình thuật toán định tuyến `handoff_routing_algorithm` và các mức thời gian chờ chuyển trạng thái hội thoại.

### Task 9: Cấu hình CRM, Rate Limits & CORS
- [ ] AC 9.1: Cho phép cấu hình giới hạn tốc độ truy cập Gateway (`gateway_rate_limit_minute`, `gateway_rate_limit_hour`) để kiểm soát lưu lượng.
- [ ] AC 9.2: Cho phép thiết lập danh sách `allowed_cors_origins` để Gateway áp dụng CORS cho chatbot widget của tenant.

### Task 10: Phân tách vai trò cấu hình (System Admin vs Tenant Admin)
- [ ] AC 10.1: Chặn không cho Tenant Admin chỉnh sửa hạng gói cước (Subscription Tier) hay các hạn mức thô của gói.
- [ ] AC 10.2: Đồng bộ hóa sự thay đổi hạng gói từ System Admin Panel vào Redis key `tenant:{tenant_id}:tier` để các service kiểm soát hạn mức tức thì.

### Task 11: REST API Quản lý Gói cước (System Admin Only)
- [ ] AC 11.1: Xây dựng các REST API CRUD `/api/v1/system/tiers` để System Admin cấu hình gói cước động.
- [ ] AC 11.2: Triển khai Guard chặn cuộc gọi API từ các tài khoản không mang role `system_admin`.
- [ ] AC 11.3: Cập nhật Redis cache key `tier:{tier_name}:limits` và publish tin hiệu lên `system.limits.updates` khi lưu thành công vào DB.

### Task 12: Quản lý Vai trò & Quyền hạn (Default & Custom Roles)
- [ ] AC 12.1: Xây dựng REST API `GET /api/v1/config/roles` để lấy danh sách vai trò hiện tại của Tenant (bao gồm cả vai trò mặc định hệ thống và tùy chỉnh).
- [ ] AC 12.2: Xây dựng REST API `POST /api/v1/config/roles` để khởi tạo một Custom Organization Role trên Keycloak bằng cách gọi REST API của **User Service** (Auth Proxy) kèm chữ ký HMAC, đồng thời lưu trữ thông tin phân quyền tương ứng vào PostgreSQL.
- [ ] AC 12.3: Xây dựng REST API `PUT /api/v1/config/roles/:role_name/permissions` để cập nhật danh sách quyền cho vai trò, sắp xếp tăng dần alphabet, ghi đè trực tiếp Redis key `tenant:{tenant_id}:role:{role_name}:permissions` (Long TTL: 30 ngày) và bắn tín hiệu Pub/Sub hủy cache Gateway.
- [ ] AC 12.4: Xây dựng REST API `DELETE /api/v1/config/roles/:role_name` để xóa Custom Organization Role trên Keycloak bằng cách gọi REST API của **User Service** (Auth Proxy) kèm chữ ký HMAC và xóa dữ liệu liên quan ở PostgreSQL.
- [ ] AC 12.5: Triển khai cơ chế bảo vệ chặn các yêu cầu chỉnh sửa hoặc xóa đối với các vai trò mặc định (`admin`, `manager`, `agent`, `viewer`), đồng thời cấm tạo mới hoặc đổi tên vai trò trùng với blacklist bảo lưu (`system`, `system_admin`, `super_admin`, `root`).

### Task 13: Zero-Trust HMAC Guard & Permission Manifest
- [ ] AC 13.1: Phát triển API manifest `GET /api/v1/permissions/manifest` trả về JSON danh sách tài nguyên và quyền dịch vụ này hỗ trợ.
- [ ] AC 13.2: Triển khai NestJS NestGuard thực hiện kiểm tra chữ ký HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET`.
- [ ] AC 13.3: Triển khai module kiểm tra quyền in-memory O(1) dựa trên HTTP Header `X-User-Permissions` hỗ trợ wildcard (`*`, `tenant-config:*`, `tenant-config:{resource}:*`).

---

## Verification & Testing Checklist

### Automated Tests
- [ ] Viết các case unit test cho `HmacVerificationGuard` kiểm thử tính hợp lệ của chữ ký, kiểm tra trường hợp timing attacks và từ chối truy cập khi sai chữ ký.
- [ ] Viết unit test kiểm thử logic gán quyền in-memory O(1) và khả năng phân giải wildcard.
- [ ] Viết integration test cho endpoint quản lý custom roles (`POST /api/v1/config/roles`, `PUT /api/v1/config/roles/:role_name/permissions`) kiểm tra việc đồng bộ sang mô hình DB và ghi đè Redis.
- [ ] Viết test mock cho cuộc gọi đồng bộ Keycloak Admin API để kiểm tra tính toàn vẹn khi API Keycloak trả lỗi.

### Manual Verification
- [ ] Khởi chạy cục bộ docker-compose, thực hiện gọi API qua Gateway để kiểm chứng Gateway inject signature và downstream verify thành công.
- [ ] Kiểm tra Redis CLI xem dữ liệu permissions lưu dưới key `tenant:{tenant_id}:role:{role_name}:permissions` có đúng định dạng CSV phân tách alphabet không.
- [ ] Test trường hợp thay đổi permissions của một custom role và kiểm chứng Gateway invalidate local cache trong < 5 giây.

---

## Service Discovery Client Integration (MỚI)

### Task 21: Service Discovery Client Integration
- [ ] AC 21.1: Triển khai lớp `ServiceRegistryClient` tự động lấy IP nội bộ qua kết nối UDP socket ảo.
- [ ] AC 21.2: Tích hợp `ServiceRegistryClient` vào lifecycle hook khởi động và tắt của ứng dụng (NestJS).
- [ ] AC 21.3: Triển khai cấu trúc JSON logs cho các sự kiện đăng ký và lỗi heartbeat lên Redis.
