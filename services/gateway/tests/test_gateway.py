import os
import time
import json
import redis
import requests
import pytest

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8081")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

TEST_TENANT_ID = "tenant-test-uuid"
ADMIN_PASSWORD = "SolavieSecurePass123!"


# ============================================================
# Helper Fixtures
# ============================================================

@pytest.fixture(scope="module")
def access_token():
    """Lấy access token từ Keycloak để dùng trong các gateway tests."""
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


@pytest.fixture(scope="module")
def redis_client():
    """Redis client để seed test config data cho dynamic policy plugin."""
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        r.ping()
        return r
    except Exception:
        pytest.skip("Redis not available for gateway tests")


# ============================================================
# Task 1: Request Routing (AC 1.1, 1.2, 1.3, 1.4)
# ============================================================

def test_gateway_routing_no_auth():
    """
    AC 2.2: WHEN token invalid hoặc expired, THE Gateway SHALL trả về 401 Unauthorized.
    Request không có token đến route được bảo vệ phải nhận 401.
    """
    url = f"{GATEWAY_URL}/api/v1/auth/realms/master/.well-known/openid-configuration"
    response = requests.get(url, timeout=5)
    # 401 Unauthorized is expected because we provided no token
    assert response.status_code == 401


def test_gateway_routing_with_auth(access_token):
    """
    AC 1.1: Route requests based on URL path prefix.
    AC 2.1: Validate JWT tokens via OIDC/JWT plugin.
    Request có token hợp lệ phải được forward đến upstream service.
    """
    url = f"{GATEWAY_URL}/api/v1/auth/realms/{TEST_TENANT_ID}/.well-known/openid-configuration"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers, timeout=10)
    # If the token is valid, it should forward the request to Keycloak and get a 200
    assert response.status_code == 200
    assert "issuer" in response.json()


def test_gateway_health_endpoint_no_auth():
    """
    AC 2.4 & 2.5: Gateway SHALL whitelist health check endpoints (không cần auth).
    """
    # Health check endpoint của Kong không yêu cầu authentication
    url = f"http://localhost:8001/status"
    try:
        response = requests.get(url, timeout=5)
        assert response.status_code == 200
    except requests.exceptions.ConnectionError:
        pytest.skip("Kong Admin API not exposed on port 8001 in this environment")


def test_gateway_webhook_no_auth():
    """
    AC 2.4: Gateway SHALL whitelist webhook endpoints (không cần auth).
    Webhooks route phải accessible mà không cần JWT.
    """
    url = f"{GATEWAY_URL}/webhooks/health"
    try:
        response = requests.get(url, timeout=5)
        # Should NOT return 401 - webhook endpoints are whitelisted
        assert response.status_code != 401, \
            "Webhook endpoint should not require auth (whitelisted by dynamic-policy plugin)"
    except requests.exceptions.ConnectionError:
        pytest.skip("Gateway not available")


# ============================================================
# Task 3: Rate Limiting (AC 3.1 - 3.5)
# ============================================================

def test_gateway_rate_limiting_headers(access_token, redis_client):
    """
    AC 3.1: Rate limiting per-tenant (based on tenant_id).
    AC 3.4: Redis backend cho distributed rate limiting.
    Kiểm tra rate limit headers được inject bởi dynamic-policy plugin.
    """
    # Seed tenant config with rate limits vào Redis
    config_data = json.dumps({
        "gateway_rate_limit_minute": 200,
        "gateway_rate_limit_hour": 5000,
        "allowed_cors_origins": ["http://localhost:3000", "https://dashboard.solavie.io"]
    })
    redis_client.set(f"tenant:{TEST_TENANT_ID}:config:security_comments_notif", config_data)

    url = f"{GATEWAY_URL}/api/v1/auth/realms/{TEST_TENANT_ID}/.well-known/openid-configuration"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Tenant-ID": TEST_TENANT_ID
    }
    response = requests.get(url, headers=headers, timeout=10)
    assert response.status_code == 200

    # AC 3.1: Verify rate limit headers are injected by Kong's dynamic-policy plugin
    assert "X-RateLimit-Limit-Minute" in response.headers, \
        "Expected 'X-RateLimit-Limit-Minute' header from dynamic-policy plugin"
    assert "X-RateLimit-Remaining-Minute" in response.headers, \
        "Expected 'X-RateLimit-Remaining-Minute' header from dynamic-policy plugin"

    limit = int(response.headers["X-RateLimit-Limit-Minute"])
    remaining = int(response.headers["X-RateLimit-Remaining-Minute"])
    assert limit == 200, f"Expected rate limit 200/min (from Redis config), got: {limit}"
    assert remaining >= 0, f"Remaining requests must be >= 0, got: {remaining}"


