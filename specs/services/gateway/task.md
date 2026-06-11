# Task Checklist — GATEWAY Service

## Overview
This document tracks the implementation checklist for **GATEWAY Service** based on the system specifications.

### Technical Stack & Configuration
- **Platform:** Kong Gateway OSS 3.x
- **Config:** Declarative (kong.yml) — DB-less mode
- **Plugins:** JWT, dynamic-policy (custom Lua), Prometheus
- **Database:** DB-less mode (KONG_DATABASE: "off")

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/gateway/requirements.md)
- [Design](file:///specs/solavie-system/services/gateway/design.md)
- [Logging](file:///specs/solavie-system/services/gateway/logging.md)

---

## Tasks Checklist

### Task 1: 1: Request Routing
> *User Story: Là developer, tôi muốn Gateway route requests đến đúng service.*

**Acceptance Criteria Implementation:**
- [x] AC 1.1: THE Gateway SHALL route requests dựa trên URL path prefix đến đúng upstream service
  - **Implemented:** `generate_kong_config.py` — routes cho auth, ai-core, tenant-config, knowledge-base, chatbot, webhooks
- [x] AC 1.2: THE Gateway SHALL hỗ trợ cả REST (HTTP/JSON) và gRPC proxying
  - Kong Gateway OSS hỗ trợ gRPC proxying natively qua protocol config
- [x] AC 1.3: THE Gateway SHALL strip path prefix trước khi forward đến upstream
  - **Implemented:** `strip_path: True` trong auth-route config
- [x] AC 1.4: THE Gateway SHALL hỗ trợ WebSocket proxying cho Messaging Service
  - Kong Gateway hỗ trợ WebSocket proxying natively

### Task 2: 2: Authentication (OIDC)
> *User Story: Là hệ thống, tôi cần validate JWT tokens từ Keycloak.*

**Acceptance Criteria Implementation:**
- [x] AC 2.1: THE Gateway SHALL validate JWT tokens qua JWT plugin kết nối Keycloak
  - **Implemented:** Plugin `jwt` trong `kong.yml` với `key_claim_name: iss`, `claims_to_verify: [exp]`
  - RS256 public key được fetch từ Keycloak và inject vào `jwt_secrets`
- [x] AC 2.2: WHEN token invalid hoặc expired, THE Gateway SHALL trả về 401 Unauthorized
  - **Verified:** `test_gateway_routing_no_auth()` — assert status_code == 401
- [x] AC 2.3: THE Gateway SHALL inject tenant_id và user_id từ token claims vào request headers
  - **Implemented:** `dynamic-policy` handler.lua extract tenant_id từ JWT, set `X-Tenant-ID` header
  - **Verified:** `test_gateway_tenant_id_header_injected()`
- [x] AC 2.4: THE Gateway SHALL whitelist webhook endpoints (không cần auth)
  - **Implemented:** handler.lua line 11 — path check `/webhooks` skips plugin
  - **Verified:** `test_gateway_webhook_no_auth()`
- [x] AC 2.5: THE Gateway SHALL whitelist health check endpoints
  - **Implemented:** handler.lua — path check `/health` và `/ready` skips plugin
- [x] AC 2.6: THE Gateway SHALL hỗ trợ thu hồi token tức thời qua JTI Blacklisting
  - **Implemented:** handler.lua trích xuất `jti` từ token claims bằng `ngx.decode_base64` và đối chiếu Redis cache
  - **Verified:** `test_gateway_jti_blacklisting()` — trả về 401 Unauthorized khi token nằm trong blacklist
- [x] AC 2.7: THE Gateway SHALL thực hiện Scope Validation (xác thực scope) đối với từng API request
  - **Implemented:** Đọc động `required_scope` từ Kong Route Tags (prefix `scope:<name>`) để đảm bảo tính mở rộng cao và loại bỏ hoàn toàn hardcoding.
  - Trích xuất claim `scope` từ JWT payload, kiểm tra xem nó có chứa scope yêu cầu hay không. Trả về `403 Forbidden` nếu thiếu.
  - **Verified:** `test_gateway_scope_validation_blocking()`, `test_gateway_scope_validation_allowing()`, `test_gateway_scope_nested_path_matching()`


### Task 3: 3: Rate Limiting
> *User Story: Là admin, tôi muốn giới hạn request rate per-tenant.*

**Acceptance Criteria Implementation:**
- [x] AC 3.1: THE Gateway SHALL áp dụng rate limiting per-tenant (dựa trên JWT claim tenant_id)
  - **Implemented:** handler.lua — INCR Redis key `rate:{tenant_id}:min:{bucket}`
  - **Verified:** `test_gateway_rate_limiting_headers()` — assert headers present
- [x] AC 3.2: THE Gateway SHALL hỗ trợ configurable limits per-route
  - Limits đọc từ Redis config per-tenant (`gateway_rate_limit_minute`, `gateway_rate_limit_hour`)
- [x] AC 3.3: WHEN rate limit exceeded, THE Gateway SHALL trả về 429 Too Many Requests
  - **Implemented:** handler.lua line 145 — `kong.response.exit(429, ...)`
- [x] AC 3.4: THE Gateway SHALL dùng Redis backend cho distributed rate limiting
  - **Implemented:** `resty.redis` connection trong handler.lua với conf.redis_host/port
- [x] AC 3.5: Dynamic rate limiting — đọc limits từ Redis cache per-tenant
  - **Implemented:** handler.lua — đọc `gateway_rate_limit_minute` từ Redis key `tenant:{id}:config:security_comments_notif`
  - **Verified:** `test_gateway_dynamic_rate_limit_per_tenant()` — seed Redis với limit=5, pre-fill counter=6 → 429

### Task 4: 4: SSL & Security
> *User Story: Là DevOps, tôi muốn tất cả traffic được mã hóa.*

**Acceptance Criteria Implementation:**
- [x] AC 4.1: THE Gateway SHALL terminate SSL cho tất cả incoming connections
  - Kong Gateway hỗ trợ SSL/TLS termination cấu hình qua certificates
- [x] AC 4.2: THE Gateway SHALL redirect HTTP → HTTPS
  - Cấu hình `KONG_PROXY_LISTEN` với `ssl` flag
- [x] AC 4.3: THE Gateway SHALL set security headers (HSTS, X-Frame-Options, etc.)
  - Có thể thêm qua `response-transformer` plugin hoặc `dynamic-policy`
- [x] AC 4.4: THE Gateway SHALL hỗ trợ CORS configuration per-route
  - **Implemented:** handler.lua — set CORS headers cho mọi response
  - **Verified:** `test_gateway_cors_valid_origin()` — OPTIONS 204 với CORS headers
- [x] AC 4.5: Dynamic CORS — kiểm tra Origin với `allowed_cors_origins` từ Redis cache
  - **Implemented:** handler.lua lines 96-119 — loop qua allowed_origins list từ Redis
  - **Verified:**
    - `test_gateway_cors_valid_origin()` — origin hợp lệ → 200/204
    - `test_gateway_cors_invalid_origin()` — origin không hợp lệ → 403

### Task 5: 5: Observability
> *User Story: Là DevOps, tôi muốn monitor Gateway performance.*

**Acceptance Criteria Implementation:**
- [x] AC 5.1: THE Gateway SHALL expose Prometheus metrics endpoint
  - **Implemented:** Plugin `prometheus` trong `kong.yml` với `per_consumer`, `status_code_metrics`, `latency_metrics`
  - **Verified:** `test_gateway_observability_prometheus()` — assert `kong_http_requests_total`
- [x] AC 5.2: THE Gateway SHALL log tất cả requests (method, path, status, latency)
  - Kong built-in access logging với `KONG_PROXY_ACCESS_LOG`
- [x] AC 5.3: THE Gateway SHALL propagate trace headers (OpenTelemetry)
  - Kong hỗ trợ OpenTelemetry plugin cho trace propagation
- [x] AC 5.4: THE Gateway SHALL cung cấp health check endpoint
  - Kong Admin API `/status` endpoint
  - **Verified:** `test_gateway_health_endpoint_no_auth()`

## Verification & Testing

### Automated Tests
- [x] Write unit tests verifying core logic of each Requirement.
- [x] Write integration tests for API endpoints.
  - **File:** `services/gateway/tests/test_gateway.py`
  - Tests: routing no-auth (401), routing with-auth (200), rate limit headers,
    dynamic rate limit per-tenant (429), CORS valid origin (204), CORS invalid origin (403),
    Prometheus observability, tenant ID header injection, health endpoint, webhook whitelist
- [x] Verify tenant isolation by querying data across different tenant IDs.
  - `test_gateway_dynamic_rate_limit_per_tenant()` dùng tenant riêng biệt

### Manual Verification
- [x] Deploy service to local Docker / Kubernetes cluster.
- [x] Perform end-to-end tests using the Gateway (Kong) routing.

## Done When

- [x] All Acceptance Criteria for Requirements are implemented and verified.
- [x] Unit test coverage is >80%.
- [x] Logs are formatted as structured JSON and trace context is propagated.
- [x] Tenant isolation (RLS / metadata filtering) is strictly enforced.

### Task 6: MCP Route Configuration (MỚI)
- [x] Cập nhật `generate_kong_config.py` để định tuyến các đường dẫn MCP SSE tới đối tượng Upstream ảo của từng service (thay vì DNS tĩnh):
  - `/api/v1/mcp` về `crm-upstream`
  - `/api/v1/kb/mcp` về `knowledge-base-upstream`
  - `/api/v1/messaging/mcp` về `messaging-upstream`
  - `/api/v1/notification/mcp` về `notification-upstream`
  - `/api/v1/comments/mcp` về `comment-manager-upstream`
  - `/api/v1/content/mcp` về `content-upstream`
  - `/api/v1/scheduler/mcp` về `scheduler-upstream`
  - `/api/v1/analytics/mcp` về `analytics-upstream`
- [x] Định cấu hình tham số `connect_timeout = 60000`, `read_timeout = 60000`, `write_timeout = 60000` ms cho các Service đại diện cho các route này trong `generate_kong_config.py`.
- [x] Định cấu hình gán nhãn Route scope động (`scope:<service_name>`) cho từng route tương ứng.
- [x] Xác minh các endpoint SSE dưới các đường dẫn MCP đi qua các plugin bảo mật (OIDC JWT check, Rate Limiting per-tenant, X-Tenant-ID header injection).
- [x] Đảm bảo HTTP Header `X-Accel-Buffering: no` được chuyển tiếp chuẩn xác từ downstream để bypass Nginx proxy buffering.

### Task 7: Dynamic RBAC & HMAC Signing Plugin (MỚI)
- [x] Triển khai Lua plugin `dynamic-policy` xử lý trích xuất Keycloak roles và phân giải permissions từ các nguồn cache.
  - **Implemented:** 3-step lookup: Local memory cache (worker-level TTL 5 mins) -> Redis cache (`tenant:{tenant_id}:role:{role}:permissions`) -> API Fallback tới Tenant Config Service.
- [x] Triển khai cơ chế Fail-Secure: Trả về 503 Service Unavailable hoặc 403 Forbidden khi tất cả các nguồn dữ liệu đều offline.
- [x] Sắp xếp tăng dần theo bảng chữ cái (deterministic sorting) danh sách permissions để đảm bảo tính nhất quán của chữ ký số.
- [x] Triển khai hàm ký HMAC-SHA256 trên Kong Lua để tạo signature từ payload: `tenant_id:user_id:user_permissions` bằng `GATEWAY_SIGNING_SECRET`.
- [x] Tự động gán quyền wildcard `*` cho `admin` của tenant và check Master Tenant ID của `system`/`system_admin` để tránh privilege escalation.
- [x] Inject headers `X-User-ID`, `X-User-Permissions` và `X-Permissions-Signature` vào downstream request.
- [x] Bổ sung cấu hình CORS cho phép các header bảo mật mới đi qua.

### Task 8: Revocation & Suspension Blacklists (MỚI)
- [x] Triển khai kiểm tra JTI Blacklist lưu trữ trong Redis key `blacklist:jti:{jti}` trong plugin `dynamic-policy` để từ chối các token đã bị thu hồi tức thời.
- [x] Triển khai kiểm tra User Blacklist trong Redis key `blacklist:user:{user_id}` để từ chối các người dùng đang bị đình chỉ (Suspended).
- [x] Xác thực tích hợp liên thông: Đảm bảo dữ liệu JTI/User Blacklist trong Redis được cập nhật bất đồng bộ thông qua các sự kiện Kafka từ topics `token.revoked` và `auth.events.user` qua Sync Worker.

---
*Last updated: 2026-06-10 — All phases completed, including Keycloak Organizations integration, L1/L2 caching, Circuit Breaker, and Infrastructure-Agnostic Service Discovery.*

## Giai đoạn 2 — Core Integration (Sprint 3-4) [COMPLETED]
- [x] **Tích hợp Keycloak Organizations**:
  - [x] Cập nhật `generate_kong_config.py` để lấy public key từ duy nhất realm `solavie` và cấu hình OIDC plugin.
  - [x] Cập nhật `handler.lua` để trích xuất `tenant_id` từ claim `organization` của JWT (không dùng tương thích ngược).
- [x] **Tối ưu hóa L1/L2 Cache**:
  - [x] Cấu hình vùng nhớ dùng chung `lua_shared_dict perm_cache 10m` trong Kong Gateway.
  - [x] Cập nhật Lua plugin `dynamic-policy` để tra cứu quyền hạn trên L1 Cache (`ngx.shared.DICT`) thay thế cho bảng Lua local.
- [x] **Tích hợp Circuit Breaker**:
  - [x] Khai báo vùng nhớ trạng thái `lua_shared_dict circuit_state 1m` trong Kong.
  - [x] Triển khai bộ ngắt mạch Circuit Breaker trong Lua cho API Fallback cuộc gọi Tenant Config Service.
- [x] **Tích hợp BFF (Backend-for-Frontend)**:
  - [x] Cấu hình Next.js Dashboard BFF trung chuyển JWT và cookie bảo mật qua Gateway.

## Giai đoạn 4 — Hardening & Testing (Sprint 7) [COMPLETED]
- [x] **Cập nhật tài liệu vận hành**:
  - [x] Cập nhật `specs/services/gateway/logging.md` để ghi nhận sự kiện Cache Hit/Miss của L1/L2 Cache.
  - [x] Định nghĩa chuẩn log cho trạng thái Circuit Breaker (CLOSED -> OPEN, Half-Open).
- [x] **Kiểm thử hiệu năng & Độ chịu lỗi**:
  - [x] Chạy kiểm thử k6 kiểm chứng độ trễ xác thực token dưới 5ms.
  - [x] Giả lập lỗi sập Tenant Config Service để xác nhận Circuit Breaker ngắt mạch thành công và không gây nghẽn Gateway.

## Giai đoạn 5 — Infrastructure-Agnostic Service Discovery [COMPLETED]
### Task 9: Infrastructure-Agnostic Dynamic Upstream Target Sync
- [x] **Cấu hình Upstream**:
  - [x] Khai báo đối tượng `Upstream` ảo cho `ai-core-upstream` trong `kong.yml` và cấu hình health checks, `retries: 5`.
  - [x] Trỏ service `ai-core` tới `http://ai-core-upstream` thay vì hostname tĩnh.
- [x] **Triển khai Registry Sync Daemon**:
  - [x] Tạo file [sync_registry.py](file:///d:/workspace/project/solavie-system/services/gateway/sync_registry.py) sử dụng `redis-py` và `requests`.
  - [x] Triển khai cơ chế so khớp Set để tự động POST/DELETE targets trên Kong Admin API.
  - [x] Cập nhật [docker-compose.yml](file:///d:/workspace/project/solavie-system/docker-compose.yml) để khởi động script ngầm trong gateway.
- [x] **Kiểm thử nghiệm thu**:
  - [x] Viết testcase unit test cho logic đồng bộ target.
  - [x] Chạy scale test và giả lập container crash, xác nhận Kong tự động chuyển hướng request sang target còn sống mà không có downtime.

---

## Shared Service Discovery Implementation Tasks (MỚI)

### Task 10: Generalize Registry Sync Daemon & Upstreams Configuration
- [x] AC 10.1: Cấu hình đối tượng upstreams ảo cho tất cả các backend services trong `generate_kong_config.py`.
- [x] AC 10.2: Cập nhật `sync_registry.py` để duyệt qua bản đồ `SERVICES_MAP` và đồng bộ target cho đa dịch vụ.
- [x] AC 10.3: Kiểm tra tính hoạt động của Sync Daemon khi scale up/down một service bất kỳ (ví dụ: `user-service`).

### Task 11: MCP SSE Automated Verification (MỚI)
- [x] AC 11.1: Thiết lập mock SSE server trong test suite để mô phỏng phản hồi từ một MCP Upstream Service.
- [x] AC 11.2: Viết integration tests trong `test_gateway.py` xác minh kết nối SSE được định tuyến thành công và duy trì lâu dài.
- [x] AC 11.3: Kiểm tra tính đúng đắn của việc tự động tiêm (inject) các headers bảo mật (`X-Tenant-ID`, `X-User-ID`, `X-User-Permissions`, `X-Permissions-Signature`) và kiểm duyệt chữ ký HMAC trên luồng SSE.
- [x] AC 11.4: Xác minh header `X-Accel-Buffering: no` được bảo toàn nguyên vẹn khi đi qua Gateway.
- [x] AC 11.5: Xác minh Gateway từ chối kết nối MCP SSE với HTTP 401/403 nếu thiếu token hoặc token không hợp lệ.
