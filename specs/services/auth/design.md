# Design — Auth Service (Keycloak)

## Overview

Dịch vụ xác thực và phân quyền tập trung — Keycloak 24+, Java (Quarkus), Port 8080, PostgreSQL (keycloak_db). Cung cấp OAuth2 Authorization Code Flow cho Dashboard, Client Credentials cho service-to-service, Multi-realm per tenant, Dynamic RBAC, Automated Tenant Provisioning, và JWT token với claims tenant_id/user_id/roles.

## Components and Interfaces

Xem **Architecture**, **Realm Structure**, và **Key Endpoints** bên dưới.

## Data Models

Keycloak quản lý data nội bộ trong `keycloak_db` (PostgreSQL). Không có custom tables — tất cả user, role, realm data được quản lý bởi Keycloak schema. Xem **Realm Structure** và **JWT Token Structure** bên dưới.
| Component | Technology |
|-----------|-----------|
| Platform | Keycloak 24+ |
| Runtime | Java (Quarkus-based) |
| Database | PostgreSQL 16 (keycloak_db) |
| Port | 8080 (HTTP), 8443 (HTTPS) |
| Admin Console | /admin |
| Mode | Production (optimized, metrics enabled) |

## Architecture

```mermaid
graph TB
    subgraph "Keycloak"
        OIDC["OIDC Endpoints"]
        ADMIN["Admin Console"]
        REALMS["Realm Manager"]
        USERS["User Store"]
        TOKENS["Token Service"]
    end

    subgraph "Clients"
        DASH["Dashboard (Next.js)"]
        KONG["Kong Gateway (OIDC plugin)"]
        SERVICES["Backend Services (token validation)"]
    end

    subgraph "Storage"
        PG["PostgreSQL (keycloak_db)"]
    end

    DASH -->|Authorization Code Flow| OIDC
    KONG -->|Token Introspection / JWKS| OIDC
    SERVICES -->|JWKS validation| OIDC
    ADMIN -->|Manage realms, users, roles| REALMS & USERS
    TOKENS --> PG
    USERS --> PG
    REALMS --> PG
```

## Realm Structure

```
Keycloak Instance
├── master realm (platform admin only)
│   └── Users: [platform-admin]
│
├── tenant-{uuid} realm
│   ├── Clients:
│   │   ├── dashboard (public, Authorization Code + PKCE)
│   │   └── api-gateway (confidential, for Kong OIDC)
│   │
│   ├── Realm Roles:
│   │   ├── admin
│   │   ├── manager
│   │   ├── agent
│   │   └── viewer
│   │
│   ├── Users:
│   │   ├── user-1 (roles: [admin])
│   │   ├── user-2 (roles: [manager])
│   │   └── user-3 (roles: [agent])
│   │
│   ├── Token Settings:
│   │   ├── Access Token Lifespan: 15 minutes
│   │   ├── Refresh Token Lifespan: 30 days
│   │   └── SSO Session Idle: 30 minutes
│   │
│   └── Security:
│       ├── Brute Force Detection: enabled (Dynamic: auth_max_login_attempts failures → 5 min lockout)
│       ├── Password Policy: minLength(auth_password_min_length), upperCase(1), digit(1), specialChars(1) (Dynamic from Tenant Config)
│       └── Required Actions: [VERIFY_EMAIL, UPDATE_PASSWORD]
│
└── tenant-{uuid-2} realm
    └── ... (same structure)
```

## JWT Token Structure

```json
{
  "iss": "http://keycloak:8080/realms/tenant-abc",
  "sub": "user-uuid-123",
  "aud": "dashboard",
  "exp": 1700000900,
  "iat": 1700000000,
  "azp": "dashboard",
  "realm_access": {
    "roles": ["manager"]
  },
  "tenant_id": "tenant-abc-uuid",
  "email": "user@company.com",
  "name": "Nguyen Van A",
  "preferred_username": "nguyenvana"
}
```

## Key Endpoints (per realm)

```
# OIDC Discovery
GET  /realms/{realm}/.well-known/openid-configuration

# Token
POST /realms/{realm}/protocol/openid-connect/token
     - grant_type=authorization_code (login)
     - grant_type=refresh_token (refresh)

# User Info
GET  /realms/{realm}/protocol/openid-connect/userinfo

# JWKS (for token verification)
GET  /realms/{realm}/protocol/openid-connect/certs

# Logout
POST /realms/{realm}/protocol/openid-connect/logout

# Admin API (master realm admin only)
GET    /admin/realms                    — List realms
POST   /admin/realms                    — Create realm
GET    /admin/realms/{realm}/users      — List users
POST   /admin/realms/{realm}/users      — Create user
PUT    /admin/realms/{realm}/users/{id} — Update user
DELETE /admin/realms/{realm}/users/{id} — Delete user
```