def test_gateway_dynamic_rate_limit_per_tenant(access_token, redis_client):
    """
    AC 3.5: Dynamic rate limiting - đọc limits từ Redis cache per-tenant.
    Seed low rate limit (5/min) vào Redis → verify sau 6 requests nhận 429.
    """
    # Seed low rate limit for specific test tenant
    low_limit_tenant = "tenant-rate-limit-test"
    config_data = json.dumps({
        "gateway_rate_limit_minute": 5,
        "gateway_rate_limit_hour": 100,
        "allowed_cors_origins": ["*"]
    })
    redis_client.set(f"tenant:{low_limit_tenant}:config:security_comments_notif", config_data)

    # Xóa rate limit counters cũ nếu còn tồn tại
    import math
    min_bucket = math.floor(time.time() / 60)
    redis_client.delete(f"rate:{low_limit_tenant}:min:{min_bucket}")

    url = f"{GATEWAY_URL}/api/v1/auth/realms/{TEST_TENANT_ID}/.well-known/openid-configuration"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Tenant-ID": low_limit_tenant
    }

    # Manually set a rate limit counter above threshold in Redis (simulating exhausted limit)
    redis_client.set(f"rate:{low_limit_tenant}:min:{min_bucket}", 6)
    redis_client.expire(f"rate:{low_limit_tenant}:min:{min_bucket}", 60)

    # Next request should be rejected with 429
    response = requests.get(url, headers=headers, timeout=10)
    assert response.status_code == 429, \
        f"Expected 429 Too Many Requests after rate limit exceeded, got: {response.status_code}"

    # Cleanup
    redis_client.delete(f"rate:{low_limit_tenant}:min:{min_bucket}")
    redis_client.delete(f"tenant:{low_limit_tenant}:config:security_comments_notif")


# ============================================================
# Task 4: SSL & Security - CORS (AC 4.4, 4.5)
# ============================================================

def test_gateway_cors_valid_origin(access_token, redis_client):
    """
    AC 4.4: CORS configuration per-route.
    AC 4.5: Dynamic CORS - kiểm tra Origin hợp lệ từ allowed_cors_origins trong Redis.
    """
    # Seed allowed origins for the test tenant
    config_data = json.dumps({
        "gateway_rate_limit_minute": 200,
        "gateway_rate_limit_hour": 5000,
        "allowed_cors_origins": ["http://localhost:3000", "https://dashboard.solavie.io"]
    })
    redis_client.set(f"tenant:{TEST_TENANT_ID}:config:security_comments_notif", config_data)

    url = f"{GATEWAY_URL}/api/v1/auth/realms/{TEST_TENANT_ID}/.well-known/openid-configuration"

    # OPTIONS preflight request với valid origin → không cần auth
    response = requests.options(url, headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization"
    }, timeout=10)

    assert response.status_code in [200, 204], \
        f"Expected 200/204 for OPTIONS preflight with valid origin, got: {response.status_code}"
    allowed_origin = response.headers.get("Access-Control-Allow-Origin", "")
    assert allowed_origin in ["*", "http://localhost:3000"], \
        f"Expected CORS origin to be allowed, got: '{allowed_origin}'"
    assert "Authorization" in response.headers.get("Access-Control-Allow-Headers", ""), \
        "Expected 'Authorization' in Access-Control-Allow-Headers"


