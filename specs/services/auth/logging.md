# Logging & Observability — Auth Service (Keycloak)

## Log Configuration
Keycloak logs qua stdout (JSON format khi cấu hình `--log-format=json`):

```json
{
  "timestamp": "2026-06-08T10:30:00.123Z",
  "level": "INFO",
  "category": "org.keycloak.events",
  "message": "LOGIN",
  "context": {
    "realm": "solavie",
    "organization": "tenant-abc",
    "client_id": "dashboard",
    "user_id": "user-uuid",
    "ip_address": "192.168.1.100",
    "auth_method": "password",
    "session_id": "session-uuid"
  }
}
```

## Keycloak Event Types (auto-logged)
| Event | Khi nào | Severity |
|-------|---------|----------|
| LOGIN | User login thành công | INFO |
| LOGIN_ERROR | Login thất bại (wrong password, locked) | WARN |
| LOGOUT | User logout | INFO |
| REGISTER | User mới đăng ký | INFO |
| UPDATE_PASSWORD | Đổi mật khẩu | INFO |
| SEND_RESET_PASSWORD | Yêu cầu reset password | INFO |
| TOKEN_EXCHANGE | Token refresh | DEBUG |
| CLIENT_LOGIN | Service account login | DEBUG |
| PERMISSION_TOKEN | Permission check | DEBUG |
| ORG_MEMBER_ADDED | Thành viên được thêm vào Organization | INFO |
| ORG_MEMBER_REMOVED | Thành viên bị xóa khỏi Organization | INFO |

## Keycloak Metrics (built-in khi KC_METRICS_ENABLED=true)
```
# Exposed at /metrics (Prometheus format)
keycloak_logins_total: Counter [realm, client_id, provider]
keycloak_login_errors_total: Counter [realm, client_id, error]
keycloak_registrations_total: Counter [realm, client_id]
keycloak_active_sessions: Gauge [realm]
keycloak_token_issued_total: Counter [realm, client_id]
keycloak_token_refresh_total: Counter [realm]
keycloak_request_duration: Histogram [method, route]
```


// Zero-Trust Security Metrics
auth_security_signature_failures_total: Counter [tenant_id, client_ip]
auth_security_permission_denied_total: Counter [tenant_id, required_permission]

## Health Endpoints
```
GET /health/ready  → Keycloak readiness (DB connected, realms loaded)
GET /health/live   → Keycloak liveness
GET /metrics       → Prometheus metrics
```

## Sync Worker Logs
Auth Sync Worker chạy bằng Python xuất bản log stdout ở định dạng cấu trúc JSON:
```json
{
  "timestamp": "2026-06-08 01:50:00,123",
  "level": "INFO",
  "category": "solavie.auth.sync_worker",
  "message": "Updating organization 'tenant-test-uuid' security attributes with passwordPolicy length(12) and failureFactor(5)"
}
```

## Alert Rules
| Alert | Condition | Severity | Action/Description |
|-------|-----------|----------|-------------------|
| HighSignatureFailures | sum(rate(auth_security_signature_failures_total[5m])) > 5 | critical | potential spoofing attempt or key mismatch |
| HighPermissionDenied | sum(rate(auth_security_permission_denied_total[5m])) > 10 | warning | user accessing forbidden resources |
| LoginErrorSpike | login_errors > 50 in 5m | critical | brute force attack verification |
| KeycloakDown | health/ready fail > 30s | critical | check keycloak container status |
| SessionOverload | active_sessions > 10000 | warning | review resource consumption |
| TokenRefreshFailing | token errors > 10 in 5m | warning | check token exchange logic |
| OrganizationCreationFail | admin API errors | critical | check realm settings and admin credentials |
| SyncWorkerFailure | sum(rate(sync_worker_errors_total[5m])) > 1 | critical | check Sync Worker process logs |
| SyncWorkerKafkaLagHigh | `sum(auth_sync_worker_kafka_consumer_lag{topic="config.updates"}) > 100` | warning | check Kafka consumer partition lag |
| SyncWorkerKafkaProduceErrors | `sum(rate(auth_sync_worker_kafka_produced_errors_total[5m])) > 1` | critical | check Kafka connection and authorization ACLs for auth.events.user |





---

## Service Discovery Audit Logs (Structured JSON)
Mọi hoạt động đăng ký, heartbeat và hủy đăng ký phải xuất ra log JSON cấu trúc chuẩn:
*   **Log Register Success:**
    `{"timestamp": "ISO-8601", "level": "info", "service": "auth", "message": "Service node registration completed", "action": "register", "node_ip": "{ip}", "node_port": {port}, "status": "success"}`
*   **Log Deregister Success:**
    `{"timestamp": "ISO-8601", "level": "info", "service": "auth", "message": "Service node deregistration completed", "action": "deregister", "node_ip": "{ip}", "node_port": {port}, "status": "success"}`
*   **Log Heartbeat Failure:**
    `{"timestamp": "ISO-8601", "level": "warn", "service": "auth", "message": "Heartbeat failure: {error}", "action": "heartbeat_failure", "node_ip": "{ip}", "node_port": {port}, "status": "failure"}`