## Tenant Onboarding Flow

```mermaid
sequenceDiagram
    PlatformAdmin->>Keycloak: POST /admin/realms (create tenant realm)
    Keycloak-->>PlatformAdmin: Realm created
    PlatformAdmin->>Keycloak: Create clients (dashboard, api-gateway)
    PlatformAdmin->>Keycloak: Create roles (admin, manager, agent, viewer)
    PlatformAdmin->>Keycloak: Fetch initial config from Tenant Config Service
    PlatformAdmin->>Keycloak: Set initial password policy & brute force limit
    PlatformAdmin->>Keycloak: Create first admin user
    Keycloak-->>User: Email invitation (set password)
    User->>Keycloak: Set password + login
    Keycloak-->>User: JWT token (tenant_id in claims)
```

## Docker Compose

```yaml
keycloak:
  image: quay.io/keycloak/keycloak:24.0
  command: start --optimized
  environment:
    KC_DB: postgres
    KC_DB_URL: jdbc:postgresql://postgres-keycloak:5432/keycloak_db
    KC_DB_USERNAME: keycloak
    KC_DB_PASSWORD: ${KC_DB_PASSWORD}
    KC_HOSTNAME: auth.yourdomain.com
    KC_PROXY: edge  # behind Kong/Nginx
    KC_METRICS_ENABLED: true
    KC_HEALTH_ENABLED: true
    KEYCLOAK_ADMIN: admin
    KEYCLOAK_ADMIN_PASSWORD: ${KC_ADMIN_PASSWORD}
  ports:
    - "8080:8080"
  depends_on:
    - postgres-keycloak

postgres-keycloak:
  image: postgres:16
  environment:
    POSTGRES_DB: keycloak_db
    POSTGRES_USER: keycloak
    POSTGRES_PASSWORD: ${KC_DB_PASSWORD}
  volumes:
    - keycloak_data:/var/lib/postgresql/data
```

## Security Hardening

| Setting | Value | Reason |
|---------|-------|--------|
| Token signing | RS256 | Asymmetric, services verify without secret |
| Access token TTL | 15 min | Minimize exposure window |
| Refresh token TTL | 30 days | UX balance |
| Brute force | Dynamic: auth_max_login_attempts failures | Prevent credential stuffing (Sync from Tenant Config) |
| Password policy | Dynamic: auth_password_min_length+ chars, complexity | Industry standard (Sync from Tenant Config) |
| CORS | Restricted to dashboard domain | Prevent CSRF |
| Admin console | IP-restricted in production | Prevent unauthorized access |
| PKCE | Enforced `S256` for client `dashboard` | Prevent Authorization Code interception on public clients |
| Refresh Token Rotation | Enabled (`revokeRefreshToken=true`, `refreshTokenMaxReuse=0`) | Prevent replay attacks of compromised refresh tokens |
| OTP Policy | Default TOTP (HmacSHA1, 6 digits, 30s period) | Enforce multi-factor authentication (MFA) |
| JTI Blacklisting | Gateway-level verification check via Redis | Immediate token revocation capability (< 1ms lookup) |
| Sync Reliability | Redis Streams with Consumer Groups | Ensure 100% delivery of security config changes |

## Dynamic Security Config Synchronization Flow

Khi Tenant thay đổi cấu hình bảo mật (`auth_password_min_length`, `auth_max_login_attempts`) tại Tenant Config Service, quá trình đồng bộ qua **Dual-Publishing** (Redis Pub/Sub & Redis Streams) diễn ra như sau:

```mermaid
sequenceDiagram
    participant Admin as Tenant Admin
    participant TCS as Tenant Config Service
    participant Redis as Redis (Streams & Pub/Sub)
    participant AuthWorker as Auth Sync Worker
    participant KC as Keycloak Admin API

    Admin->>TCS: PATCH /api/v1/config/security_comments_notif
    TCS->>TCS: Save to config_db
    TCS->>Redis: XADD config.updates.stream * data (JSON config update)
    TCS->>Redis: PUBLISH config.updates (fallback event)
    Note over Redis, AuthWorker: Worker reads updates reliably from Stream Consumer Group
    Redis-->>AuthWorker: XREADGROUP config.updates.stream (worker-1)
    AuthWorker->>KC: PUT /admin/realms/{tenant_id} (update password policy & failureFactor)
    KC-->>AuthWorker: 204 No Content
    AuthWorker->>Redis: XACK config.updates.stream auth-sync-group {message_id}
    AuthWorker->>AuthWorker: Log successful sync
```