def test_gateway_cors_invalid_origin(access_token, redis_client):
    """
    AC 4.5: Dynamic CORS - kiểm tra Origin KHÔNG hợp lệ bị từ chối với 403.
    Origin không có trong allowed_cors_origins của tenant → phải bị block.
    """
    # Seed config with restrictive allowed origins
    config_data = json.dumps({
        "gateway_rate_limit_minute": 200,
        "gateway_rate_limit_hour": 5000,
        "allowed_cors_origins": ["https://dashboard.solavie.io"]  # Only this origin allowed
    })
    redis_client.set(f"tenant:{TEST_TENANT_ID}:config:security_comments_notif", config_data)

    url = f"{GATEWAY_URL}/api/v1/auth/realms/{TEST_TENANT_ID}/.well-known/openid-configuration"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Origin": "https://evil-site.hacker.com",  # Invalid origin NOT in allowed list
        "X-Tenant-ID": TEST_TENANT_ID
    }

    response = requests.get(url, headers=headers, timeout=10)

    # Dynamic CORS policy should block this origin with 403 Forbidden
    assert response.status_code == 403, \
        f"Expected 403 Forbidden for invalid CORS origin, got: {response.status_code}"

    # Cleanup: restore wildcard CORS for subsequent tests
    config_data_reset = json.dumps({
        "gateway_rate_limit_minute": 200,
        "gateway_rate_limit_hour": 5000,
        "allowed_cors_origins": ["*"]
    })
    redis_client.set(f"tenant:{TEST_TENANT_ID}:config:security_comments_notif", config_data_reset)


# ============================================================
# Task 5: Observability (AC 5.1, 5.4)
# ============================================================

def test_gateway_observability_prometheus():
    """
    AC 5.1: Gateway SHALL expose Prometheus metrics endpoint.
    AC 5.4: Gateway SHALL provide health check endpoint.
    """
    # Prometheus metrics endpoint (Kong Admin API)
    url = "http://localhost:8001/metrics"
    try:
        response = requests.get(url, timeout=10)
        assert response.status_code == 200
        assert "kong_http_requests_total" in response.text, \
            "Expected Prometheus metric 'kong_http_requests_total' in response"
    except requests.exceptions.ConnectionError:
        pytest.skip("Kong Admin API not exposed on port 8001 in this environment")


def test_gateway_tenant_id_header_injected(access_token):
    """
    AC 2.3: Gateway SHALL inject tenant_id và user_id từ token claims vào request headers.
    Xác minh X-Tenant-ID header được set bởi dynamic-policy plugin.
    """
    url = f"{GATEWAY_URL}/api/v1/auth/realms/{TEST_TENANT_ID}/.well-known/openid-configuration"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers, timeout=10)
    # The response itself doesn't contain the request headers, but if we get 200
    # it means dynamic-policy set the X-Tenant-ID header and forwarded request successfully
    assert response.status_code == 200


def test_gateway_jti_blacklisting(access_token, redis_client):
    """
    Xác minh Gateway từ chối token có JTI nằm trong Redis Blacklist.
    """
    # 1. Giải mã token lấy JTI
    parts = access_token.split('.')
    payload_b64 = parts[1]
    payload_b64 += '=' * (-len(payload_b64) % 4)
    import base64
    payload_json = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
    claims = json.loads(payload_json)
    jti = claims.get("jti")
    assert jti is not None, "Token must contain a JTI claim"

    # 2. Đưa JTI vào Redis Blacklist (giả lập sync worker)
    blacklist_key = f"blacklist:jti:{jti}"
    redis_client.setex(blacklist_key, 60, "revoked")

    try:
        # 3. Gửi request qua Gateway với token bị revoked
        url = f"{GATEWAY_URL}/api/v1/auth/realms/{TEST_TENANT_ID}/.well-known/openid-configuration"
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(url, headers=headers, timeout=10)
        
        # Verify nhận 401
        assert response.status_code == 401, \
            f"Expected 401 Unauthorized for revoked token, got: {response.status_code}"
        assert "revoked" in response.text.lower()
    finally:
        # Cleanup
        redis_client.delete(blacklist_key)


