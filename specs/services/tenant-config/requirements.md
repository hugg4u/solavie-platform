# Requirements Document

## Introduction

Dịch vụ quản lý tập trung toàn bộ cấu hình hệ thống của Solavie Marketing Platform. Cung cấp REST API CRUD cho Dashboard, hot-reload qua Redis Pub/Sub để tất cả services nhận cấu hình mới trong < 5 giây mà không cần restart, và gRPC interface cho services truy vấn nhanh khi cache miss.

## Tech Stack
- **Language:** Node.js 20
- **Framework:** NestJS
- **Port:** 3006
- **Database:** PostgreSQL (config_db)
- **Cache:** Redis (hot-reload pub/sub, config cache)

## Glossary
- **Tenant_Config**: Service này — quản lý tập trung cấu hình hệ thống
- **Hot Reload**: Cơ chế đồng bộ cấu hình mới xuống tất cả services đang chạy trong < 5 giây mà không cần restart
- **Config Category**: Nhóm cấu hình: ai_kb, chat_routing, content_scheduler, crm_campaign, security_comments_notif
- **Default Config**: Bộ cấu hình mặc định được áp dụng khi Tenant mới được tạo
- **Audit Log**: Bản ghi thay đổi cấu hình: ai thay đổi, giá trị cũ/mới, timestamp

## Requirements

### Requirement 1: REST API CRUD Cấu hình

**User Story:** Là một Tenant Admin, tôi muốn xem và chỉnh sửa cấu hình hệ thống từ Dashboard mà không cần can thiệp kỹ thuật.

#### Acceptance Criteria
1. THE Tenant_Config SHALL cung cấp REST API GET /config/{category} trả về cấu hình hiện tại của Tenant theo từng nhóm: ai_kb, chat_routing, content_scheduler, crm_campaign, security_comments_notif
2. THE Tenant_Config SHALL cung cấp REST API PATCH /config/{category} cho phép cập nhật một phần (partial update) cấu hình của nhóm chỉ định; chỉ các field được gửi trong request body mới được cập nhật
3. THE Tenant_Config SHALL cung cấp REST API GET /config trả về toàn bộ cấu hình của Tenant dưới dạng một JSON object lồng nhau theo 5 nhóm
4. IF request không có JWT Bearer token hợp lệ, THEN THE Tenant_Config SHALL từ chối và trả về HTTP 401
5. IF JWT hợp lệ nhưng role không phải Admin, THEN THE Tenant_Config SHALL từ chối PATCH request và trả về HTTP 403; GET request vẫn được phép cho tất cả roles
6. THE Tenant_Config SHALL áp dụng tenant isolation: mọi API call phải filter theo tenant_id từ JWT claims; từ chối nếu thiếu tenant_id

### Requirement 2: Validation Schema

**User Story:** Là một Tenant Admin, tôi muốn hệ thống kiểm tra tính hợp lệ của giá trị cấu hình trước khi lưu để tránh cấu hình sai gây lỗi hệ thống.

#### Acceptance Criteria
1. THE Tenant_Config SHALL validate mọi giá trị cấu hình trước khi lưu vào DB theo schema sau:
   - confidence_threshold: số thực trong khoảng [0.60, 0.95]
   - kb_chunk_size: số nguyên trong khoảng [128, 1024]
   - kb_chunk_overlap_percentage: số thực trong khoảng [5, 30]
   - rag_relevance_threshold: số thực trong khoảng [0.0, 1.0]
   - offline_mode_behavior: một trong các giá trị: lead_capture, ai_warning, offline_msg
   - handoff_routing_algorithm: một trong: round_robin, least_busy, queue_claim, hybrid
   - manual_to_auto_timeout_hours: số thực trong khoảng [1, 24]
   - auto_close_timeout_hours: số thực trong khoảng [1, 48]
   - auto_approve_quality_threshold: số thực trong khoảng [0.0, 1.0]
   - max_post_retry_attempts: số nguyên trong khoảng [1, 5]
   - max_daily_posts_per_channel: số nguyên trong khoảng [1, 50]
   - hot_lead_threshold: số nguyên trong khoảng [0, 100]
   - contact_auto_merge_threshold: số thực trong khoảng [0.0, 1.0]
   - session_timeout_minutes: số nguyên trong khoảng [5, 480]
   - audit_log_retention_days: số nguyên trong khoảng [30, 365]
   - dms_max_storage_mb: số nguyên trong khoảng [100, 100000]
   - dms_max_file_versions: số nguyên trong khoảng [1, 20]
   - campaign_fb_outside_24h_action: một trong: skip, use_tag, paid
   - gateway_rate_limit_minute: số nguyên trong khoảng [10, 1000]
   - gateway_rate_limit_hour: số nguyên trong khoảng [100, 50000]
   - allowed_cors_origins: danh sách chuỗi (array string) đại diện cho các origin được phép gọi API
   - auth_password_min_length: số nguyên trong khoảng [6, 30]
   - auth_max_login_attempts: số nguyên trong khoảng [3, 20]
