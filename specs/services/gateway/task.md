# Task Checklist — GATEWAY Service

## Overview
This document tracks the implementation checklist for **GATEWAY Service** based on the system specifications.

### Technical Stack & Configuration
- **Platform:** Kong Gateway OSS 3.x
- **Config:** Declarative (kong.yml) hoặc Admin API
- **Plugins:** OIDC, Rate Limiting, Cors, Request Transformer, Prometheus
- **Database:** PostgreSQL (kong_db) hoặc DB-less mode

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/gateway/requirements.md)
- [Design](file:///specs/solavie-system/services/gateway/design.md)
- [Logging](file:///specs/solavie-system/services/gateway/logging.md)

---

## Tasks Checklist

### Task 1: 1: Request Routing
> *User Story: Là developer, tôi muốn Gateway route requests đến đúng service.*

**Acceptance Criteria Implementation:**
- [ ] AC 1.1: THE Gateway SHALL route requests dựa trên URL path prefix đến đúng upstream service
- [ ] AC 1.2: THE Gateway SHALL hỗ trợ cả REST (HTTP/JSON) và gRPC proxying
- [ ] AC 1.3: THE Gateway SHALL strip path prefix trước khi forward đến upstream
- [ ] AC 1.4: THE Gateway SHALL hỗ trợ WebSocket proxying cho Messaging Service

### Task 2: 2: Authentication (OIDC)
> *User Story: Là hệ thống, tôi cần validate JWT tokens từ Keycloak.*

**Acceptance Criteria Implementation:**
- [ ] AC 2.1: THE Gateway SHALL validate JWT tokens qua OIDC plugin kết nối Keycloak
- [ ] AC 2.2: WHEN token invalid hoặc expired, THE Gateway SHALL trả về 401 Unauthorized
- [ ] AC 2.3: THE Gateway SHALL inject tenant_id và user_id từ token claims vào request headers
- [ ] AC 2.4: THE Gateway SHALL whitelist webhook endpoints (không cần auth)
- [ ] AC 2.5: THE Gateway SHALL whitelist health check endpoints

### Task 3: 3: Rate Limiting
> *User Story: Là admin, tôi muốn giới hạn request rate per-tenant.*

**Acceptance Criteria Implementation:**
- [ ] AC 3.1: THE Gateway SHALL áp dụng rate limiting per-tenant (dựa trên JWT claim tenant_id)
- [ ] AC 3.2: THE Gateway SHALL hỗ trợ configurable limits per-route
- [ ] AC 3.3: WHEN rate limit exceeded, THE Gateway SHALL trả về 429 Too Many Requests
- [ ] AC 3.4: THE Gateway SHALL dùng Redis backend cho distributed rate limiting
- [ ] AC 3.5: Cấu hình / Lập trình cơ chế dynamic rate limiting, đọc giới hạn tần suất (`gateway_rate_limit_minute`, `gateway_rate_limit_hour`) của từng tenant từ Redis cache
- [ ] Viết integration test mô phỏng gửi request vượt quá rate limit động của tenant và kiểm chứng mã trả về là 429

### Task 4: 4: SSL & Security
> *User Story: Là DevOps, tôi muốn tất cả traffic được mã hóa.*

**Acceptance Criteria Implementation:**
- [ ] AC 4.1: THE Gateway SHALL terminate SSL cho tất cả incoming connections
- [ ] AC 4.2: THE Gateway SHALL redirect HTTP → HTTPS
- [ ] AC 4.3: THE Gateway SHALL set security headers (HSTS, X-Frame-Options, etc.)
- [ ] AC 4.4: THE Gateway SHALL hỗ trợ CORS configuration per-route
- [ ] AC 4.5: Cấu hình / Lập trình cơ chế dynamic CORS, kiểm tra Origin header của request với danh sách `allowed_cors_origins` của tenant tương ứng trong Redis cache
- [ ] Viết integration test kiểm tra CORS với Origin hợp lệ và không hợp lệ dựa theo cấu hình động của từng tenant

### Task 5: 5: Observability
> *User Story: Là DevOps, tôi muốn monitor Gateway performance.*

**Acceptance Criteria Implementation:**
- [ ] AC 5.1: THE Gateway SHALL expose Prometheus metrics endpoint
- [ ] AC 5.2: THE Gateway SHALL log tất cả requests (method, path, status, latency)
- [ ] AC 5.3: THE Gateway SHALL propagate trace headers (OpenTelemetry)
- [ ] AC 5.4: THE Gateway SHALL cung cấp health check endpoint

## Verification & Testing

### Automated Tests
- [ ] Write unit tests verifying core logic of each Requirement.
- [ ] Write integration tests for API endpoints.
- [ ] Verify tenant isolation by querying data across different tenant IDs.

### Manual Verification
- [ ] Deploy service to local Docker / Kubernetes cluster.
- [ ] Perform end-to-end tests using the Gateway (Kong) routing.

## Done When

- [ ] All Acceptance Criteria for Requirements are implemented and verified.
- [ ] Unit test coverage is >80%.
- [ ] Logs are formatted as structured JSON and trace context is propagated.
- [ ] Tenant isolation (RLS / metadata filtering) is strictly enforced.
