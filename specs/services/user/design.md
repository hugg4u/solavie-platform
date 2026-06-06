# Design — User Service (Internal Profile)

## Overview
User Service quản lý hồ sơ nghiệp vụ và trạng thái của các nhân viên (Users). Service được thiết kế theo kiến trúc Microservice hướng sự kiện, giao tiếp nội bộ qua gRPC và đồng bộ trạng thái qua event streams.

## Architectural Diagram

```
                 [ Kong API Gateway ]
                         │  (Headers: X-User-Id, X-Tenant-Id)
                         ▼
             [ User Service (NestJS) ] ── (gRPC/REST) ──► [ Other Services ]
               │                 │
      (Read/Write)               │ (Admin API / Webhook)
               ▼                 ▼
     [ PostgreSQL DB ]    [ Keycloak (Auth) ]
    (solavie_user_db)
```

## Data Models

Cơ sở dữ liệu `solavie_user_db` được lưu trữ trên PostgreSQL 16 và áp dụng chính sách Row-Level Security (RLS) để cô lập dữ liệu đa tenant.

### Bảng `users`
Bảng lưu trữ thông tin nghiệp vụ và trạng thái làm việc của nhân viên:

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY, -- Trùng khớp 100% với User UUID trong Keycloak
    tenant_id UUID NOT NULL, -- Định danh doanh nghiệp sở hữu nhân viên
    phone_number VARCHAR(20) DEFAULT NULL,
    avatar_url VARCHAR(255) DEFAULT NULL,
    department VARCHAR(50) DEFAULT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- PENDING, ACTIVE, SUSPENDED
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Bật tính năng Row-Level Security (RLS)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Thiết lập Policy cô lập đa tenant
CREATE POLICY tenant_user_isolation_policy ON users
    USING (tenant_id = current_setting('app.current_tenant_id', true)::UUID);
