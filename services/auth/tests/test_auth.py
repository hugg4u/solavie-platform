import os
import subprocess
import sys
import json
import base64
import time
import uuid
import pytest
import requests

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8081")
ADMIN_USER = os.getenv("KC_ADMIN", "admin")
ADMIN_PASSWORD = os.getenv("KC_ADMIN_PASSWORD", "admin_secret_pass")

TEST_TENANT_ID = f"tenant-test-{uuid.uuid4()}"
TEST_TENANT_NAME = f"Test Tenant Company {uuid.uuid4().hex[:8]}"
TEST_ADMIN_EMAIL = f"admin@{uuid.uuid4().hex[:8]}.com"
TEST_ADMIN_PASSWORD = "SolavieSecurePass123!"

# --- Helper roles for RBAC tests ---
ROLES_TO_TEST = ["Admin", "Manager", "Agent", "Viewer"]

def get_redis_client():
    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", 6379))
    try:
        from redis.cluster import RedisCluster
        r = RedisCluster(host=host, port=port, decode_responses=True)
        r.ping()
        return r
    except Exception as e:
        print(f"RedisCluster connection failed: {e}. Falling back to standalone Redis client.")
        import redis
        r = redis.Redis(host=host, port=port, decode_responses=True)
        r.ping()
        return r

def decode_jwt_payload(token):
    parts = token.split('.')
    if len(parts) != 3:
        raise ValueError("Invalid JWT token format")
    payload_b64 = parts[1]
    payload_b64 += '=' * (-len(payload_b64) % 4)
    payload_json = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
    return json.loads(payload_json)

