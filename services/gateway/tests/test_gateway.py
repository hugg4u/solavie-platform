import os
import time
import requests
import pytest

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8081")
TEST_TENANT_ID = "tenant-test-uuid"
ADMIN_PASSWORD = "SolavieSecurePass123!"

@pytest.fixture(scope="module")
def access_token():
    # First ensure we can get a token from the auth service directly
    token_url = f"{KEYCLOAK_URL}/realms/{TEST_TENANT_ID}/protocol/openid-connect/token"
    payload = {
        "client_id": "dashboard",
        "username": "admin",
        "password": ADMIN_PASSWORD,
        "grant_type": "password",
        "scope": "openid email profile"
    }
    
    response = requests.post(token_url, data=payload, timeout=10)
    if response.status_code != 200:
        pytest.skip(f"Could not authenticate with Keycloak for tests: {response.text}")
    
    return response.json()["access_token"]

def test_gateway_routing_no_auth():
    # Requirement 2.2: WHEN token invalid hoặc expired, THE Gateway SHALL trả về 401 Unauthorized
    # The /api/v1/auth route is protected by OIDC globally
    url = f"{GATEWAY_URL}/api/v1/auth/realms/master/.well-known/openid-configuration"
    response = requests.get(url, timeout=5)
    
    # 401 Unauthorized is expected because we provided no token
    assert response.status_code == 401
    
def test_gateway_routing_with_auth(access_token):
    # Requirement 1.1: Route requests based on prefix
    # Requirement 2.1: Validate JWT tokens via OIDC plugin
    url = f"{GATEWAY_URL}/api/v1/auth/realms/{TEST_TENANT_ID}/.well-known/openid-configuration"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    response = requests.get(url, headers=headers, timeout=10)
    
    # If the token is valid, it should forward the request to Keycloak and get a 200
    assert response.status_code == 200
    assert "issuer" in response.json()

def test_gateway_rate_limiting(access_token):
    # Requirement 3.1 & 3.3: Rate limit per tenant and return 429 when exceeded
    # We set a high rate limit (200/min) so to trigger it we would need many requests.
    # We will do a few requests to verify headers are present
    url = f"{GATEWAY_URL}/api/v1/auth/realms/{TEST_TENANT_ID}/.well-known/openid-configuration"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Tenant-ID": TEST_TENANT_ID
    }
    
    response = requests.get(url, headers=headers, timeout=10)
    assert response.status_code == 200
    
    # Verify rate limit headers are injected by Kong
    assert "X-RateLimit-Limit-Minute" in response.headers
    assert "X-RateLimit-Remaining-Minute" in response.headers

def test_gateway_cors(access_token):
    # Requirement 4.4: CORS configuration per-route
    url = f"{GATEWAY_URL}/api/v1/auth/realms/{TEST_TENANT_ID}/.well-known/openid-configuration"
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET"
    }
    
    # OPTIONS request shouldn't require auth
    response = requests.options(url, headers=headers, timeout=10)
    assert response.status_code in [200, 204]
    assert response.headers.get("Access-Control-Allow-Origin") in ["*", "http://localhost:3000"]
    assert "Authorization" in response.headers.get("Access-Control-Allow-Headers", "")

def test_gateway_observability():
    # Requirement 5.1 & 5.4: Prometheus metrics and health endpoints
    url = f"http://localhost:8001/metrics"
    try:
        response = requests.get(url, timeout=10)
        assert response.status_code == 200
        assert "kong_http_requests_total" in response.text
    except requests.exceptions.ConnectionError:
        pass # Admin API might not be exposed depending on setup