2. IF bất kỳ giá trị nào không hợp lệ, THEN THE Tenant_Config SHALL từ chối toàn bộ PATCH request và trả về HTTP 422 với danh sách chi tiết các field lỗi và lý do
3. THE Tenant_Config SHALL validate kiểu dữ liệu: boolean fields phải là true/false, không chấp nhận 0/1 hoặc "true"/"false" dạng string

### Requirement 3: Hot Reload qua Redis Pub/Sub

**User Story:** Là một Tenant Admin, tôi muốn thay đổi cấu hình có hiệu lực ngay lập tức trên toàn hệ thống mà không cần restart bất kỳ service nào.

#### Acceptance Criteria
1. WHEN cấu hình được lưu thành công vào DB, THE Tenant_Config SHALL ghi giá trị mới vào Redis cache key `{tenant_id}:config:{category}` và publish event tới Redis channel `config.updates` trong cùng một transaction
2. THE Tenant_Config SHALL đảm bảo tất cả services đang chạy nhận và áp dụng cấu hình mới trong < 5 giây sau khi Admin lưu thay đổi
3. THE Tenant_Config SHALL publish event `config.updates` với payload: tenant_id, category, updated_fields (danh sách tên field đã thay đổi), updated_at
4. IF ghi Redis cache thất bại sau khi lưu DB thành công, THEN THE Tenant_Config SHALL retry ghi Redis tối đa 3 lần với backoff 1s; nếu vẫn thất bại, THE Tenant_Config SHALL log lỗi và trả về HTTP 207 (Multi-Status) chỉ rõ DB đã lưu nhưng cache chưa đồng bộ
5. IF publish Redis Pub/Sub thất bại, THEN THE Tenant_Config SHALL retry tối đa 3 lần; nếu vẫn thất bại, THE Tenant_Config SHALL log lỗi nhưng vẫn trả về HTTP 200 vì DB đã lưu thành công; services sẽ nhận config mới qua cache miss fallback

### Requirement 4: gRPC Config Reader

**User Story:** Là một microservice nội bộ, tôi muốn truy vấn cấu hình nhanh qua gRPC khi Redis cache miss để không bị gián đoạn.

#### Acceptance Criteria
1. THE Tenant_Config SHALL cung cấp gRPC service GetConfig(tenant_id, category) trả về cấu hình của nhóm chỉ định từ DB
2. THE Tenant_Config SHALL trả về response gRPC trong vòng 100ms cho mọi truy vấn
3. THE Tenant_Config SHALL xác thực service-to-service calls qua JWT Client Credentials token; từ chối request không có token hợp lệ
4. THE Tenant_Config SHALL hỗ trợ gRPC GetAllConfig(tenant_id) trả về toàn bộ cấu hình của Tenant trong một lần gọi
5. IF tenant_id không tồn tại trong DB, THEN THE Tenant_Config SHALL trả về default config thay vì lỗi

### Requirement 5: Default Config khi Tenant mới

**User Story:** Là một Super Admin, tôi muốn Tenant mới được tạo với bộ cấu hình mặc định hợp lý để có thể sử dụng ngay mà không cần cấu hình thủ công.

