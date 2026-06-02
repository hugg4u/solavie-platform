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

### Requirement 2: Authentication (OIDC)

**User Story:** Là hệ thống, tôi cần validate JWT tokens từ Keycloak.

#### Acceptance Criteria
1. THE Gateway SHALL validate JWT tokens qua OIDC plugin kết nối Keycloak
2. WHEN token invalid hoặc expired, THE Gateway SHALL trả về 401 Unauthorized
3. THE Gateway SHALL inject tenant_id và user_id từ token claims vào request headers
4. THE Gateway SHALL whitelist webhook endpoints (không cần auth)
5. THE Gateway SHALL whitelist health check endpoints
6. THE Gateway SHALL thực hiện thu hồi token tức thời thông qua kiểm tra JTI Blacklist lưu trữ trên Redis cache (sử dụng tiền tố `blacklist:jti:{jti}`), trả về `401 Unauthorized` nếu token nằm trong blacklist.

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
