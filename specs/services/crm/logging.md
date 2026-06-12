# Logging & Observability — CRM Service

## Log Format: Structured JSON
```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "info",
  "service": "crm",
  "trace_id": "abc123",
  "tenant_id": "tenant-uuid",
  "message": "Lead score updated",
  "context": {
    "contact_id": "contact-uuid",
    "old_score": 45,
    "new_score": 72,
    "change": 27,
    "scoring_factors": ["high_message_frequency", "product_interest"]
  }
}
```

## Log Levels
| Level | Khi nào | Ví dụ |
|-------|---------|-------|
| ERROR | Security shared secret configuration missing | `"GATEWAY_SIGNING_SECRET is not configured"` |
| ERROR | DB write fail, AI Core scoring fail, merge conflict | `"Lead scoring failed: AI Core timeout"` |
| WARN | Signature validation failure, permission denied, unauthorized access attempt | `"HMAC signature verification failed: signature mismatch"` |
| WARN | Duplicate detected, score spike (possible anomaly) | `"Potential duplicate: same phone across 2 contacts"` |
| INFO | Contact created, score updated, segment recalculated, merge completed | `"Contact merged: 2 records → 1"` |
| DEBUG | Scoring factors detail, segment filter queries, merge resolution | `"Segment 'hot-leads' recalculated: 45 contacts"` |

## Prometheus Metrics
```typescript
crm_contacts_total: Gauge [tenant_id]
crm_contacts_created_total: Counter [channel]
crm_lead_score_updates_total: Counter [tenant_id]
crm_lead_score_distribution: Histogram [buckets: 0,10,20,...,100]
crm_duplicates_detected_total: Counter []
crm_merges_completed_total: Counter []
crm_segments_recalculated_total: Counter []
crm_ai_scoring_duration: Histogram []
crm_kafka_events_consumed_total: Counter [topic]
crm_mcp_tool_executions_total: Counter [tenant_id, server_name, tool_name, status]
crm_mcp_tool_execution_duration_seconds: Histogram [tenant_id, server_name, tool_name]
crm_mcp_security_violations_total: Counter [tenant_id, reason]

// Proposal PDF Metrics
crm_proposal_pdf_generated_total: Counter [tenant_id, status]
crm_proposal_pdf_duration_seconds: Histogram [tenant_id]

// Zero-Trust Security Metrics
crm_security_signature_failures_total: Counter [tenant_id, client_ip]
crm_security_permission_denied_total: Counter [tenant_id, required_permission]
```


## Health Endpoints
```
GET /health   → {"status": "ok"}
GET /ready    → {"status": "ready", "postgres": "connected", "kafka": "connected"}
GET /metrics  → Prometheus format
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| HighSignatureFailures | sum(rate(crm_security_signature_failures_total[5m])) > 5 | critical (potential spoofing attempt or key mismatch) |
| HighPermissionDenied | sum(rate(crm_security_permission_denied_total[5m])) > 10 | warning (user accessing forbidden resources) |
| ScoringFailing | ai_scoring errors > 5 in 10m | warning |
| HighDuplicateRate | duplicates_detected > 20 in 1h | info |
| KafkaConsumerLag | lag > 500 for 5m | warning |
| MCPSecurityBreach | crm_mcp_security_violations_total > 0 | critical |
| MCPExecutionFailure | crm_mcp_tool_executions_total{status="error"} > 5 in 5m | warning |
| ProposalPDFGenerationFailure | sum(rate(crm_proposal_pdf_generated_total{status="error"}[5m])) / sum(rate(crm_proposal_pdf_generated_total[5m])) > 0.05 or histogram_quantile(0.95, sum(rate(crm_proposal_pdf_duration_seconds_bucket[5m])) by (le)) > 10 | warning (PDF error rate > 5% or p95 latency > 10s) |

---

## Service Discovery Audit Logs

Khi `ServiceRegistryClient` thực hiện đăng ký hoặc hủy đăng ký trên Redis, nó phải ghi nhận log có cấu trúc JSON như sau:

### 1. Log Đăng ký Thành công (register)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "crm",
  "message": "Service node registration completed",
  "action": "register",
  "node_ip": "172.20.0.10",
  "node_port": 3003,
  "status": "success",
  "context": {
    "redis_key": "registry:service:crm"
  }
}
```

### 2. Log Hủy Đăng ký Thành công (deregister)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "crm",
  "message": "Service node deregistration completed",
  "action": "deregister",
  "node_ip": "172.20.0.10",
  "node_port": 3003,
  "status": "success",
  "context": {
    "redis_key": "registry:service:crm"
  }
}
```

### 3. Log Proposal PDF Generation
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "crm",
  "message": "Proposal PDF generated and uploaded to DMS",
  "action": "proposal_pdf_generated",
  "tenant_id": "tenant-uuid",
  "context": {
    "proposal_id": "proposal-uuid",
    "dms_file_id": "dms-file-uuid",
    "pdf_size_kb": 245,
    "duration_ms": 1230
  }
}
```

### 4. Log MCP Tool Call Execution (với Security Cross-Tenant validation)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "crm",
  "message": "MCP tool call execution completed",
  "action": "mcp_tool_execution",
  "tenant_id": "tenant-uuid",
  "context": {
    "server_name": "solar_calc",
    "tool_name": "get_proposal_preview",
    "input_params_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "validation_result": "valid"
  }
}
```

### 5. Log MCP Tool Call Cross-Tenant Security Block
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "warn",
  "service": "crm",
  "message": "MCP tool call blocked: cross-tenant access attempt detected",
  "action": "mcp_tool_blocked",
  "tenant_id": "tenant-uuid-authorized",
  "context": {
    "requested_tenant_id": "tenant-uuid-target-victim",
    "server_name": "crm",
    "tool_name": "get_contact_360",
    "validation_result": "cross-tenant-blocked"
  }
}
```