#### Acceptance Criteria
1. WHEN Auth Service publish event tạo Tenant mới, THE Tenant_Config SHALL tự động tạo bản ghi cấu hình mặc định cho Tenant đó với các giá trị:
   - chatbot_enabled: true
   - confidence_threshold: 0.70
   - auto_handoff_on_negative: true
   - ai_vision_invoice_reading: true
   - rag_relevance_threshold: 0.50
   - offline_mode_behavior: lead_capture
   - handoff_routing_algorithm: hybrid
   - manual_to_auto_timeout_hours: 2
   - auto_close_timeout_hours: 24
   - require_content_approval: true
   - auto_approve_quality_threshold: 0.85
   - data_masking_enabled: true
   - session_timeout_minutes: 60
   - audit_log_retention_days: 90
   - dms_max_storage_mb: 5000
   - dms_max_file_versions: 5
2. THE Tenant_Config SHALL hoàn tất tạo default config trong vòng 5 giây sau khi nhận event tạo Tenant mới
3. IF tạo default config thất bại, THEN THE Tenant_Config SHALL retry tối đa 3 lần và publish event lỗi lên Kafka để Admin được thông báo

### Requirement 6: Audit Log Thay đổi Cấu hình

**User Story:** Là một Tenant Admin, tôi muốn xem lịch sử thay đổi cấu hình để biết ai đã thay đổi gì và khi nào.

#### Acceptance Criteria
1. WHEN cấu hình được cập nhật thành công, THE Tenant_Config SHALL ghi audit log với: tenant_id, changed_by (user_id từ JWT), category, field_name, old_value, new_value, changed_at (UTC timestamp)
2. THE Tenant_Config SHALL cung cấp API GET /config/audit-log trả về lịch sử thay đổi cấu hình của Tenant, sắp xếp theo changed_at giảm dần, phân trang tối đa 50 items/page
3. THE Tenant_Config SHALL lưu giữ audit log trong số ngày cấu hình bởi audit_log_retention_days (mặc định 90 ngày)
4. THE Tenant_Config SHALL chạy background job hàng ngày để xóa audit log cũ hơn audit_log_retention_days
5. THE Tenant_Config SHALL che giá trị nhạy cảm trong audit log (ví dụ: API keys, passwords) bằng cách thay thế bằng `[REDACTED]`

### Requirement 7: Cấu hình Chatbot & AI (ai_kb)

**User Story:** Là một Tenant Admin, tôi muốn cấu hình linh hoạt hành vi của chatbot AI để phù hợp với nhu cầu kinh doanh của tổ chức.

