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

def decode_jwt_payload(token):
    parts = token.split('.')
    if len(parts) != 3:
        raise ValueError("Invalid JWT token format")
    payload_b64 = parts[1]
    payload_b64 += '=' * (-len(payload_b64) % 4)
    payload_json = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
    return json.loads(payload_json)

def get_admin_token():
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

def get_organization_id(keycloak_url, admin_token, realm_name, alias):
    url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/organizations"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    orgs = response.json()
    for org in orgs:
        if org.get("alias") == alias:
            return org.get("id")
    return None

def test_organization_provisioning_and_migration():
    # 1. Khởi tạo legacy tenant bằng provision_realm.py
    unique_suffix = uuid.uuid4().hex[:8]
    legacy_tenant_id = f"legacy-tenant-{unique_suffix}"
    legacy_tenant_name = f"Legacy Tenant Co {unique_suffix}"
    legacy_admin_email = f"admin@{legacy_tenant_id}.com"
    legacy_admin_password = "LegacySecurePass123!"

    provision_realm_script = os.path.join(os.path.dirname(__file__), "../scripts/provision_realm.py")
    cmd_legacy = [
        sys.executable, provision_realm_script,
        "--keycloak-url", KEYCLOAK_URL,
        "--admin-username", ADMIN_USER,
        "--admin-password", ADMIN_PASSWORD,
        "--tenant-id", legacy_tenant_id,
        "--tenant-name", legacy_tenant_name,
        "--admin-email", legacy_admin_email,
        "--admin-password-user", legacy_admin_password
    ]
    
    print(f"Running legacy provisioning: {' '.join(cmd_legacy)}")
    result_legacy = subprocess.run(cmd_legacy, capture_output=True, text=True)
    assert result_legacy.returncode == 0, f"Legacy realm provisioning failed: {result_legacy.stderr}"

    # 2. Tạo Realm 'solavie' và Organization bằng provision_organization.py (nếu chưa có realm, script tự động tạo)
    provision_org_script = os.path.join(os.path.dirname(__file__), "../scripts/provision_organization.py")
    org_suffix = uuid.uuid4().hex[:8]
    org_tenant_id = f"org-tenant-{org_suffix}"
    org_tenant_name = f"Org Tenant Co {org_suffix}"
    org_admin_email = f"admin@{org_tenant_id}.com"
    org_admin_password = "SolavieSecurePass123!"

    cmd_org = [
        sys.executable, provision_org_script,
        "--keycloak-url", KEYCLOAK_URL,
        "--admin-username", ADMIN_USER,
        "--admin-password", ADMIN_PASSWORD,
        "--tenant-id", org_tenant_id,
        "--tenant-name", org_tenant_name,
        "--admin-email", org_admin_email,
        "--admin-password-user", org_admin_password
    ]
    
    print(f"Running organization provisioning: {' '.join(cmd_org)}")
    result_org = subprocess.run(cmd_org, capture_output=True, text=True)
    assert result_org.returncode == 0, f"Organization provisioning failed: {result_org.stderr}"

    # Verify output format
    assert "PROVISION_OUTPUT_START" in result_org.stdout
    assert "PROVISION_OUTPUT_END" in result_org.stdout

    # 3. Chạy script di trú migrate_realm_to_org.py để đưa users từ legacy realm sang organization mới trong realm 'solavie'
    migrate_script = os.path.join(os.path.dirname(__file__), "../scripts/migrate_realm_to_org.py")
    cmd_migrate = [
        sys.executable, migrate_script,
        "--keycloak-url", KEYCLOAK_URL,
        "--admin-username", ADMIN_USER,
        "--admin-password", ADMIN_PASSWORD,
        "--old-realm", legacy_tenant_id,
        "--new-realm", "solavie"
    ]
    
    print(f"Running user migration: {' '.join(cmd_migrate)}")
    result_migrate = subprocess.run(cmd_migrate, capture_output=True, text=True)
    assert result_migrate.returncode == 0, f"Migration script failed: {result_migrate.stderr}"

    # 4. Xác minh qua Keycloak Admin API
    admin_token = get_admin_token()
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    # a. Kiểm tra Org exist
    org_url = f"{KEYCLOAK_URL}/admin/realms/solavie/organizations"
    resp_orgs = requests.get(org_url, headers=headers, timeout=10)
    assert resp_orgs.status_code == 200
    org_list = resp_orgs.json()
    legacy_org = next((o for o in org_list if o["alias"] == legacy_tenant_id), None)
    assert legacy_org is not None, f"Organization with alias {legacy_tenant_id} should be created by migration"

    # b. Kiểm tra user đã di trú tồn tại trong realm 'solavie'
    migrated_username = f"admin-{legacy_tenant_id}"
    user_search_url = f"{KEYCLOAK_URL}/admin/realms/solavie/users?username={migrated_username}"
    resp_users = requests.get(user_search_url, headers=headers, timeout=10)
    assert resp_users.status_code == 200
    users = resp_users.json()
    assert len(users) == 1, f"Migrated user {migrated_username} should exist in realm 'solavie'"
    migrated_user = users[0]

    # c. Kiểm tra user thuộc về Organization
    members_url = f"{KEYCLOAK_URL}/admin/realms/solavie/organizations/{legacy_org['id']}/members"
    resp_members = requests.get(members_url, headers=headers, timeout=10)
    assert resp_members.status_code == 200
    member_ids = [m["id"] for m in resp_members.json()]
    assert migrated_user["id"] in member_ids, "Migrated user must be a member of the organization"

    # d. Kiểm tra user có realm-level role 'Admin' (được gán từ script di trú)
    user_roles_url = f"{KEYCLOAK_URL}/admin/realms/solavie/users/{migrated_user['id']}/role-mappings/realm"
    resp_roles = requests.get(user_roles_url, headers=headers, timeout=10)
    assert resp_roles.status_code == 200
    roles = [r["name"] for r in resp_roles.json()]
    assert "Admin" in roles, f"Migrated user must have 'Admin' role assigned. Got: {roles}"

    # 5. Xác minh JWT token chứa claim organization và roles
    # Do user được di trú có 'requiredActions': ['UPDATE_PASSWORD'], direct password grant sẽ bị chặn/yêu cầu reset.
    # Để kiểm tra lấy token và decode claims, thiếp sẽ tạm thời xoá requiredActions và set password cố định cho user.
    update_user_url = f"{KEYCLOAK_URL}/admin/realms/solavie/users/{migrated_user['id']}"
    # Xoá requiredActions
    resp_update = requests.put(update_user_url, headers=headers, json={"requiredActions": []}, timeout=10)
    assert resp_update.status_code == 204
    
    # Set mật khẩu mới
    reset_pwd_url = f"{KEYCLOAK_URL}/admin/realms/solavie/users/{migrated_user['id']}/reset-password"
    resp_pwd = requests.put(reset_pwd_url, headers=headers, json={
        "type": "password",
        "value": "NewMigratedPass123!",
        "temporary": False
    }, timeout=10)
    assert resp_pwd.status_code == 204

    # Đăng nhập lấy access token
    token_url = f"{KEYCLOAK_URL}/realms/solavie/protocol/openid-connect/token"
    payload = {
        "client_id": "dashboard",
        "username": migrated_username,
        "password": "NewMigratedPass123!",
        "grant_type": "password",
        "scope": "openid email profile organization:*"
    }
    resp_token = requests.post(token_url, data=payload, timeout=10)
    assert resp_token.status_code == 200
    token_data = resp_token.json()
    assert "access_token" in token_data

    # Giải mã JWT
    claims = decode_jwt_payload(token_data["access_token"])
    print(f"Decoded JWT Claims: {json.dumps(claims, indent=2)}")

    # Xác minh claims
    assert "organization" in claims, "JWT claims should contain organization memberships"
    org_claim = claims["organization"]
    assert len(org_claim) > 0
    assert legacy_tenant_id in org_claim or any(legacy_tenant_id in o for o in org_claim)

    assert "roles" in claims
    assert "Admin" in claims["roles"]
    
    # Cleanup
    # Delete legacy realm
    del_realm_url = f"{KEYCLOAK_URL}/admin/realms/{legacy_tenant_id}"
    requests.delete(del_realm_url, headers=headers, timeout=10)
    
    # Delete test organizations
    for t_id in [org_tenant_id, legacy_tenant_id]:
        o_id = get_organization_id(KEYCLOAK_URL, admin_token, "solavie", t_id)
        if o_id:
            requests.delete(f"{KEYCLOAK_URL}/admin/realms/solavie/organizations/{o_id}", headers=headers, timeout=10)
            
    # Delete test users
    for u_name in [f"admin-{org_tenant_id}", f"admin-{legacy_tenant_id}"]:
        u_resp = requests.get(f"{KEYCLOAK_URL}/admin/realms/solavie/users?username={u_name}", headers=headers, timeout=10)
        if u_resp.status_code == 200 and u_resp.json():
            u_id = u_resp.json()[0]["id"]
            requests.delete(f"{KEYCLOAK_URL}/admin/realms/solavie/users/{u_id}", headers=headers, timeout=10)
