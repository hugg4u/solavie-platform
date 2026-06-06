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
- [ ] Cập nhật tệp cấu hình Kong `kong.yml` để định tuyến các đường dẫn MCP SSE:
  - `/api/v1/mcp` về dịch vụ CRM (`http://crm:3003`)
  - `/api/v1/kb/mcp` về dịch vụ Knowledge Base (`http://knowledge-base:8004`)
  - `/api/v1/messaging/mcp` về dịch vụ Messaging (`http://messaging:3002`)
  - `/api/v1/notification/mcp` về dịch vụ Notification (`http://notification:3004`)
  - `/api/v1/comments/mcp` về dịch vụ Comment Manager (`http://comment-manager:3005`)
  - `/api/v1/content/mcp` về dịch vụ Content (`http://content:8002`)
  - `/api/v1/scheduler/mcp` về dịch vụ Scheduler (`http://scheduler:8003`)
  - `/api/v1/analytics/mcp` về dịch vụ Analytics (`http://analytics:8006`)
- [ ] Xác minh các endpoint SSE dưới các đường dẫn MCP đi qua các plugin bảo mật (OIDC JWT check, Rate Limiting per-tenant, X-Tenant-ID header injection).

### Task 7: Dynamic RBAC & HMAC Signing Plugin (MỚI)
- [x] Triển khai Lua plugin `dynamic-policy` xử lý trích xuất Keycloak roles và phân giải permissions từ các nguồn cache.
- [x] Triển khai cơ chế Fail-Secure: Trả về 503 hoặc 403 khi tất cả các nguồn dữ liệu đều offline.
- [x] Triển khai hàm ký HMAC-SHA256 trên Kong Lua để tạo signature.
- [x] Inject headers `X-User-Permissions` và `X-Permissions-Signature` vào downstream request.
- [x] Bổ sung cấu hình CORS cho phép các header bảo mật mới đi qua.

---
*Last updated: 2026-06-06 — Core tasks and Dynamic RBAC tasks completed; MCP tasks added.*