#### Acceptance Criteria
1. THE Tenant_Config SHALL cho phép bật/tắt chatbot (chatbot_enabled) để chuyển 100% sang chế độ nhân viên tự chat
2. THE Tenant_Config SHALL cho phép ghi đè System Prompt của chatbot (chatbot_system_prompt_override) với nội dung tùy chỉnh tối đa 10,000 ký tự
3. THE Tenant_Config SHALL cho phép cấu hình ngưỡng confidence_threshold trong khoảng [0.60, 0.95] để kiểm soát độ chắc chắn trước khi bot tự động trả lời
4. THE Tenant_Config SHALL cho phép bật/tắt tính năng đọc hóa đơn bằng AI Vision (ai_vision_invoice_reading)
5. THE Tenant_Config SHALL cho phép cấu hình model routing (llm_model_routing) dạng JSON map: use_case → model_name
6. THE Tenant_Config SHALL cho phép cấu hình danh sách fallback models (ai_fallback_models) dạng array string
7. THE Tenant_Config SHALL quản lý cấu hình các khóa API (API Keys) và API Base URL của các LLM Provider (OpenAI, Anthropic, DeepSeek, vLLM/Ollama local) tại trang quản trị tập trung, thực hiện mã hóa đối xứng (AES-256) khóa API trước khi lưu trữ vào cơ sở dữ liệu `config_db`.
8. THE Tenant_Config SHALL tự động gửi thông báo đồng bộ cấu hình qua kênh Redis Pub/Sub `config.updates` ngay khi Admin lưu thay đổi để AI Core cập nhật.
9. THE Tenant_Config SHALL quản lý cấu hình danh sách các Custom MCP SSE Servers được phê duyệt (mcp_server_whitelist) dưới dạng danh sách JSON objects. Mỗi MCP Server trong danh sách chứa: server_name, sse_url, status (active/inactive), description, và danh sách custom_headers (để xác thực/giao tiếp an toàn).
10. THE Tenant_Config SHALL validate định dạng sse_url của các Custom MCP Servers (bắt buộc bắt đầu bằng http:// hoặc https:// và kết thúc bằng /mcp hoặc tương tự), đồng thời chặn các ký tự lạ để phòng tránh SSRF và Command Injection.

### Requirement 8: Cấu hình Chat Routing & Giờ làm việc (chat_routing)

**User Story:** Là một Tenant Admin, tôi muốn cấu hình giờ làm việc và hành vi ngoài giờ để chatbot hoạt động đúng theo lịch của tổ chức.

#### Acceptance Criteria
1. THE Tenant_Config SHALL cho phép cấu hình working_hours dạng object: {day_of_week: {start: "HH:MM", end: "HH:MM"}} cho từng ngày trong tuần (0=Chủ nhật, 6=Thứ bảy)
2. THE Tenant_Config SHALL cho phép cấu hình offline_mode_behavior: lead_capture (thu thập thông tin), ai_warning (cảnh báo ngoài giờ), offline_msg (tin nhắn tĩnh)
3. THE Tenant_Config SHALL cho phép cấu hình handoff_routing_algorithm: round_robin, least_busy, queue_claim, hoặc hybrid
4. THE Tenant_Config SHALL cho phép cấu hình manual_to_auto_timeout_hours (1-24 giờ) — thời gian chờ trước khi tự động chuyển từ Manual về Auto
5. THE Tenant_Config SHALL cho phép cấu hình auto_close_timeout_hours (1-48 giờ) — thời gian không hoạt động trước khi tự động đóng hội thoại

### Requirement 9: Cấu hình CRM & Bảo mật

**User Story:** Là một Tenant Admin, tôi muốn cấu hình quy tắc lead scoring và bảo mật dữ liệu phù hợp với chính sách của tổ chức.

#### Acceptance Criteria
1. THE Tenant_Config SHALL cho phép cấu hình lead_scoring_rules dạng JSON dynamic weights: {factor_name: weight_value} để tính điểm tiềm năng khách hàng
2. THE Tenant_Config SHALL cho phép cấu hình hot_lead_threshold (0-100) — ngưỡng điểm để kích hoạt cảnh báo Hot Lead
3. THE Tenant_Config SHALL cho phép bật/tắt data_masking_enabled để che thông tin nhạy cảm của khách hàng
4. THE Tenant_Config SHALL cho phép cấu hình session_timeout_minutes (5-480) — thời gian không hoạt động trước khi tự động đăng xuất
5. THE Tenant_Config SHALL cho phép cấu hình banned_keywords dạng array string — danh sách từ cấm trong bài viết và chatbot
6. THE Tenant_Config SHALL cho phép cấu hình giới hạn tốc độ truy cập Gateway (gateway_rate_limit_minute trong khoảng [10, 1000], gateway_rate_limit_hour trong khoảng [100, 50000]) để chống DDOS và kiểm soát hạn mức sử dụng API của từng tenant
7. THE Tenant_Config SHALL cho phép cấu hình danh sách domain được phép gọi API (allowed_cors_origins dạng array string) để thiết lập CORS an toàn cho chatbot widget
8. THE Tenant_Config SHALL cho phép cấu hình chính sách bảo mật xác thực (auth_password_min_length trong khoảng [6, 30] và auth_max_login_attempts trong khoảng [3, 20] lần nhập sai trước khi khóa tài khoản) để đồng bộ chính sách bảo mật tài khoản cho Keycloak

### Requirement 10: Phân tách vai trò cấu hình (System Admin vs Tenant Admin)

**User Story:** Là một System Admin, tôi muốn cấu hình gói cước và gán hạng mức sử dụng cho từng Tenant, đồng thời đảm bảo Admin của các Tenant chỉ có thể chỉnh sửa cấu hình riêng biệt của họ mà không ảnh hưởng đến hạn mức gói.

#### Acceptance Criteria
1. THE Tenant_Config SHALL KHÔNG cho phép Admin Tenant sửa đổi hạng gói cước (Subscription Tier) hay hạn mức API thô của gói cước từ trang Dashboard của Tenant.
2. THE Tenant_Config/Keycloak DB SHALL lưu trữ hạng gói cước (`free`, `standard`, `enterprise`) của Tenant độc lập và chỉ cho phép System Admin sửa đổi qua trang quản trị hệ thống (System Admin Panel).
3. WHEN System Admin cập nhật hạng gói của Tenant, sự thay đổi đó SHALL được lưu vào Redis dưới dạng key `tenant:{tenant_id}:tier` để các service downstream thực hiện kiểm tra hạn mức tần suất gọi API (Rate Limiting) ngay lập tức.
4. THE Tenant_Config SHALL cho phép Tenant Admin tự do cấu hình các tham số nội bộ (như API Keys riêng - BYOK, System Prompt riêng, confidence thresholds) thông qua REST API, các thông số này được mã hóa bảo mật và cách ly tuyệt đối giữa các tenant.

### Requirement 11: REST API Quản lý Gói cước và Hạn mức (System Admin Only)

**User Story:** Là một System Admin, tôi muốn cấu hình động các gói cước và hạn mức tài nguyên đi kèm từ hệ thống để thay đổi chính sách kinh doanh SaaS mà không cần thay đổi mã nguồn.

#### Acceptance Criteria
1. THE Tenant_Config SHALL cung cấp các REST API cho System Admin để thực hiện CRUD các gói cước và hạn mức:
   - `GET /api/v1/system/tiers`: Xem danh sách tất cả các gói cước và hạn mức tài nguyên đang được định nghĩa.
   - `POST /api/v1/system/tiers`: Khởi tạo một hạng gói cước mới hoặc cập nhật hạn mức của gói cước hiện tại.
   - `DELETE /api/v1/system/tiers/:tier`: Xóa một hạng gói cước (chỉ cho phép nếu không còn tenant nào sử dụng).
2. IF request không mang JWT token hợp lệ của System Admin (role `system_admin`), THEN THE Tenant_Config SHALL từ chối và trả về HTTP 403.
3. WHEN hạn mức gói cước (Tier Limits) được lưu thành công vào DB, THE Tenant_Config SHALL cập nhật Redis cache key `tier:{tier_name}:limits` và publish một thông điệp thông báo lên kênh Redis Pub/Sub `system.limits.updates`.
4. THE Tenant_Config SHALL đảm bảo các microservices liên quan tự động lắng nghe kênh `system.limits.updates` và tải lại hạn mức cước mới vào bộ nhớ trong vòng < 5 giây.


### Requirement: Zero-Trust Access Control & Permission Manifest

**User Story:** Là Tenant Admin, tôi muốn xem danh sách quyền hạn mà dịch vụ `tenant-config` hỗ trợ để thiết lập vai trò tùy chỉnh trên Dashboard và đảm bảo bảo mật Zero-Trust downstream.

#### Acceptance Criteria
1. THE TENANT_CONFIG_Service SHALL cung cấp API manifest tại `GET /api/v1/permissions/manifest` trả về danh sách tài nguyên (resources) và hành động (actions) được hỗ trợ.
2. THE TENANT_CONFIG_Service SHALL thực hiện kiểm tra chữ ký số HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET` để xác thực request được gửi trực tiếp từ API Gateway tin cậy.
3. THE TENANT_CONFIG_Service SHALL thực hiện kiểm tra quyền in-memory O(1) dựa trên HTTP Header `X-User-Permissions` truyền từ Gateway. Định dạng quyền của dịch vụ tuân theo cấu trúc `tenant-config:{resource}:{action}` hỗ trợ ký tự đại diện `*` (Super Admin), `tenant-config:*` (Toàn quyền trên service), và `tenant-config:{resource}:*` (Toàn quyền trên tài nguyên).

## Security & Access Control
- **Authentication & Authorization:** APIs của Tenant Config Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `tenant-config`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Tenant Config Service.
- **Tenant Isolation:** Dữ liệu Tenant Config **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.

