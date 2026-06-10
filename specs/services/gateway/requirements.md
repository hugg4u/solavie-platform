# Requirements — Gateway (Kong)

## Overview
API Gateway tập trung — Kong Gateway OSS. Xử lý SSL termination, rate limiting per-tenant, OIDC token validation với Keycloak, request routing, gRPC proxying.

## Tech Stack
- **Platform:** Kong Gateway OSS 3.x
- **Config:** Declarative (kong.yml) hoặc Admin API
- **Plugins:** OIDC, Rate Limiting, Cors, Request Transformer, Prometheus
- **Database:** PostgreSQL (kong_db) hoặc DB-less mode

## Requirements

### Requirement 1: Request Routing

**User Story:** Là developer, tôi muốn Gateway route requests đến đúng service.

#### Acceptance Criteria
1. THE Gateway SHALL route requests dựa trên URL path prefix đến đúng upstream service
2. THE Gateway SHALL hỗ trợ cả REST (HTTP/JSON) và gRPC proxying
3. THE Gateway SHALL strip path prefix trước khi forward đến upstream
4. THE Gateway SHALL hỗ trợ WebSocket proxying cho Messaging Service
5. THE Gateway SHALL định tuyến tới các service nghiệp vụ (`ai-core`, v.v.) qua các đối tượng Upstream ảo được định nghĩa trong `kong.yml` thay vì trỏ trực tiếp đến tên miền DNS tĩnh.
6. THE Gateway SHALL chạy một luồng nền Registry Sync Daemon để đồng bộ realtime danh sách IP từ Redis vào Kong Upstream targets qua Admin API cục bộ.
7. THE Gateway SHALL áp dụng active/passive health checks cùng cơ chế `retries` (tối thiểu 5 lần) trên Upstream để tự động loại bỏ target chết và tự động thử lại request trên target khác mà không gây ra lỗi cho client.

### Requirement 2: Authentication (OIDC) & Permission Resolution

**User Story:** Là hệ thống, tôi cần validate JWT tokens từ Keycloak, phân giải vai trò thành quyền hạn chi tiết và ký số chuyển tiếp xuống các microservices bảo mật.

#### Acceptance Criteria
1. THE Gateway SHALL validate JWT tokens qua OIDC plugin kết nối Keycloak.
2. WHEN token invalid hoặc expired, THE Gateway SHALL trả về 401 Unauthorized.
3. THE Gateway SHALL trích xuất claims (tenant_id, user_id, roles), tự động phân giải chúng thành danh sách quyền hạn động theo quy chuẩn `{service}:{resource}:{action}` thông qua 3 tầng lookup:
   - **Tầng 1 (L1 Cache - ngx.shared.DICT):** Bộ nhớ đệm dùng chung giữa các worker (shared memory zone `perm_cache`), hết hạn sau 5 phút, tự động giải phóng khi đầy bộ nhớ (LRU eviction).
   - **Tầng 2 (L2 Cache - Redis):** Bộ nhớ đệm phân tán Redis key `tenant:{tenant_id}:role:{role}:permissions`.
   - **Tầng 3 (API Fallback):** Gọi REST API trực tiếp đến Tenant Config Service (`GET /api/v1/config/tenants/{tenant_id}/roles/permissions?roles=role`). Khi thành công, ghi ngược vào L2 Cache (TTL 1 hour) và L1 Cache (TTL 5 mins).
4. THE Gateway SHALL bảo vệ luồng gọi API Fallback (Tầng 3) bằng **Circuit Breaker** độc lập per-service. Nếu Tenant Config Service gặp lỗi hoặc timeout liên tiếp quá 5 lần trong 30 giây, mạch sẽ chuyển sang trạng thái OPEN (Mở) trong 30 giây để từ chối các request fallback tiếp theo (tránh nghẽn Gateway), sử dụng dữ liệu cũ trong L1 Cache (stale cache) hoặc áp dụng cơ chế Fail-Secure.
5. THE Gateway SHALL gộp các quyền của tất cả các vai trò lại (Union Set), tiến hành sắp xếp theo bảng chữ cái (deterministic sorting) để đảm bảo tính nhất quán của chữ ký, và ký số danh sách quyền này bằng thuật toán HMAC-SHA256 trên chuỗi payload `tenant_id:user_id:user_permissions` bằng khóa bí mật chung `GATEWAY_SIGNING_SECRET`.
6. THE Gateway SHALL inject 4 security headers trước khi forward tới downstream services:
   - `X-Tenant-ID`: Tenant ID được lấy từ Organization alias hoặc name đã được xác thực qua JWT.
   - `X-User-ID`: User ID (sub claim).
   - `X-User-Permissions`: Chuỗi CSV các quyền đã được sắp xếp tăng dần.
   - `X-Permissions-Signature`: Chữ ký số HMAC-SHA256 của payload.