```

### Bảng `user_preferences`
Bảng lưu trữ cấu hình giao diện cá nhân của nhân viên:

```sql
CREATE TABLE user_preferences (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    theme VARCHAR(20) NOT NULL DEFAULT 'dark',
    language VARCHAR(10) NOT NULL DEFAULT 'vi',
    notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Bật tính năng RLS
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

-- Thiết lập Policy liên kết qua bảng users để kiểm tra tenant_id
CREATE POLICY tenant_pref_isolation_policy ON user_preferences
    USING (user_id IN (SELECT id FROM users WHERE tenant_id = current_setting('app.current_tenant_id', true)::UUID));
```

## REST & gRPC API Endpoints

### 1. REST APIs (Dành cho Dashboard gọi qua Gateway)
* `POST /api/v1/users/invite` (Yêu cầu quyền Admin)
  * Mô tả: Gửi email mời nhân viên tham gia hệ thống và tạo tài khoản tạm thời.
  * Body: `{"email": "employee@tenant.com", "role": "agent", "department": "Marketing"}`
* `GET /api/v1/users/me`
  * Mô tả: Trả về thông tin cá nhân và cấu hình preferences của User hiện tại.
  * Headers: Chứa `X-User-Id` và `X-Tenant-Id`.
* `PUT /api/v1/users/profile`
  * Mô tả: Cập nhật thông tin avatar, số điện thoại của User.
  * Body: `{"phone_number": "0987...", "avatar_url": "https://..."}`
* `PUT /api/v1/users/preferences`
  * Mô tả: Thay đổi cấu hình giao diện (theme, ngôn ngữ).
  * Body: `{"theme": "light", "language": "en"}`

### 2. gRPC Interface (Dành cho giao tiếp nội bộ tốc độ cao)
```protobuf
syntax = "proto3";

package solavie.user.v1;

service UserService {
  rpc GetUserProfile (GetUserProfileRequest) returns (GetUserProfileResponse);
  rpc ValidateUserAccess (ValidateUserAccessRequest) returns (ValidateUserAccessResponse);
}

message GetUserProfileRequest {
  string user_id = 1;
  string tenant_id = 2;
}

message GetUserProfileResponse {
  string user_id = 1;
  string tenant_id = 2;
  string phone_number = 3;
  string avatar_url = 4;
  string department = 5;
  string status = 6;
}

message ValidateUserAccessRequest {
  string user_id = 1;
  string tenant_id = 2;
  string required_role = 3;
}

message ValidateUserAccessResponse {
  bool is_allowed = 1;
}
```

## Key Workflows

### 📨 1. Quy trình Mời và Kích hoạt Tài khoản (Invitation Flow)

```mermaid
sequenceDiagram
    participant Admin as Tenant Admin (Dashboard)
    participant US as User Service (Backend)
    participant KC as Keycloak (Auth)
    participant NS as Notification Service
    participant Emp as Nhân viên mới

    Admin->>US: POST /api/v1/users/invite {"email", "role", "department"}
    Note over US: Tự động trích xuất tenant_id của Admin
    US->>KC: POST /admin/realms/{realm}/users (Tạo user shadow, disabled)
    KC-->>US: Trả về Keycloak User UUID
    US->>US: Lưu UUID vào bảng users với status='PENDING'
    US->>US: Sinh mã kích hoạt dùng 1 lần (TTL 24h)
    US->>NS: Publish Event "user.invited" (Email, Token kích hoạt)
    NS-->>Emp: Gửi Email chứa Link Kích hoạt tài khoản
    Emp->>KC: Click link ➡️ Thiết lập mật khẩu và xác nhận email
    KC->>US: Gọi Webhook / Event "user.verified" (UUID)
    US->>US: Cập nhật status='ACTIVE' trong bảng users
```

### 🔄 2. Quy trình Khóa/Mở khóa tài khoản (User Suspension & Activation)

Để đảm bảo tính nhất quán, hành động khóa hoặc mở khóa tài khoản nhân viên có thể xuất phát từ hai nơi:

#### Luồng A: Thao tác từ Dashboard (Do Admin của Tenant thực hiện - US ➡️ KC)
```mermaid
sequenceDiagram
    participant Admin as Tenant Admin (Dashboard)
    participant US as User Service (Backend)
    participant KC as Keycloak (Auth)
    participant Redis as Redis (token.revoked)

    Admin->>US: POST /api/v1/users/{id}/suspend (hoặc /unsuspend)
    US->>KC: 1. Đặt trạng thái: PUT /users/{id} {"enabled": false}
    US->>KC: 2. Hủy Sessions: POST /users/{id}/logout
    KC-->>US: Xác nhận thành công
    US->>Redis: 3. PUBLISH token.revoked {"jti": "...", "exp": ...}
    US->>US: 4. Cập nhật status='SUSPENDED' ở database Backend
    US-->>Admin: Trả về trạng thái đã cập nhật thành công
```

#### Luồng B: Thao tác từ trang Keycloak Admin Console hoặc do Brute Force (KC ➡️ US)
```mermaid
sequenceDiagram
    participant KC as Keycloak (Auth)
    participant Redis as Redis (auth.user.events)
    participant US as User Service (Backend)

    KC->>KC: Trigger event: user.disabled (hoặc user.enabled)
    KC->>Redis: PUBLISH auth.user.events {"event": "user.disabled", "user_id": "uuid"}
    Redis-->>US: Nhận event
    US->>US: Cập nhật status='SUSPENDED' (hoặc 'ACTIVE') ở database Backend
```

### 🔄 3. Quy trình Cập nhật thông tin Danh tính (Identity Update Flow - US ➡️ KC)

Khi người dùng cập nhật các trường thông tin danh tính cơ bản (Email, Họ, Tên) từ trang cá nhân trên Dashboard:

```mermaid
sequenceDiagram
    participant User as User (Dashboard)
    participant US as User Service (Backend)
    participant KC as Keycloak (Auth)

    User->>US: PUT /api/v1/users/profile {"email": "new@email.com", "first_name": "A", "last_name": "Nguyen"}
    US->>KC: PUT /admin/realms/{realm}/users/{id} {"email": "new@email.com", "firstName": "A", "lastName": "Nguyen"}
    KC-->>US: 204 No Content
    US->>US: Cập nhật database local (nếu cần lưu cache)
    US-->>User: Trả về kết quả cập nhật thành công
```


## Zero-Trust HMAC Guard & Permission Manifest

### 1. Permission Manifest API
`GET /api/v1/permissions/manifest`
Trả về JSON chứa danh sách các tài nguyên và hành động được định nghĩa cho service này:
```json
{
    "service": "user",
    "resources": [
        {
            "name": "users",
            "description": "Tenant workspace users",
            "actions": [
                "create",
                "read",
                "update",
                "delete"
            ]
        }
    ]
}
```

### 2. Zero-Trust HMAC Signature Verification
Dịch vụ kiểm tra và xác thực chữ ký signature trên mỗi request tại lớp Guard/Interceptor của Spring Boot (Java):
1. Trích xuất `X-Tenant-ID`, `X-User-ID`, `X-User-Permissions` và `X-Permissions-Signature` từ headers.
2. Tính toán signature mong đợi:
   `expected_sig = HMAC_SHA256(GATEWAY_SIGNING_SECRET, X-Tenant-ID + ":" + X-User-ID + ":" + X-User-Permissions)`
3. So sánh `X-Permissions-Signature` với `expected_sig`. Nếu không khớp, trả về ngay lập tức mã lỗi `403 Forbidden` (Signature Mismatch).
4. So khớp in-memory O(1): parse `X-User-Permissions` thành một Set và đối chiếu với quyền yêu cầu của endpoint (ví dụ: `user:users:create`).
   - Hỗ trợ wildcard: `*` (Super Admin bypass), `user:*` (Service bypass), và `user:users:*` (Resource bypass).