@pytest.fixture(scope="session", autouse=True)
def provision_tenant():
    # Run the provisioning script
    script_path = os.path.join(os.path.dirname(__file__), "../scripts/provision_organization.py")
    cmd = [
        sys.executable, script_path,
        "--keycloak-url", KEYCLOAK_URL,
        "--admin-username", ADMIN_USER,
        "--admin-password", ADMIN_PASSWORD,
        "--tenant-id", TEST_TENANT_ID,
        "--tenant-name", TEST_TENANT_NAME,
        "--admin-email", TEST_ADMIN_EMAIL,
        "--admin-password-user", TEST_ADMIN_PASSWORD
    ]
    
    print(f"Running provisioning CLI script command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Provisioning failed: {result.stderr}"
    
    # Extract provision output
    output_lines = result.stdout.split('\n')
    json_lines = []
    capture = False
    for line in output_lines:
        if line.strip() == "PROVISION_OUTPUT_START":
            capture = True
            continue
        if line.strip() == "PROVISION_OUTPUT_END":
            capture = False
            continue
        if capture:
            json_lines.append(line)
            
    assert json_lines, "Could not find PROVISION_OUTPUT block in provisioning script output"
    provision_data = json.loads('\n'.join(json_lines))
    return provision_data

def test_oidc_discovery(provision_tenant):
    # Requirement 1.4: OIDC discovery endpoint per realm
    discovery_url = f"{KEYCLOAK_URL}/realms/solavie/.well-known/openid-configuration"
    response = requests.get(discovery_url, timeout=10)
    assert response.status_code == 200
    data = response.json()
    
    # Basic OIDC assertions
    # Keycloak returns the issuer based on KC_HOSTNAME config which may not include the port.
    # We verify the realm suffix is correct rather than exact URL match.
    assert data["issuer"].endswith("/realms/solavie")
    assert "authorization_endpoint" in data
    assert "token_endpoint" in data
    assert "jwks_uri" in data
    assert "userinfo_endpoint" in data
    assert "end_session_endpoint" in data

def test_oauth2_password_grant(provision_tenant):
    # Simulate obtaining a token using Direct Access Grants (direct login check)
    token_url = f"{KEYCLOAK_URL}/realms/solavie/protocol/openid-connect/token"
    payload = {
        "client_id": "dashboard",
        "username": f"admin-{TEST_TENANT_ID}",
        "password": TEST_ADMIN_PASSWORD,
        "grant_type": "password",
        "scope": "openid email profile organization"
    }
    
    response = requests.post(token_url, data=payload, timeout=10)
    assert response.status_code == 200
    token_data = response.json()
    
    # Requirement 1.2 & 1.3: Access token and refresh token issued
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"].lower() == "bearer"
    
    # Decode and verify JWT claims
    # Requirement 1.5: JWT claims shall include sub, tenant_id, roles, email, name
    access_token = token_data["access_token"]
    claims = decode_jwt_payload(access_token)
    
    assert "sub" in claims
    assert TEST_TENANT_ID in claims.get("organization", [])
    assert "Admin" in claims.get("roles", [])
    assert claims.get("email") == TEST_ADMIN_EMAIL
    
    # Check default password policy lockout and complexity settings
    # Test session idle / lifetime settings
    assert token_data.get("expires_in") <= 900  # Access token lifespan: 15 min (900 seconds)

def test_token_refresh(provision_tenant):
    # Authenticate first
    token_url = f"{KEYCLOAK_URL}/realms/solavie/protocol/openid-connect/token"
    payload = {
        "client_id": "dashboard",
        "username": f"admin-{TEST_TENANT_ID}",
        "password": TEST_ADMIN_PASSWORD,
        "grant_type": "password",
        "scope": "openid email profile organization"
    }
    response = requests.post(token_url, data=payload, timeout=10)
    assert response.status_code == 200
    token_data = response.json()
    refresh_token = token_data["refresh_token"]
    
    # Refresh
    refresh_payload = {
        "client_id": "dashboard",
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    
    # Wait a second to ensure iat is different if needed
    time.sleep(1)
    
    refresh_response = requests.post(token_url, data=refresh_payload, timeout=10)
    assert refresh_response.status_code == 200
    refreshed_data = refresh_response.json()
    
    assert "access_token" in refreshed_data
    assert "refresh_token" in refreshed_data
    
    # Verify new token claims
    claims = decode_jwt_payload(refreshed_data["access_token"])
    assert TEST_TENANT_ID in claims.get("organization", [])
    assert "Admin" in claims.get("roles", [])

def test_token_revocation_logout(provision_tenant):
    # Authenticate
    token_url = f"{KEYCLOAK_URL}/realms/solavie/protocol/openid-connect/token"
    payload = {
        "client_id": "dashboard",
        "username": f"admin-{TEST_TENANT_ID}",
        "password": TEST_ADMIN_PASSWORD,
        "grant_type": "password",
        "scope": "openid email profile organization"
    }
    response = requests.post(token_url, data=payload, timeout=10)
    assert response.status_code == 200
    token_data = response.json()
    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]
    
    # User info verification before logout
    userinfo_url = f"{KEYCLOAK_URL}/realms/solavie/protocol/openid-connect/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    userinfo_response = requests.get(userinfo_url, headers=headers, timeout=10)
    assert userinfo_response.status_code == 200
    
    # Perform Logout
    logout_url = f"{KEYCLOAK_URL}/realms/solavie/protocol/openid-connect/logout"
    logout_payload = {
        "client_id": "dashboard",
        "refresh_token": refresh_token
    }
    logout_response = requests.post(logout_url, data=logout_payload, timeout=10)
    # Keycloak returns 204 No Content for successful OIDC logout
    assert logout_response.status_code == 204
    
    # Verify token is revoked: user info call should now fail with 401 Unauthorized
    revoked_userinfo = requests.get(userinfo_url, headers=headers, timeout=10)
    assert revoked_userinfo.status_code == 401
    
    # Refreshing again should fail
    refresh_payload = {
        "client_id": "dashboard",
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    failed_refresh = requests.post(token_url, data=refresh_payload, timeout=10)
    assert failed_refresh.status_code == 400
    assert "invalid_grant" in failed_refresh.json().get("error", "")


# ============================================================
# Task 3: RBAC - Role-Based Access Control (AC 3.1 - 3.6)
# ============================================================

def get_admin_token_for_realm(realm_id):
    """Helper: Lấy admin token từ master realm để gọi Admin API."""
    url = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
    data = {
        "client_id": "admin-cli",
        "username": ADMIN_USER,
        "password": ADMIN_PASSWORD,
        "grant_type": "password"
    }
    response = requests.post(url, data=data, timeout=10)
    response.raise_for_status()
    return response.json()["access_token"]


def test_rbac_roles_exist(provision_tenant):
    """
    AC 3.1: Auth_Service SHALL hỗ trợ roles: Admin, Manager, Agent, Viewer.
    Kiểm tra tất cả các role được tạo trong realm của tenant.
    """
    admin_token = get_admin_token_for_realm("solavie")
    url = f"{KEYCLOAK_URL}/admin/realms/solavie/roles"
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = requests.get(url, headers=headers, timeout=10)
    assert response.status_code == 200

    existing_roles = {role["name"] for role in response.json()}
    for role_name in ROLES_TO_TEST:
        assert role_name in existing_roles, f"Role '{role_name}' MUST exist in realm 'solavie'"


def test_rbac_admin_role_in_token(provision_tenant):
    """
    AC 3.6: Auth_Service SHALL include roles trong JWT token claims.
    Admin user phải có role 'Admin' trong token.
    """
    token_url = f"{KEYCLOAK_URL}/realms/solavie/protocol/openid-connect/token"
    payload = {
        "client_id": "dashboard",
        "username": f"admin-{TEST_TENANT_ID}",
        "password": TEST_ADMIN_PASSWORD,
        "grant_type": "password",
        "scope": "openid email profile organization"
    }
    response = requests.post(token_url, data=payload, timeout=10)
    assert response.status_code == 200
    token_data = response.json()

    claims = decode_jwt_payload(token_data["access_token"])
    roles = claims.get("roles", [])
    assert "Admin" in roles, f"Expected 'Admin' role in JWT claims, got: {roles}"


def test_rbac_create_manager_user(provision_tenant):
    """
    AC 3.3: Manager role phải có thể được gán cho user.
    Tạo user mới với role Manager và xác minh role trong token.
    """
    admin_token = get_admin_token_for_realm("solavie")
    # 1. Tạo user mới
    manager_username = f"manager-{uuid.uuid4().hex[:8]}"
    manager_password = "ManagerPass456!"
    user_payload = {
        "username": manager_username,
        "email": f"{manager_username}@test.com",
        "firstName": "Test",
        "lastName": "Manager",
        "enabled": True,
        "emailVerified": True,
        "requiredActions": [],
        "credentials": [{"type": "password", "value": manager_password, "temporary": False}]
    }
    create_user_url = f"{KEYCLOAK_URL}/admin/realms/solavie/users"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    resp = requests.post(create_user_url, headers=headers, json=user_payload, timeout=10)
    assert resp.status_code == 201, f"Failed to create user: {resp.text}"
    user_id = resp.headers.get("Location", "").split("/")[-1]

    # 2. Lấy ID của role Manager
    roles_url = f"{KEYCLOAK_URL}/admin/realms/solavie/roles/Manager"
    role_resp = requests.get(roles_url, headers=headers, timeout=10)
    assert role_resp.status_code == 200, f"Role 'Manager' not found: {role_resp.text}"
    manager_role = role_resp.json()

    # 3. Gán role Manager cho user
    assign_url = f"{KEYCLOAK_URL}/admin/realms/solavie/users/{user_id}/role-mappings/realm"
    assign_resp = requests.post(assign_url, headers=headers, json=[manager_role], timeout=10)
    assert assign_resp.status_code == 204, f"Failed to assign Manager role: {assign_resp.text}"

    # 4. Link user to organization
    org_id = provision_tenant["organization_id"]
    member_url = f"{KEYCLOAK_URL}/admin/realms/solavie/organizations/{org_id}/members"
    member_resp = requests.post(member_url, headers=headers, json=user_id, timeout=10)
    assert member_resp.status_code in [200, 201, 204]

    # 5. Lấy token và xác minh role Manager trong JWT claims
    token_url = f"{KEYCLOAK_URL}/realms/solavie/protocol/openid-connect/token"
    token_payload = {
        "client_id": "dashboard",
        "username": manager_username,
        "password": manager_password,
        "grant_type": "password",
        "scope": "openid email profile organization"
    }
    token_resp = requests.post(token_url, data=token_payload, timeout=10)
    assert token_resp.status_code == 200, f"Login failed for manager user: {token_resp.text}"
    claims = decode_jwt_payload(token_resp.json()["access_token"])
    assert "Manager" in claims.get("roles", []), f"Expected 'Manager' in roles, got: {claims.get('roles')}"
    assert TEST_TENANT_ID in claims.get("organization", [])


# ============================================================
# Task 4 AC 4.5 + Task 5 AC 5.3: Dynamic Security Config Sync
# ============================================================

def test_dynamic_password_policy_sync(provision_tenant):
    """
    AC 4.5: Auth_Service SHALL áp dụng chính sách mật khẩu được đồng bộ từ Tenant Config Service.
    Kiểm tra: Thay đổi passwordPolicy được đồng bộ thành công vào attributes của Organization.
    """
    admin_token = get_admin_token_for_realm("solavie")
    org_id = provision_tenant["organization_id"]
    org_url = f"{KEYCLOAK_URL}/admin/realms/solavie/organizations/{org_id}"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    # Connect to Redis to trigger sync
    r = get_redis_client()
    
    # Update config in Redis
    config_key = f"tenant:{TEST_TENANT_ID}:config:security_comments_notif"
    config_payload = {
        "auth_password_min_length": 14,
        "auth_max_login_attempts": 7
    }
    r.set(config_key, json.dumps(config_payload))
    
    # Publish to pub/sub channel to trigger sync worker
    sync_event = {
        "category": "security_comments_notif",
        "tenant_id": TEST_TENANT_ID
    }
    r.publish("config.updates", json.dumps(sync_event))
    
    # Wait for sync worker to run
    time.sleep(2)
    
    # Verify the Organization attributes were updated
    response = requests.get(org_url, headers=headers, timeout=10)
    assert response.status_code == 200
    org_data = response.json()
    attrs = org_data.get("attributes", {})
    
    assert attrs.get("auth_password_min_length") == ["14"], f"Expected min length 14, got {attrs.get('auth_password_min_length')}"
    assert attrs.get("auth_max_login_attempts") == ["7"], f"Expected max attempts 7, got {attrs.get('auth_max_login_attempts')}"


def test_brute_force_protection_sync(provision_tenant):
    """
    AC 5.3: Auth_Service SHALL giới hạn số lần đăng nhập sai theo cấu hình auth_max_login_attempts.
    Kiểm tra: Thay đổi brute-force settings được đồng bộ vào attributes của Organization.
    """
    admin_token = get_admin_token_for_realm("solavie")
    org_id = provision_tenant["organization_id"]
    org_url = f"{KEYCLOAK_URL}/admin/realms/solavie/organizations/{org_id}"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    r = get_redis_client()
    
    # Update config in Redis
    config_key = f"tenant:{TEST_TENANT_ID}:config:security_comments_notif"
    config_payload = {
        "auth_password_min_length": 8,
        "auth_max_login_attempts": 3
    }
    r.set(config_key, json.dumps(config_payload))
    
    # Publish to pub/sub channel to trigger sync worker
    sync_event = {
        "category": "security_comments_notif",
        "tenant_id": TEST_TENANT_ID
    }
    r.publish("config.updates", json.dumps(sync_event))
    
    # Wait for sync worker to run
    time.sleep(2)
    
    # Verify the Organization attributes were updated
    response = requests.get(org_url, headers=headers, timeout=10)
    assert response.status_code == 200
    org_data = response.json()
    attrs = org_data.get("attributes", {})
    
    assert attrs.get("auth_max_login_attempts") == ["3"]


# ============================================================
# Task 5 AC 5.1: Token Security - RS256 Signing Algorithm
# ============================================================

def test_token_signed_with_rs256(provision_tenant):
    """
    AC 5.1: Auth_Service SHALL sign tokens với RS256 (asymmetric keys).
    Xác minh JWT header chứa 'alg: RS256'.
    """
    token_url = f"{KEYCLOAK_URL}/realms/solavie/protocol/openid-connect/token"
    payload = {
        "client_id": "dashboard",
        "username": f"admin-{TEST_TENANT_ID}",
        "password": TEST_ADMIN_PASSWORD,
        "grant_type": "password",
        "scope": "openid"
    }
    response = requests.post(token_url, data=payload, timeout=10)
    assert response.status_code == 200
    access_token = response.json()["access_token"]

    # Decode JWT header (first part)
    header_b64 = access_token.split(".")[0]
    header_b64 += "=" * (-len(header_b64) % 4)
    header = json.loads(base64.urlsafe_b64decode(header_b64).decode("utf-8"))

    assert header.get("alg") == "RS256", \
        f"Expected RS256 algorithm in JWT header, got: {header.get('alg')}"
    assert header.get("typ") == "JWT", \
        f"Expected 'JWT' type in header, got: {header.get('typ')}"


def test_refresh_token_rotation(provision_tenant):
    """
    Xác minh Refresh Token Rotation hoạt động:
    Refresh token cũ sau khi sử dụng một lần phải bị vô hiệu hóa ngay lập tức.
    """
    token_url = f"{KEYCLOAK_URL}/realms/solavie/protocol/openid-connect/token"
    payload = {
        "client_id": "dashboard",
        "username": f"admin-{TEST_TENANT_ID}",
        "password": TEST_ADMIN_PASSWORD,
        "grant_type": "password",
        "scope": "openid"
    }
    # 1. Login lần đầu lấy token
    response = requests.post(token_url, data=payload, timeout=10)
    assert response.status_code == 200
    token_data = response.json()
    refresh_token_1 = token_data["refresh_token"]

    # 2. Sử dụng refresh_token lần thứ nhất -> nhận token mới và refresh_token_2
    refresh_payload = {
        "client_id": "dashboard",
        "grant_type": "refresh_token",
        "refresh_token": refresh_token_1
    }
    response_refresh_1 = requests.post(token_url, data=refresh_payload, timeout=10)
    assert response_refresh_1.status_code == 200
    
    # 3. Thử sử dụng lại refresh_token_1 đã dùng -> phải bị từ chối với lỗi 400
    response_refresh_2 = requests.post(token_url, data=refresh_payload, timeout=10)
    assert response_refresh_2.status_code == 400, \
        f"Expected 400 when reusing refresh token, got: {response_refresh_2.status_code}. Response: {response_refresh_2.text}"
    assert "invalid_grant" in response_refresh_2.json().get("error", "")


def test_pkce_enforcement(provision_tenant):
    """
    Xác minh PKCE được cưỡng chế cho Dashboard client.
    Gửi Authorization Request không có code_challenge -> phải bị từ chối.
    """
    auth_url = f"{KEYCLOAK_URL}/realms/solavie/protocol/openid-connect/auth"
    params = {
        "client_id": "dashboard",
        "redirect_uri": "http://localhost:8000",
        "response_type": "code",
        "scope": "openid"
    }
    response = requests.get(auth_url, params=params, timeout=10, allow_redirects=False)
    # Keycloak có thể trả về 400 Bad Request hoặc 302 Redirect kèm tham số lỗi PKCE
    if response.status_code == 302:
        location = response.headers.get("Location", "")
        assert "code_challenge" in location or "invalid_request" in location or "error" in location, \
            f"Expected PKCE-related error in redirect Location, got: {location}"
    else:
        assert response.status_code == 400, \
            f"Expected 400 Bad Request due to missing PKCE parameters, got: {response.status_code}"
        assert "code_challenge" in response.text or "challenge" in response.text or "PKCE" in response.text
