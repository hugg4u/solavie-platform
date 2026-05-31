import os
import subprocess
import sys
import json
import base64
import time
import pytest
import requests

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8081")
ADMIN_USER = os.getenv("KC_ADMIN", "admin")
ADMIN_PASSWORD = os.getenv("KC_ADMIN_PASSWORD", "admin_secret_pass")
TEST_TENANT_ID = "tenant-test-uuid"
TEST_TENANT_NAME = "Test Tenant Company"
TEST_ADMIN_EMAIL = "admin@testtenant.com"
TEST_ADMIN_PASSWORD = "SolavieSecurePass123!"

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
    script_path = os.path.join(os.path.dirname(__file__), "../scripts/provision_realm.py")
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
    discovery_url = f"{KEYCLOAK_URL}/realms/{TEST_TENANT_ID}/.well-known/openid-configuration"
    response = requests.get(discovery_url, timeout=10)
    assert response.status_code == 200
    data = response.json()
    
    # Basic OIDC assertions
    # Keycloak returns the issuer based on KC_HOSTNAME config which may not include the port.
    # We verify the realm suffix is correct rather than exact URL match.
    assert data["issuer"].endswith(f"/realms/{TEST_TENANT_ID}")
    assert "authorization_endpoint" in data
    assert "token_endpoint" in data
    assert "jwks_uri" in data
    assert "userinfo_endpoint" in data
    assert "end_session_endpoint" in data

def test_oauth2_password_grant(provision_tenant):
    # Simulate obtaining a token using Direct Access Grants (direct login check)
    token_url = f"{KEYCLOAK_URL}/realms/{TEST_TENANT_ID}/protocol/openid-connect/token"
    payload = {
        "client_id": "dashboard",
        "username": "admin",
        "password": TEST_ADMIN_PASSWORD,
        "grant_type": "password",
        "scope": "openid email profile"
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
    assert claims["tenant_id"] == TEST_TENANT_ID
    assert "Admin" in claims.get("roles", [])
    assert claims.get("email") == TEST_ADMIN_EMAIL
    
    # Check default password policy lockout and complexity settings
    # Test session idle / lifetime settings
    assert token_data.get("expires_in") <= 900  # Access token lifespan: 15 min (900 seconds)

def test_token_refresh(provision_tenant):
    # Authenticate first
    token_url = f"{KEYCLOAK_URL}/realms/{TEST_TENANT_ID}/protocol/openid-connect/token"
    payload = {
        "client_id": "dashboard",
        "username": "admin",
        "password": TEST_ADMIN_PASSWORD,
        "grant_type": "password",
        "scope": "openid email profile"
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
    assert claims["tenant_id"] == TEST_TENANT_ID
    assert "Admin" in claims.get("roles", [])

def test_token_revocation_logout(provision_tenant):
    # Authenticate
    token_url = f"{KEYCLOAK_URL}/realms/{TEST_TENANT_ID}/protocol/openid-connect/token"
    payload = {
        "client_id": "dashboard",
        "username": "admin",
        "password": TEST_ADMIN_PASSWORD,
        "grant_type": "password",
        "scope": "openid email profile"
    }
    response = requests.post(token_url, data=payload, timeout=10)
    assert response.status_code == 200
    token_data = response.json()
    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]
    
    # User info verification before logout
    userinfo_url = f"{KEYCLOAK_URL}/realms/{TEST_TENANT_ID}/protocol/openid-connect/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    userinfo_response = requests.get(userinfo_url, headers=headers, timeout=10)
    assert userinfo_response.status_code == 200
    
    # Perform Logout
    logout_url = f"{KEYCLOAK_URL}/realms/{TEST_TENANT_ID}/protocol/openid-connect/logout"
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
