# Logging & Observability — Content Service

## Log Format: Structured JSON
```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "info",
  "service": "content",
  "trace_id": "abc123",
  "tenant_id": "tenant-uuid",
  "message": "Content generated",
  "context": {
    "post_id": "post-uuid",
    "platform": "facebook",
    "quality_score": 0.82,
    "generation_time_ms": 3500,
    "model_used": "claude-sonnet",
    "status": "draft"
  }
}
```

## Log Levels
| Level | Khi nào | Ví dụ |
|-------|---------|-------|
| ERROR | Security shared secret configuration missing | `"GATEWAY_SIGNING_SECRET is not configured"` |
| ERROR | AI Core fail, KB unreachable, DB write fail | `"Content generation failed: AI Core timeout"` |
| WARN | Signature validation failure, permission denied, unauthorized access attempt | `"HMAC signature verification failed: signature mismatch"` |
| WARN | Low quality score, regeneration needed | `"Quality score 0.55, needs revision"` |
| INFO | Content generated, approved, published, rejected | `"Post approved by manager, scheduling..."` |
| DEBUG | Full generated content, RAG context, quality check details | `"Quality issues: [brand_voice_mismatch]"` |

## Prometheus Metrics
```python
content_generated_total: Counter ['platform', 'status'] # draft/approved/rejected/published
content_generation_duration: Histogram ['platform']
content_quality_score: Histogram [buckets: 0.0-1.0]
content_approval_time: Histogram [] # time from draft to approved
content_regeneration_total: Counter [] # quality < 0.7 → regenerate
content_published_total: Counter ['platform']

# Model Context Protocol (MCP) Metrics
content_mcp_connections_active: Gauge [tenant_id]
content_mcp_requests_total: Counter [tool_name, status] # status: success/error
content_mcp_execution_duration_seconds: Histogram [tool_name]

// Zero-Trust Security Metrics
content_security_signature_failures_total: Counter [tenant_id, client_ip]
content_security_permission_denied_total: Counter [tenant_id, required_permission]
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| HighSignatureFailures | sum(rate(content_security_signature_failures_total[5m])) > 5 | critical (potential spoofing attempt or key mismatch) |
| HighPermissionDenied | sum(rate(content_security_permission_denied_total[5m])) > 10 | warning (user accessing forbidden resources) |
| GenerationFailing | generated{status=error} > 3 in 10m | warning |
| LowQualityRate | quality_score < 0.7 for > 50% in 1h | info |
| ApprovalBacklog | pending approvals > 20 | info |

---

## Service Discovery Audit Logs

Khi `ServiceRegistryClient` thực hiện đăng ký hoặc hủy đăng ký trên Redis, nó phải ghi nhận log có cấu trúc JSON như sau:

### 1. Log Đăng ký Thành công (register)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "content",
  "message": "Service node registration completed",
  "action": "register",
  "node_ip": "172.20.0.10",
  "node_port": 8002,
  "status": "success",
  "context": {
    "redis_key": "registry:service:content"
  }
}
```

### 2. Log Hủy Đăng ký Thành công (deregister)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "content",
  "message": "Service node deregistration completed",
  "action": "deregister",
  "node_ip": "172.20.0.10",
  "node_port": 8002,
  "status": "success",
  "context": {
    "redis_key": "registry:service:content"
  }
}
```