## Token Revocation & JTI Blacklisting Flow

Khi người dùng thực hiện đăng xuất (logout) hoặc token bị thu hồi, hệ thống chặn đứng request tại Gateway qua cơ chế:

```mermaid
sequenceDiagram
    participant User as User / Admin
    participant Auth as Keycloak
    participant Redis as Redis Pub/Sub (token.revoked)
    participant Worker as Auth Sync Worker
    participant Cache as Redis Cache (Blacklist)
    participant GW as Kong API Gateway
    
    User->>Auth: POST /protocol/openid-connect/logout
    Auth->>Auth: Invalidate User Session
    Auth->>Redis: PUBLISH token.revoked (jti, exp)
    Redis-->>Worker: Deliver revocation event
    Worker->>Cache: SETEX blacklist:jti:{jti} TTL=(exp - now) "revoked"
    Worker->>Worker: Log JTI blacklisted successfully
    
    Note over User, GW: Khi User cố gắng gửi request mang token cũ qua Gateway
    User->>GW: GET /api/v1/documents (Bearer Token)
    GW->>GW: Parse JWT Claims & Extract `jti` via ngx.decode_base64
    GW->>Cache: GET blacklist:jti:{jti}
    Cache-->>GW: Return "revoked"
    GW-->>User: HTTP 401 Unauthorized {"message": "Token has been revoked"}
```

Chi tiết gọi Keycloak Admin API để đồng bộ:
- **Endpoint:** `PUT /admin/realms/{realm_name}`
- **Headers:** `Authorization: Bearer <admin_token>`
- **Payload:**
```json
{
  "passwordPolicy": "length(auth_password_min_length) and upperCase(1) and digits(1) and specialChars(1)",
  "bruteForceProtected": true,
  "permanentLockout": false,
  "failureFactor": auth_max_login_attempts
}
```

## Monitoring

- `GET /health/ready` — Readiness probe
- `GET /health/live` — Liveness probe
- `GET /metrics` — Prometheus metrics (login count, token issued, failures)


## Correctness Properties

### Property 1: Tenant Isolation
**Validates: Requirements 4.1**
Moi query va operation phai filter theo tenant_id tu JWT claims. Khong co cross-tenant data leakage o bat ky tang nao (DB, Kafka, Redis, Qdrant, MinIO).

### Property 2: Idempotency
**Validates: Requirements 3.1**
Moi write operation phai co idempotency key de tranh duplicate processing khi retry. Kafka consumer phai idempotent.

### Property 3: At-least-once Delivery
**Validates: Requirements 3.1**
Kafka events phai duoc xu ly it nhat mot lan. Sau 3 retries voi exponential backoff (1s, 2s, 4s), event chuyen vao dead-letter queue.

### Property 4: Circuit Breaker Correctness
**Validates: Requirements 5.1**
Sync calls toi external services phai qua circuit breaker. Open sau 5 failures trong 30s, Half-Open probe sau 60s.

### Property 5: Data Consistency
**Validates: Requirements 3.1**
Distributed transactions dung Saga pattern voi compensating actions khi rollback. Moi destructive action ghi audit.events Kafka topic.
## Error Handling

| Scenario | Strategy |
|----------|----------|
| External API timeout | Retry t?i da 3 l?n v?i exponential backoff (1s, 2s, 4s); sau d� tr? v? l?i c� c?u tr�c |
| Database connection error | Circuit breaker + fallback response; alert qua Alertmanager |
| Kafka publish failure | Retry 3 l?n; n?u v?n th?t b?i ghi v�o dead-letter queue |
| Invalid tenant_id | Reject ngay v?i HTTP 403 + ghi security warning v�o audit log |
| Validation error | Tr? v? HTTP 422 v?i danh s�ch field errors chi ti?t |
| Unhandled exception | Log structured JSON v?i trace_id; tr? v? HTTP 500 v?i error_id d? debug |

## Testing Strategy

| Layer | Tool | Coverage Target |
|-------|------|----------------|
| Unit Tests | Jest (Node.js) / pytest (Python) / JUnit 5 (Java) | > 80% business logic |
| Integration Tests | Testcontainers (PostgreSQL, Redis, Kafka) | Happy path + error paths |
| Contract Tests | Pact (consumer-driven) cho gRPC interfaces | Chatbot?AI Core, Messaging?Chatbot |
| Property-Based Tests | fast-check (JS) / Hypothesis (Python) | Tenant isolation, idempotency |
| Load Tests | k6 | Chatbot E2E < 2s t?i 100 concurrent users |
