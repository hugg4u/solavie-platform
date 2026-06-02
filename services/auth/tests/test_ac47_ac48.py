"""
Test suite for remaining Auth Service tasks:
  - AC 4.7: user-service-client Client Credentials provisioning & Least Privilege role assignment
  - AC 4.8: Sync Worker forwards Keycloak user events to User Service webhook
"""
import os
import sys
import json
import hmac
import hashlib
import uuid
import pytest
import requests
from unittest.mock import patch, MagicMock

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8081")
ADMIN_USER = os.getenv("KC_ADMIN", "admin")
ADMIN_PASSWORD = os.getenv("KC_ADMIN_PASSWORD", "admin_secret_pass")

# Reuse the same tenant provisioned by test_auth.py session fixture.
# If run standalone, provision a fresh one.
TEST_TENANT_ID = os.getenv("TEST_TENANT_ID", f"tenant-ac47-{uuid.uuid4()}")
TEST_TENANT_NAME = "AC47 Test Tenant"
TEST_ADMIN_EMAIL = "admin@ac47tenant.com"
TEST_ADMIN_PASSWORD = "SolavieSecurePass123!"


# ---------------------------------------------------------------------------
# Fixture: Provision tenant (idempotent — skips if realm already exists)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def ensure_tenant_exists():
    """Provision the test tenant if it doesn't already exist."""
    import subprocess
    script_path = os.path.join(os.path.dirname(__file__), "../scripts/provision_realm.py")
    cmd = [
        sys.executable, script_path,
        "--keycloak-url", KEYCLOAK_URL,
        "--admin-username", ADMIN_USER,
        "--admin-password", ADMIN_PASSWORD,
        "--tenant-id", TEST_TENANT_ID,
        "--tenant-name", TEST_TENANT_NAME,
        "--admin-email", TEST_ADMIN_EMAIL,
        "--admin-password-user", TEST_ADMIN_PASSWORD,
        # Do NOT use --force so we skip if already exists
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # returncode 0 = created, returncode 0 with "already exists" message = skipped → both OK
    assert result.returncode == 0, \
        f"Provisioning for AC 4.7/4.8 test tenant failed: {result.stderr}"


def _get_admin_token():
    """Get Keycloak master realm admin token."""
    token_url = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
    resp = requests.post(token_url, data={
        "client_id": "admin-cli",
        "username": ADMIN_USER,
        "password": ADMIN_PASSWORD,
        "grant_type": "password"
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# AC 4.7 Tests — user-service-client provisioning
# ---------------------------------------------------------------------------

class TestAC47UserServiceClient:
    """
    AC 4.7 / Requirement 5.4:
    user-service-client must be provisioned with Client Credentials only,
    and its service account must have ONLY 'manage-users' role from realm-management.
    """

    def test_client_exists_with_correct_config(self, ensure_tenant_exists):
        """
        AC 4.7.1: 'user-service-client' phải tồn tại trong tenant realm
        với đúng cấu hình Client Credentials (không phải public client).
        """
        admin_token = _get_admin_token()
        headers = {"Authorization": f"Bearer {admin_token}"}

        resp = requests.get(
            f"{KEYCLOAK_URL}/admin/realms/{TEST_TENANT_ID}/clients",
            headers=headers, timeout=10
        )
        assert resp.status_code == 200, f"Failed to fetch clients: {resp.text}"

        clients = resp.json()
        user_svc = next((c for c in clients if c["clientId"] == "user-service-client"), None)

        assert user_svc is not None, \
            "AC 4.7 FAILED: 'user-service-client' was NOT provisioned in tenant realm"
        assert user_svc["serviceAccountsEnabled"] is True, \
            "AC 4.7 FAILED: serviceAccountsEnabled must be True (Client Credentials Flow)"
        assert user_svc["standardFlowEnabled"] is False, \
            "AC 4.7 FAILED: standardFlowEnabled must be False (Least Privilege — no Authorization Code)"
        assert user_svc["publicClient"] is False, \
            "AC 4.7 FAILED: must be confidential client (publicClient=False)"
        assert user_svc["directAccessGrantsEnabled"] is False, \
            "AC 4.7 FAILED: directAccessGrantsEnabled must be False (no password grant)"

    def test_service_account_has_manage_users_role_only(self, ensure_tenant_exists):
        """
        AC 4.7.2 / Requirement 5.4 Least Privilege:
        Service account phải có 'manage-users' nhưng KHÔNG có 'manage-realm',
        'manage-clients', hay bất kỳ admin-level role nào khác.
        """
        admin_token = _get_admin_token()
        headers = {"Authorization": f"Bearer {admin_token}"}
        base = KEYCLOAK_URL

        # 1. Lấy UUIDs
        clients_resp = requests.get(
            f"{base}/admin/realms/{TEST_TENANT_ID}/clients",
            headers=headers, timeout=10
        )
        clients_resp.raise_for_status()
        clients = clients_resp.json()

        user_svc = next((c for c in clients if c["clientId"] == "user-service-client"), None)
        realm_mgmt = next((c for c in clients if c["clientId"] == "realm-management"), None)
        assert user_svc and realm_mgmt, "Required clients not found in realm"

        # 2. Lấy service account user
        sa_resp = requests.get(
            f"{base}/admin/realms/{TEST_TENANT_ID}/clients/{user_svc['id']}/service-account-user",
            headers=headers, timeout=10
        )
        assert sa_resp.status_code == 200, f"Service account not accessible: {sa_resp.text}"
        sa_user_id = sa_resp.json()["id"]

        # 3. Kiểm tra role mappings
        roles_resp = requests.get(
            f"{base}/admin/realms/{TEST_TENANT_ID}/users/{sa_user_id}/role-mappings/clients/{realm_mgmt['id']}",
            headers=headers, timeout=10
        )
        assert roles_resp.status_code == 200
        assigned_roles = [r["name"] for r in roles_resp.json()]

        assert "manage-users" in assigned_roles, \
            f"AC 4.7 FAILED: 'manage-users' not assigned. Got: {assigned_roles}"

        # Least Privilege check — no overly-broad roles
        banned_roles = {"manage-realm", "manage-clients", "manage-authorization", "realm-admin"}
        violations = banned_roles.intersection(set(assigned_roles))
        assert not violations, \
            f"AC 4.7 SECURITY VIOLATION: Service account has over-privileged roles: {violations}"


# ---------------------------------------------------------------------------
# AC 4.8 Tests — Sync Worker event forwarding (unit tests with mock)
# ---------------------------------------------------------------------------

class TestAC48SyncWorkerEventForwarding:
    """
    AC 4.8: sync_worker.py lắng nghe 'auth.user.events' và forward đúng sang
    User Service webhook endpoint với HMAC-SHA256 signature.
    """

    @pytest.fixture(autouse=True)
    def setup_module_import(self):
        """Import sync_worker module và patch constants cho từng test."""
        scripts_dir = os.path.join(os.path.dirname(__file__), "../scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        import sync_worker as sw
        self.sw = sw

        # Backup originals
        self._orig_secret = sw.WEBHOOK_SECRET
        self._orig_url = sw.USER_SERVICE_WEBHOOK_URL

        sw.WEBHOOK_SECRET = "test-secret-key-256"
        sw.USER_SERVICE_WEBHOOK_URL = "http://mock-user-service:3008/api/v1/users/events"

        yield

        # Restore
        sw.WEBHOOK_SECRET = self._orig_secret
        sw.USER_SERVICE_WEBHOOK_URL = self._orig_url

    def _compute_expected_sig(self, payload_dict: dict) -> str:
        payload_str = json.dumps(payload_dict, separators=(",", ":"))
        return hmac.new(
            "test-secret-key-256".encode("utf-8"),
            payload_str.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    def test_verify_email_event_mapped_correctly(self):
        """AC 4.8: VERIFY_EMAIL → user.verified mapping và webhook được gọi."""
        with patch("sync_worker.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=204)

            self.sw.forward_user_event_to_service({
                "type": "VERIFY_EMAIL",
                "user_id": "user-uuid-001",
                "realm": "tenant-xyz",
                "email": "user@test.com"
            })

            assert mock_post.called, "AC 4.8 FAILED: webhook was not called"
            sent_data = json.loads(mock_post.call_args[1]["data"])
            assert sent_data["event"] == "user.verified"
            assert sent_data["userId"] == "user-uuid-001"
            assert sent_data["realm"] == "tenant-xyz"

    def test_disable_user_event_mapped_correctly(self):
        """AC 4.8: DISABLE_USER → user.disabled."""
        with patch("sync_worker.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=204)

            self.sw.forward_user_event_to_service({
                "type": "DISABLE_USER",
                "user_id": "user-uuid-002",
                "realm": "tenant-xyz",
            })

            sent_data = json.loads(mock_post.call_args[1]["data"])
            assert sent_data["event"] == "user.disabled"

    def test_delete_user_event_mapped_correctly(self):
        """AC 4.8: DELETE_USER → user.deleted."""
        with patch("sync_worker.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=204)

            self.sw.forward_user_event_to_service({
                "type": "DELETE_USER",
                "user_id": "user-uuid-003",
                "realm": "tenant-xyz",
            })

            sent_data = json.loads(mock_post.call_args[1]["data"])
            assert sent_data["event"] == "user.deleted"

    def test_hmac_signature_is_correct(self):
        """
        AC 4.8: Header X-Webhook-Signature phải chứa HMAC-SHA256 đúng
        để User Service có thể xác thực nguồn gốc event.
        """
        with patch("sync_worker.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=204)

            self.sw.forward_user_event_to_service({
                "type": "VERIFY_EMAIL",
                "user_id": "user-uuid-sig-test",
                "realm": "tenant-sig",
                "email": "sig@test.com"
            })

            sent_headers = mock_post.call_args[1]["headers"]
            sent_data = mock_post.call_args[1]["data"]

            assert "X-Webhook-Signature" in sent_headers, \
                "AC 4.8 FAILED: HMAC signature header missing from webhook request"

            # Recompute expected sig from actual sent data
            expected_sig = hmac.new(
                "test-secret-key-256".encode("utf-8"),
                sent_data.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()

            assert sent_headers["X-Webhook-Signature"] == expected_sig, \
                f"AC 4.8 FAILED: HMAC signature mismatch.\n" \
                f"Got: {sent_headers['X-Webhook-Signature']}\n" \
                f"Expected: {expected_sig}"

    def test_webhook_url_is_correct_endpoint(self):
        """AC 4.8: Phải gọi đúng User Service webhook URL."""
        with patch("sync_worker.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=204)

            self.sw.forward_user_event_to_service({
                "type": "REGISTER",
                "user_id": "user-uuid-004",
                "realm": "tenant-url-test"
            })

            called_url = mock_post.call_args[0][0]
            assert called_url == "http://mock-user-service:3008/api/v1/users/events", \
                f"AC 4.8 FAILED: Wrong webhook URL: {called_url}"
