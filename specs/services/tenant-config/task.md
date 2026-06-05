# Task Checklist — TENANT-CONFIG Service

## Overview
This document tracks the implementation checklist for **TENANT-CONFIG Service** based on the system specifications.

### Technical Stack & Configuration
- **Language:** Node.js 20
- **Framework:** NestJS
- **Port:** 3006
- **Database:** PostgreSQL
- **Cache:** Redis

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/tenant-config/requirements.md)
- [Design](file:///specs/solavie-system/services/tenant-config/design.md)

---

## Tasks Checklist

### Task 1: 1: REST API CRUD Cấu hình
> *User Story: Là một Tenant Admin, tôi muốn xem và chỉnh sửa cấu hình hệ thống từ Dashboard mà không cần can thiệp kỹ thuật.*

**Acceptance Criteria Implementation:**
- [ ] AC 1.1: THE Tenant_Config SHALL cung cấp REST API GET /config/{category} trả về cấu hình hiện tại của Tenant theo từng nhóm: ai_kb, chat_routing, content_scheduler, crm_campaign, security_comments_notif
- [ ] AC 1.2: THE Tenant_Config SHALL cung cấp REST API PATCH /config/{category} cho phép cập nhật một phần (partial update) cấu hình của nhóm chỉ định; chỉ các field được gửi trong request body mới được cập nhật
- [ ] AC 1.3: THE Tenant_Config SHALL cung cấp REST API GET /config trả về toàn bộ cấu hình của Tenant dưới dạng một JSON object lồng nhau theo 5 nhóm
- [ ] AC 1.4: IF request không có JWT Bearer token hợp lệ, THEN THE Tenant_Config SHALL từ chối và trả về HTTP 401
- [ ] AC 1.5: IF JWT hợp lệ nhưng role không phải Admin, THEN THE Tenant_Config SHALL từ chối PATCH request và trả về HTTP 403; GET request vẫn được phép cho tất cả roles
- [ ] AC 1.6: THE Tenant_Config SHALL áp dụng tenant isolation: mọi API call phải filter theo tenant_id từ JWT claims; từ chối nếu thiếu tenant_id

### Task 2: 2: Validation Schema
> *User Story: Là một Tenant Admin, tôi muốn hệ thống kiểm tra tính hợp lệ của giá trị cấu hình trước khi lưu để tránh cấu hình sai gây lỗi hệ thống.*

**Acceptance Criteria Implementation:**
- [ ] AC 2.1: THE Tenant_Config SHALL validate mọi giá trị cấu hình trước khi lưu vào DB theo schema sau:
- [ ] AC 2.2: confidence_threshold: số thực trong khoảng [0.60, 0.95]
- [ ] AC 2.3: kb_chunk_size: số nguyên trong khoảng [128, 1024]
- [ ] AC 2.4: kb_chunk_overlap_percentage: số thực trong khoảng [5, 30]
- [ ] AC 2.5: rag_relevance_threshold: số thực trong khoảng [0.0, 1.0]
- [ ] AC 2.6: offline_mode_behavior: một trong các giá trị: lead_capture, ai_warning, offline_msg
- [ ] AC 2.7: handoff_routing_algorithm: một trong: round_robin, least_busy, queue_claim, hybrid
- [ ] AC 2.8: manual_to_auto_timeout_hours: số thực trong khoảng [1, 24]
- [ ] AC 2.9: auto_close_timeout_hours: số thực trong khoảng [1, 48]
- [ ] AC 2.10: auto_approve_quality_threshold: số thực trong khoảng [0.0, 1.0]
- [ ] AC 2.11: max_post_retry_attempts: số nguyên trong khoảng [1, 5]
- [ ] AC 2.12: max_daily_posts_per_channel: số nguyên trong khoảng [1, 50]
- [ ] AC 2.13: hot_lead_threshold: số nguyên trong khoảng [0, 100]
- [ ] AC 2.14: contact_auto_merge_threshold: số thực trong khoảng [0.0, 1.0]
- [ ] AC 2.15: session_timeout_minutes: số nguyên trong khoảng [5, 480]
- [ ] AC 2.16: audit_log_retention_days: số nguyên trong khoảng [30, 365]
- [ ] AC 2.17: dms_max_storage_mb: số nguyên trong khoảng [100, 100000]
- [ ] AC 2.18: dms_max_file_versions: số nguyên trong khoảng [1, 20]
- [ ] AC 2.19: campaign_fb_outside_24h_action: một trong: skip, use_tag, paid
- [ ] AC 2.20: gateway_rate_limit_minute: số nguyên trong khoảng [10, 1000]
- [ ] AC 2.21: gateway_rate_limit_hour: số nguyên trong khoảng [100, 50000]
- [ ] AC 2.22: allowed_cors_origins: danh sách chuỗi (array string)
- [ ] AC 2.23: auth_password_min_length: số nguyên trong khoảng [6, 30]
- [ ] AC 2.24: auth_max_login_attempts: số nguyên trong khoảng [3, 20]
- [ ] AC 2.25: mcp_server_whitelist: danh sách các Custom MCP SSE Servers được phê duyệt, chứa server_name, sse_url, status, description, custom_headers
- [ ] AC 2.26: IF bất kỳ giá trị nào không hợp lệ, THEN THE Tenant_Config SHALL từ chối toàn bộ PATCH request và trả về HTTP 422 với danh sách chi tiết các field lỗi và lý do
- [ ] AC 2.26: THE Tenant_Config SHALL validate kiểu dữ liệu: boolean fields phải là true/false, không chấp nhận 0/1 hoặc "true"/"false" dạng string

### Task 3: 3: Hot Reload qua Redis Pub/Sub
> *User Story: Là một Tenant Admin, tôi muốn thay đổi cấu hình có hiệu lực ngay lập tức trên toàn hệ thống mà không cần restart bất kỳ service nào.*

**Acceptance Criteria Implementation:**
- [ ] AC 3.1: WHEN cấu hình được lưu thành công vào DB, THE Tenant_Config SHALL ghi giá trị mới vào Redis cache key `{tenant_id}:config:{category}` và publish event tới Redis channel `config.updates` trong cùng một transaction
- [ ] AC 3.2: THE Tenant_Config SHALL đảm bảo tất cả services đang chạy nhận và áp dụng cấu hình mới trong < 5 giây sau khi Admin lưu thay đổi
- [ ] AC 3.3: THE Tenant_Config SHALL publish event `config.updates` với payload: tenant_id, category, updated_fields (danh sách tên field đã thay đổi), updated_at
- [ ] AC 3.4: IF ghi Redis cache thất bại sau khi lưu DB thành công, THEN THE Tenant_Config SHALL retry ghi Redis tối đa 3 lần với backoff 1s; nếu vẫn thất bại, THE Tenant_Config SHALL log lỗi và trả về HTTP 207 (Multi-Status) chỉ rõ DB đã lưu nhưng cache chưa đồng bộ
- [ ] AC 3.5: IF publish Redis Pub/Sub thất bại, THEN THE Tenant_Config SHALL retry tối đa 3 lần; nếu vẫn thất bại, THE Tenant_Config SHALL log lỗi nhưng vẫn trả về HTTP 200 vì DB đã lưu thành công; services sẽ nhận config mới qua cache miss fallback

### Task 4: 4: gRPC Config Reader
> *User Story: Là một microservice nội bộ, tôi muốn truy vấn cấu hình nhanh qua gRPC khi Redis cache miss để không bị gián đoạn.*

**Acceptance Criteria Implementation:**
- [ ] AC 4.1: THE Tenant_Config SHALL cung cấp gRPC service GetConfig(tenant_id, category) trả về cấu hình của nhóm chỉ định từ DB
- [ ] AC 4.2: THE Tenant_Config SHALL trả về response gRPC trong vòng 100ms cho mọi truy vấn
- [ ] AC 4.3: THE Tenant_Config SHALL xác thực service-to-service calls qua JWT Client Credentials token; từ chối request không có token hợp lệ
- [ ] AC 4.4: THE Tenant_Config SHALL hỗ trợ gRPC GetAllConfig(tenant_id) trả về toàn bộ cấu hình của Tenant trong một lần gọi
- [ ] AC 4.5: IF tenant_id không tồn tại trong DB, THEN THE Tenant_Config SHALL trả về default config thay vì lỗi

### Task 5: 5: Default Config khi Tenant mới
> *User Story: Là một Super Admin, tôi muốn Tenant mới được tạo với bộ cấu hình mặc định hợp lý để có thể sử dụng ngay mà không cần cấu hình thủ công.*

**Acceptance Criteria Implementation:**
- [ ] AC 5.1: WHEN Auth Service publish event tạo Tenant mới, THE Tenant_Config SHALL tự động tạo bản ghi cấu hình mặc định cho Tenant đó với các giá trị:
- [ ] AC 5.2: chatbot_enabled: true
- [ ] AC 5.3: confidence_threshold: 0.70
- [ ] AC 5.4: auto_handoff_on_negative: true
- [ ] AC 5.5: ai_vision_invoice_reading: true
- [ ] AC 5.6: rag_relevance_threshold: 0.50
- [ ] AC 5.7: offline_mode_behavior: lead_capture
- [ ] AC 5.8: handoff_routing_algorithm: hybrid
- [ ] AC 5.9: manual_to_auto_timeout_hours: 2
- [ ] AC 5.10: auto_close_timeout_hours: 24
- [ ] AC 5.11: require_content_approval: true
- [ ] AC 5.12: auto_approve_quality_threshold: 0.85
- [ ] AC 5.13: data_masking_enabled: true
- [ ] AC 5.14: session_timeout_minutes: 60
- [ ] AC 5.15: mcp_server_whitelist: mặc định là mảng rỗng []
- [ ] AC 5.15: audit_log_retention_days: 90
- [ ] AC 5.16: dms_max_storage_mb: 5000
- [ ] AC 5.17: dms_max_file_versions: 5
- [ ] AC 5.18: THE Tenant_Config SHALL hoàn tất tạo default config trong vòng 5 giây sau khi nhận event tạo Tenant mới
- [ ] AC 5.19: IF tạo default config thất bại, THEN THE Tenant_Config SHALL retry tối đa 3 lần và publish event lỗi lên Kafka để Admin được thông báo

### Task 6: 6: Audit Log Thay đổi Cấu hình
> *User Story: Là một Tenant Admin, tôi muốn xem lịch sử thay đổi cấu hình để biết ai đã thay đổi gì và khi nào.*

**Acceptance Criteria Implementation:**
- [ ] AC 6.1: WHEN cấu hình được cập nhật thành công, THE Tenant_Config SHALL ghi audit log với: tenant_id, changed_by (user_id từ JWT), category, field_name, old_value, new_value, changed_at (UTC timestamp)
- [ ] AC 6.2: THE Tenant_Config SHALL cung cấp API GET /config/audit-log trả về lịch sử thay đổi cấu hình của Tenant, sắp xếp theo changed_at giảm dần, phân trang tối đa 50 items/page
- [ ] AC 6.3: THE Tenant_Config SHALL lưu giữ audit log trong số ngày cấu hình bởi audit_log_retention_days (mặc định 90 ngày)
- [ ] AC 6.4: THE Tenant_Config SHALL chạy background job hàng ngày để xóa audit log cũ hơn audit_log_retention_days
- [ ] AC 6.5: THE Tenant_Config SHALL che giá trị nhạy cảm trong audit log (ví dụ: API keys, passwords) bằng cách thay thế bằng `[REDACTED]`

### Task 7: 7: Cấu hình Chatbot & AI (ai_kb)
> *User Story: Là một Tenant Admin, tôi muốn cấu hình linh hoạt hành vi của chatbot AI để phù hợp với nhu cầu kinh doanh của tổ chức.*

**Acceptance Criteria Implementation:**
- [ ] AC 7.1: THE Tenant_Config SHALL cho phép bật/tắt chatbot (chatbot_enabled) để chuyển 100% sang chế độ nhân viên tự chat
- [ ] AC 7.2: THE Tenant_Config SHALL cho phép ghi đè System Prompt của chatbot (chatbot_system_prompt_override) với nội dung tùy chỉnh tối đa 10,000 ký tự
- [ ] AC 7.3: THE Tenant_Config SHALL cho phép cấu hình ngưỡng confidence_threshold trong khoảng [0.60, 0.95] để kiểm soát độ chắc chắn trước khi bot tự động trả lời
- [ ] AC 7.4: THE Tenant_Config SHALL cho phép bật/tắt tính năng đọc hóa đơn bằng AI Vision (ai_vision_invoice_reading)
- [ ] AC 7.5: THE Tenant_Config SHALL cho phép cấu hình model routing (llm_model_routing) dạng JSON map: use_case → model_name
- [ ] AC 7.6: THE Tenant_Config SHALL cho phép cấu hình danh sách fallback models (ai_fallback_models) dạng array string
- [ ] AC 7.7: THE Tenant_Config SHALL quản lý cấu hình các khóa API (API Keys) và API Base URL của các LLM Provider tại trang quản trị tập trung, thực hiện mã hóa đối xứng (AES-256) khóa API trước khi lưu trữ vào DB
- [ ] AC 7.8: THE Tenant_Config SHALL tự động gửi thông báo đồng bộ cấu hình qua kênh Redis Pub/Sub `config.updates` ngay khi Admin lưu thay đổi để AI Core cập nhật
- [ ] Triển khai Encryption Module: Sử dụng `aes-256-gcm` với biến môi trường `ENCRYPTION_KEY` để mã hóa và giải mã API keys trong cấu hình `ai_kb`
- [ ] Triển khai Redis Pub/Sub Publisher Module: Tạo module trong NestJS để phát sự kiện đồng bộ lên kênh `config.updates` mỗi khi lưu/cập nhật cấu hình thành công

### Task 8: 8: Cấu hình Chat Routing & Giờ làm việc (chat_routing)
> *User Story: Là một Tenant Admin, tôi muốn cấu hình giờ làm việc và hành vi ngoài giờ để chatbot hoạt động đúng theo lịch của tổ chức.*

**Acceptance Criteria Implementation:**
- [ ] AC 8.1: THE Tenant_Config SHALL cho phép cấu hình working_hours dạng object: {day_of_week: {start: "HH:MM", end: "HH:MM"}} cho từng ngày trong tuần (0=Chủ nhật, 6=Thứ bảy)
- [ ] AC 8.2: THE Tenant_Config SHALL cho phép cấu hình offline_mode_behavior: lead_capture (thu thập thông tin), ai_warning (cảnh báo ngoài giờ), offline_msg (tin nhắn tĩnh)
- [ ] AC 8.3: THE Tenant_Config SHALL cho phép cấu hình handoff_routing_algorithm: round_robin, least_busy, queue_claim, hoặc hybrid
- [ ] AC 8.4: THE Tenant_Config SHALL cho phép cấu hình manual_to_auto_timeout_hours (1-24 giờ) — thời gian chờ trước khi tự động chuyển từ Manual về Auto
- [ ] AC 8.5: THE Tenant_Config SHALL cho phép cấu hình auto_close_timeout_hours (1-48 giờ) — thời gian không hoạt động trước khi tự động đóng hội thoại

### Task 9: 9: Cấu hình CRM & Bảo mật
> *User Story: Là một Tenant Admin, tôi muốn cấu hình quy tắc lead scoring và bảo mật dữ liệu phù hợp với chính sách của tổ chức.*

**Acceptance Criteria Implementation:**
- [ ] AC 9.1: THE Tenant_Config SHALL cho phép cấu hình lead_scoring_rules dạng JSON dynamic weights: {factor_name: weight_value} để tính điểm tiềm năng khách hàng
- [ ] AC 9.2: THE Tenant_Config SHALL cho phép cấu hình hot_lead_threshold (0-100) — ngưỡng điểm để kích hoạt cảnh báo Hot Lead
- [ ] AC 9.3: THE Tenant_Config SHALL cho phép bật/tắt data_masking_enabled để che thông tin nhạy cảm của khách hàng
- [ ] AC 9.4: THE Tenant_Config SHALL cho phép cấu hình session_timeout_minutes (5-480) — thời gian không hoạt động trước khi tự động đăng xuất
- [ ] AC 9.5: THE Tenant_Config SHALL cho phép cấu hình banned_keywords dạng array string — danh sách từ cấm trong bài viết và chatbot
- [ ] AC 9.6: THE Tenant_Config SHALL cho phép cấu hình giới hạn tốc độ truy cập Gateway (gateway_rate_limit_minute trong khoảng [10, 1000], gateway_rate_limit_hour trong khoảng [100, 50000]) để chống DDOS và kiểm soát hạn mức sử dụng API của từng tenant
- [ ] AC 9.7: THE Tenant_Config SHALL cho phép cấu hình danh sách domain được phép gọi API (allowed_cors_origins dạng array string) để thiết lập CORS an toàn cho chatbot widget
- [ ] AC 9.8: THE Tenant_Config SHALL cho phép cấu hình chính sách bảo mật xác thực (auth_password_min_length trong khoảng [6, 30] và auth_max_login_attempts trong khoảng [3, 20] lần nhập sai trước khi khóa tài khoản) để đồng bộ chính sách bảo mật tài khoản cho Keycloak

### Task 10: 10: Phân tách vai trò cấu hình (System Admin vs Tenant Admin)
> *User Story: Là một System Admin, tôi muốn cấu hình gói cước và gán hạng mức sử dụng cho từng Tenant, đồng thời đảm bảo Admin của các Tenant chỉ có thể chỉnh sửa cấu hình riêng biệt của họ mà không ảnh hưởng đến hạn mức gói.*

**Acceptance Criteria Implementation:**
- [ ] AC 10.1: THE Tenant_Config SHALL KHÔNG cho phép Admin Tenant sửa đổi hạng gói cước (Subscription Tier) hay hạn mức API thô của gói cước từ trang Dashboard của Tenant
- [ ] AC 10.2: THE Tenant_Config/Keycloak DB SHALL lưu trữ hạng gói cước (`free`, `standard`, `enterprise`) của Tenant độc lập và chỉ cho phép System Admin sửa đổi qua trang quản trị hệ thống (System Admin Panel)
- [ ] AC 10.3: WHEN System Admin cập nhật hạng gói của Tenant, sự thay đổi đó SHALL được lưu vào Redis dưới dạng key `tenant:{tenant_id}:tier` để các service downstream thực hiện kiểm tra hạn mức tần suất gọi API (Rate Limiting) ngay lập tức
- [ ] AC 10.4: THE Tenant_Config SHALL cho phép Tenant Admin tự do cấu hình các tham số nội bộ (như API Keys riêng - BYOK, System Prompt riêng, confidence thresholds) thông qua REST API, các thông số này được mã hóa bảo mật và cách ly tuyệt đối giữa các tenant

## Verification & Testing

### Automated Tests
- [ ] Write unit tests verifying core logic of each Requirement (including NestJS config service, validation pipes, and audit log generation).
- [ ] Write unit tests verifying the symmetric Encryption/Decryption utility (AES-256-GCM) with correct key padding.
- [ ] Write integration tests for API endpoints (`/config`, `/config/audit-log`).
- [ ] Verify tenant isolation by querying data across different tenant IDs via gRPC and REST APIs.
- [ ] Verify that sensitive fields are masked as `[REDACTED]` in the audit logs but stored encrypted in the database.

### Manual Verification
- [ ] Deploy service to local Docker / Kubernetes cluster.
- [ ] Perform end-to-end tests using the Gateway (Kong) routing.
- [ ] Test the Redis Pub/Sub event emission on patch requests and confirm event payload format.

## Done When

- [ ] All Acceptance Criteria for Requirements are implemented and verified.
- [ ] Unit test coverage is >80%.
- [ ] Logs are formatted as structured JSON and trace context is propagated.
- [ ] Tenant isolation (RLS / metadata filtering) is strictly enforced.

### Task: Security Integration (MỚI)
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `tenant-config`
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`
