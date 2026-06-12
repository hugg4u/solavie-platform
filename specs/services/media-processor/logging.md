# Logging — Media-processor Service


---

## Service Discovery Audit Logs (Structured JSON)
Mọi hoạt động đăng ký, heartbeat và hủy đăng ký phải xuất ra log JSON cấu trúc chuẩn:
*   **Log Register Success:**
    `{"timestamp": "ISO-8601", "level": "info", "service": "media-processor", "message": "Service node registration completed", "action": "register", "node_ip": "{ip}", "node_port": {port}, "status": "success"}`
*   **Log Deregister Success:**
    `{"timestamp": "ISO-8601", "level": "info", "service": "media-processor", "message": "Service node deregistration completed", "action": "deregister", "node_ip": "{ip}", "node_port": {port}, "status": "success"}`
*   **Log Heartbeat Failure:**
    `{"timestamp": "ISO-8601", "level": "warn", "service": "media-processor", "message": "Heartbeat failure: {error}", "action": "heartbeat_failure", "node_ip": "{ip}", "node_port": {port}, "status": "failure"}`