7. THE Gateway SHALL tự động gán quyền wildcard `*` cho vai trò `admin` nội bộ của tenant (chỉ có quyền trong phạm vi tenant của họ). Đối với vai trò `system` hoặc `system_admin`, THE Gateway SHALL chỉ tự động gán quyền wildcard `*` và cho phép bypass khi và chỉ khi `tenant_id` trích xuất từ JWT trùng khớp với Master Tenant ID (`solavie-system-master`); nếu vai trò `system` hoặc `system_admin` thuộc vai trò thuộc Organization thông thường, Gateway SHALL từ chối gán wildcard `*` và trả về lỗi `403 Forbidden` để ngăn chặn Privilege Escalation.
8. THE Gateway SHALL áp dụng nguyên tắc **Fail-Secure**: Nếu người dùng có vai trò nhưng hệ thống Gateway không thể kết nối tới cả Redis và API Fallback để phân giải quyền, Gateway SHALL chặn request và trả về lỗi `503 Service Unavailable` thay vì cho qua với quyền mặc định.
9. THE Gateway SHALL whitelist các webhook endpoints (không cần auth) và health check endpoints.
10. THE Gateway SHALL thực hiện thu hồi token tức thời thông qua kiểm tra JTI Blacklist lưu trữ trên Redis cache (sử dụng tiền tố `blacklist:jti:{jti}`), trả về `401 Unauthorized` nếu token nằm trong blacklist.
11. THE Gateway SHALL thực hiện kiểm tra tính hợp lệ của OAuth2 client scopes (Scope Validation) đối với các API request. Khi forward request đến một service nghiệp vụ cụ thể, Gateway phải xác minh Access Token chứa scope được chỉ định của service đó (ví dụ: route `/api/v1/campaigns` yêu cầu scope `campaign`). Nếu thiếu scope hợp lệ, Gateway SHALL từ chối request với mã lỗi `403 Forbidden`.
12. THE Gateway SHALL thực hiện kiểm tra User Blacklist lưu trữ trên Redis cache (sử dụng tiền tố `blacklist:user:{user_id}`) để chặn các người dùng đang bị đình chỉ (Suspended), trả về `401 Unauthorized` nếu user bị khóa.

### Requirement 3: Rate Limiting

**User Story:** Là admin, tôi muốn giới hạn request rate per-tenant.

#### Acceptance Criteria
1. THE Gateway SHALL áp dụng rate limiting per-tenant (dựa trên JWT claim tenant_id)
2. THE Gateway SHALL hỗ trợ configurable limits per-route
3. WHEN rate limit exceeded, THE Gateway SHALL trả về 429 Too Many Requests
4. THE Gateway SHALL dùng Redis backend cho distributed rate limiting
5. THE Gateway SHALL đồng bộ động cấu hình giới hạn tần suất (`gateway_rate_limit_minute`, `gateway_rate_limit_hour`) cho từng tenant từ Redis cache được cập nhật bởi Tenant Config Service

### Requirement 4: SSL & Security

**User Story:** Là DevOps, tôi muốn tất cả traffic được mã hóa.

#### Acceptance Criteria
1. THE Gateway SHALL terminate SSL cho tất cả incoming connections
2. THE Gateway SHALL redirect HTTP → HTTPS
3. THE Gateway SHALL set security headers (HSTS, X-Frame-Options, etc.)
4. THE Gateway SHALL hỗ trợ CORS configuration per-route
5. THE Gateway SHALL cấu hình CORS động (danh sách `allowed_cors_origins`) cho từng tenant từ dữ liệu cache Redis cập nhật bởi Tenant Config Service

### Requirement 5: Observability

**User Story:** Là DevOps, tôi muốn monitor Gateway performance.

#### Acceptance Criteria
1. THE Gateway SHALL expose Prometheus metrics endpoint
2. THE Gateway SHALL log tất cả requests (method, path, status, latency)
3. THE Gateway SHALL propagate trace headers (OpenTelemetry)
4. THE Gateway SHALL cung cấp health check endpoint

### Requirement 6: MCP Route Redirection (Server-Sent Events)

**User Story:** Là hệ thống AI, tôi muốn Gateway định tuyến các kết nối Model Context Protocol (MCP) truyền trực tiếp (Server-Sent Events) tới các microservices nghiệp vụ ổn định, không bị ngắt kết nối giữa chừng.

#### Acceptance Criteria
1. THE Gateway SHALL định tuyến các đường dẫn MCP SSE bao gồm `/api/v1/mcp` tới dịch vụ `crm`, `/api/v1/kb/mcp` tới dịch vụ `knowledge-base`, `/api/v1/messaging/mcp` tới dịch vụ `messaging`, và các đường dẫn tương ứng khác cho cả 7 dịch vụ nghiệp vụ hỗ trợ MCP.
2. THE Gateway SHALL duy trì kết nối persistent cho các requests này, tự động thiết lập thời gian chờ của luồng gửi/nhận (read/write/send timeout) ở mức tối thiểu `60000ms` (60 giây) để tránh tự động ngắt kết nối.
3. THE Gateway SHALL tắt tính năng buffering dữ liệu (bằng cách thiết lập header `X-Accel-Buffering: no` hoặc thông qua cấu hình proxy buffer) để đảm bảo dữ liệu sự kiện (events) được truyền trực tiếp đến client theo thời gian thực (realtime streaming).
4. THE Gateway SHALL kiểm tra đầy đủ token OIDC, rate limiting và inject các security headers (`X-Tenant-ID`, `X-User-ID`, `X-User-Permissions`, `X-Permissions-Signature`) cho các kết nối MCP trước khi chuyển tiếp.

---

## Upstream Dynamic Routing & Gateway Service Discovery Requirements

### Requirement 8: Shared Service Discovery
1. THE Gateway SHALL định tuyến tất cả các request tới các microservices nghiệp vụ nội bộ thông qua các đối tượng Upstream ảo thay vì hostname/port tĩnh.
2. THE Gateway Sync Daemon SHALL quét định kỳ danh sách IP:Port từ các Redis Sets của từng dịch vụ hoạt động để cập nhật danh sách targets của Upstream tương ứng trong cấu hình Kong.
3. THE Gateway Sync Daemon SHALL tự động thực hiện reload cấu hình qua API `/config` của Kong nếu phát hiện sự thay đổi targets.