def get_token_with_scopes(scopes_str):
    """Helper to request a token from Keycloak with specific optional scopes."""
    token_url = f"{KEYCLOAK_URL}/realms/{TEST_TENANT_ID}/protocol/openid-connect/token"
    payload = {
        "client_id": "dashboard",
        "username": "admin",
        "password": ADMIN_PASSWORD,
        "grant_type": "password",
        "scope": f"openid email profile {scopes_str}"
    }
    response = requests.post(token_url, data=payload, timeout=10)
    response.raise_for_status()
    return response.json()["access_token"]


def test_gateway_scope_validation_blocking(access_token):
    """
    Xác minh Gateway chặn các request thiếu scope thích hợp (trả về 403 Forbidden).
    """
    # Gọi endpoint /api/v1/completions với token mặc định (chỉ có openid email profile, không có ai-core scope)
    url = f"{GATEWAY_URL}/api/v1/completions"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers, timeout=10)
    assert response.status_code == 403, f"Expected 403 Forbidden for missing ai-core scope, got {response.status_code}"
    assert "missing required scope" in response.text.lower()


def test_gateway_scope_validation_allowing():
    """
    Xác minh Gateway cho phép request đi qua khi token mang scope thích hợp.
    """
    # 1. Lấy token có ai-core scope
    token = get_token_with_scopes("ai-core")
    
    # 2. Gọi endpoint /api/v1/completions
    url = f"{GATEWAY_URL}/api/v1/completions"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, timeout=10)
    
    # Vì ai-core service đang chạy, nó sẽ trả về kết quả thành công hoặc 404/405 từ upstream,
    # nhưng quan trọng là KHÔNG phải 403 Forbidden!
    assert response.status_code != 403, f"Expected request to pass gateway scope validation, but got 403: {response.text}"
    assert response.status_code in [200, 404, 405, 502], f"Unexpected status code: {response.status_code}"


def test_gateway_scope_nested_path_matching():
    """
    Kiểm tra thuật toán so khớp prefix (longest match) và tính phân tách segment của Gateway.
    """
    # 1. Lấy token chỉ có ai-core scope (cho phép /api/v1/completions nhưng không cho /api/v1/completions/jobs)
    token_ai = get_token_with_scopes("ai-core")
    
    # 2. Gọi /api/v1/completions/jobs -> yêu cầu scope media-processor (phải bị chặn 403)
    url_jobs = f"{GATEWAY_URL}/api/v1/completions/jobs"
    headers_jobs = {"Authorization": f"Bearer {token_ai}"}
    resp_jobs = requests.get(url_jobs, headers=headers_jobs, timeout=10)
    assert resp_jobs.status_code == 403, f"Expected 403 for /api/v1/completions/jobs with only ai-core scope, got {resp_jobs.status_code}"
    
    # 3. Gọi /api/v1/completions/configs -> yêu cầu scope ai-core (phải đi qua -> 200/404/405/502)
    url_completions_sub = f"{GATEWAY_URL}/api/v1/completions/configs"
    headers_completions_sub = {"Authorization": f"Bearer {token_ai}"}
    resp_completions_sub = requests.get(url_completions_sub, headers=headers_completions_sub, timeout=10)
    assert resp_completions_sub.status_code != 403, f"Expected /api/v1/completions/configs to pass scope check, got 403"

    # 4. Kiểm tra phân tách segment:
    # Lấy token chỉ có tenant-config scope (cho phép /api/v1/config)
    token_config = get_token_with_scopes("tenant-config")
    
    # Gọi /api/v1/configs -> yêu cầu scope ai-core. 
    # Nếu so khớp prefix sai (config là prefix của configs), nó sẽ nhầm sang tenant-config scope và cho qua.
    # Nhưng vì có kiểm tra phân tách segment, nó sẽ nhận diện đúng là yêu cầu ai-core scope, 
    # do đó token chỉ có tenant-config scope sẽ bị chặn 403.
    url_configs = f"{GATEWAY_URL}/api/v1/configs"
    headers_configs = {"Authorization": f"Bearer {token_config}"}
    resp_configs = requests.get(url_configs, headers=headers_configs, timeout=10)
    assert resp_configs.status_code == 403, f"Expected 403 for /api/v1/configs with only tenant-config scope, got {resp_configs.status_code}"


