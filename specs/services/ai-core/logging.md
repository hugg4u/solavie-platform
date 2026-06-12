# Logging & Observability — AI Core Service

## Log Configuration

### Format: Structured JSON
```json
{
  "timestamp": "2026-06-04T10:30:00.123Z",
  "level": "info",
  "service": "ai-core",
  "trace_id": "abc123def456",
  "span_id": "span789",
  "tenant_id": "tenant-uuid",
  "message": "LLM completion successful",
  "context": {
    "use_case": "chatbot",
    "model": "gpt-4o-mini",
    "provider": "openai",
    "latency_ms": 450,
    "prompt_tokens": 200,
    "completion_tokens": 80,
    "cost_usd": 0.00009,
    "cache_hit": true,
    "is_fallback": false,
    "pii_masked_keys": ["[PHONE_1]", "[EMAIL_1]"],
    "nli_grounding_score": 0.94,
    "nli_status": "entailment",
    "agent_iterations": 2,
    "tools_executed": ["knowledge_base_search"]
  }
}
```

### Semantic Cache Log Format (MỚI)
```json
{
  "timestamp": "2026-06-11T11:20:00.123Z",
  "level": "info",
  "service": "ai-core",
  "trace_id": "abc123def456",
  "tenant_id": "tenant-uuid",
  "message": "Semantic cache query result",
  "context": {
    "use_case": "chatbot",
    "question": "giá lắp điện mặt trời là bao nhiêu",
    "question_hash": "md5_hash_value",
    "similarity_score": 0.954,
    "cache_hit": true,
    "latency_ms": 8
  }
}
```

```json
{
  "timestamp": "2026-06-11T11:20:01.123Z",
  "level": "info",
  "service": "ai-core",
  "trace_id": "abc123def456",
  "tenant_id": "tenant-uuid",
  "message": "Semantic cache query result",
  "context": {
    "use_case": "chatbot",
    "question": "pin mặt trời bảo hành bao lâu",
    "question_hash": "md5_hash_value_2",
    "similarity_score": 0.721,
    "cache_hit": false,
    "latency_ms": 12
  }
}
```

```json
{
  "timestamp": "2026-06-11T11:20:05.123Z",
  "level": "error",
  "service": "ai-core",
  "trace_id": "abc123def456",
  "tenant_id": "tenant-uuid",
  "message": "Failed to write response to semantic cache",
  "action": "cache_write_error",
  "context": {
    "use_case": "chatbot",
    "question_hash": "md5_hash_value_2",
    "error_message": "Redis connection timed out"
  }
}
```

### Log Levels
| Level | Khi nào dùng | Ví dụ |
|-------|-------------|-------|
| ERROR | LLM call fail, circuit breaker trip, all providers down | `"Provider openai timeout after 10s"` |
| WARN | Fallback triggered, quota approaching, high latency | `"Fallback to anthropic, openai circuit open"` |
| INFO | Request completed, model resolved, cache hit/miss | `"Completion: chatbot, gpt-4o-mini, 450ms"` |
| DEBUG | Full prompt content, raw response, optimization steps | `"Token optimization: 2000 → 800 tokens"` |

### Sensitive Data Rules
- NEVER log full prompt content ở level INFO (chỉ DEBUG)
- NEVER log API keys
- Log tenant_id nhưng KHÔNG log user PII
- Truncate long content (max 200 chars in logs)

## OpenTelemetry SDK Config

```python
# Python: opentelemetry setup
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer

# Traces
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="otel-collector:4317"))
)

# Metrics
metrics.set_meter_provider(MeterProvider(
    metric_readers=[PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint="otel-collector:4317"),
        export_interval_millis=15000
    )]
))

# Auto-instrument FastAPI + gRPC
FastAPIInstrumentor.instrument_app(app)
GrpcInstrumentorServer().instrument()
```

## Trace Spans

```
[AI Core Request] (root span from caller)
├── [validate_request] — 1ms
├── [resolve_model] — 2ms (DB lookup if tenant config)
├── [guardrail_input_pii_tokenization] — 2ms (Regex PII de-id)
├── [token_optimization] — 5-50ms
│   ├── [check_prompt_cache] — 1ms (Redis)
│   ├── [compress_history] — 20ms (if needed, calls LLM)
│   └── [extract_relevant] — 5ms
├── [agent_react_loop] (LangGraph Orchestration) — 300-3000ms
│   ├── [iteration_1_reason] — 300ms (LLM call with tokenized prompt)
│   ├── [iteration_1_execute_tools] — 50-1000ms
│   │   ├── [check_tool_permission] — 3ms (Redis Keycloak matrix checking module:action)
│   │   ├── [check_rate_limit] — 1ms (Redis sliding window)
│   │   ├── [re_id_arguments_restore] — 1ms (Restore placeholders from local state pii_map)
│   │   └── [execute_tool_call: knowledge_base_search] — 50ms (HTTP call to kb service)
│   ├── [iteration_2_reason] — 300ms
│   └── ...
├── [guardrail_output_nli_validate] — 150ms (MNLI model inference)
├── [guardrail_output_pii_restore] — 1ms (Restore placeholders in response to real PII)
└── [log_usage] — 1ms (async, non-blocking)
```

## Prometheus Metrics

```python
# Custom metrics exposed at GET /metrics
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
ai_requests_total = Counter(
    "ai_core_requests_total",
    "Total AI Core requests",
    ["use_case", "model", "provider", "status"]  # status: success/error/fallback
)

ai_request_duration = Histogram(
    "ai_core_request_duration_seconds",
    "AI Core request duration",
    ["use_case", "model"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Token metrics
ai_tokens_total = Counter(
    "ai_core_tokens_total",
    "Total tokens used",
    ["tenant_id", "use_case", "model", "type"]  # type: prompt/completion
)

ai_cost_total = Counter(
    "ai_core_cost_usd_total",
    "Total cost in USD",
    ["tenant_id", "use_case", "model"]
)

# Cache metrics
ai_cache_hits = Counter(
    "ai_core_cache_hits_total",
    "Prompt cache hits",
    ["use_case"]
)

ai_cache_misses = Counter(
    "ai_core_cache_misses_total",
    "Prompt cache misses",
    ["use_case"]
)

# Semantic Cache metrics (MỚI)
ai_semantic_cache_hits = Counter(
    "ai_core_semantic_cache_hits_total",
    "Total semantic cache hits",
    ["tenant_id", "use_case"]
)

ai_semantic_cache_misses = Counter(
    "ai_core_semantic_cache_misses_total",
    "Total semantic cache misses",
    ["tenant_id", "use_case"]
)

ai_semantic_cache_similarity = Histogram(
    "ai_core_semantic_cache_similarity_score",
    "Semantic cache cosine similarity score distribution",
    ["tenant_id", "use_case"],
    buckets=[0.5, 0.7, 0.8, 0.85, 0.9, 0.92, 0.95, 0.98, 1.0]
)

# Circuit breaker
ai_circuit_breaker_state = Gauge(
    "ai_core_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half-open)",
    ["provider"]
)

ai_fallback_total = Counter(
    "ai_core_fallback_total",
    "Fallback invocations",
    ["primary_provider", "fallback_provider", "reason"]
)

# Confidence distribution (for chatbot)
ai_confidence_histogram = Histogram(
    "ai_core_confidence_score",
    "Confidence score distribution",
    ["use_case"],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# Guardrail & Safety metrics (MỚI)
ai_pii_tokens_generated_total = Counter(
    "ai_core_pii_tokens_total",
    "Total PII tokens generated by de-identification",
    ["tenant_id", "pii_type"]  # pii_type: email, phone, card
)

ai_nli_grounding_score = Histogram(
    "ai_core_nli_grounding_score",
    "NLI Entailment score distribution",
    ["tenant_id", "use_case"],
    buckets=[0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0]
)

ai_nli_violations_total = Counter(
    "ai_core_nli_violations_total",
    "Total NLI grounding validation violations (score < 0.80)",
    ["tenant_id", "use_case"]
)

ai_rag_similarity_score = Histogram(
    "ai_core_rag_similarity_score",
    "RAG document retrieval similarity score distribution",
    ["tenant_id", "source"],  # source: kb, etc.
    buckets=[0.1, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

ai_rate_limit_violations_total = Counter(
    "ai_core_rate_limit_violations_total",
    "Total rate limit violations blocked at gate",
    ["tenant_id", "tool_name"]
)
```

## Health Endpoints

```
GET /health   → {"status": "ok", "uptime": 3600}
GET /ready    → {"status": "ready", "providers": {"openai": "up", "anthropic": "up"}}
GET /metrics  → Prometheus format
```

## Alert Rules (specific to AI Core)

| Alert | Condition | Severity |
|-------|-----------|----------|
| AllProvidersDown | Both openai + anthropic circuit open | critical |
| HighFallbackRate | fallback_total/requests_total > 10% in 5m | warning |
| CostSpike | cost_usd_total rate > $10/hour | warning |
| HighLatency | p95 > 5s for chatbot use_case | warning |
| LowCacheHitRate | cache_hits / (hits + misses) < 20% | info |
| QuotaApproaching | tenant token usage > 80% monthly quota | info |
| HighSignatureFailures | sum(rate(ai_core_security_signature_failures_total[5m])) > 5 | critical (potential spoofing attempt or key mismatch) |
| HighPermissionDenied | sum(rate(ai_core_security_permission_denied_total[5m])) > 10 | warning (user accessing forbidden resources) |

## Zero-Trust Security Logs & Metrics

### Permission and Signature Failure Log Format
```json
{
  "timestamp": "2026-06-06T11:45:00.123Z",
  "level": "warn",
  "service": "ai-core",
  "trace_id": "xyz987lmn456",
  "tenant_id": "tenant-uuid",
  "user_id": "user-uuid",
  "message": "HMAC signature verification failed: signature mismatch",
  "context": {
    "client_ip": "192.168.1.102",
    "received_signature": "ab09c8f...",
    "expected_signature": "f2a3c7d..."
  }
}
```

```json
{
  "timestamp": "2026-06-06T11:46:12.456Z",
  "level": "warn",
  "service": "ai-core",
  "trace_id": "xyz987lmn456",
  "tenant_id": "tenant-uuid",
  "user_id": "user-uuid",
  "message": "Permission check failed: required 'ai-core:chats:create'",
  "context": {
    "user_permissions": ["ai-core:prompts:read", "ai-core:prompts:write"]
  }
}
```

### Zero-Trust Custom Metrics
```python
# Custom security metrics exposed at GET /metrics
ai_security_signature_failures_total = Counter(
    "ai_core_security_signature_failures_total",
    "Total HMAC signature validation failures",
    ["tenant_id", "client_ip"]
)

ai_security_permission_denied_total = Counter(
    "ai_core_security_permission_denied_total",
    "Total permission denied decisions at downstream guard",
    ["tenant_id", "required_permission"]
)
```

### Zero-Trust Service Registry Logs
Dịch vụ phải ghi log có cấu trúc cho các sự kiện vòng đời đăng ký dịch vụ:

```json
{
  "timestamp": "2026-06-09T17:40:00.123Z",
  "level": "info",
  "service": "ai-core",
  "message": "Service node registration completed",
  "action": "register", // register, heartbeat_success, heartbeat_failure, deregister
  "node_ip": "172.20.0.10",
  "node_port": 8000,
  "status": "success",
  "context": {
    "redis_key": "registry:service:ai-core"
  }
}
```




---

## Service Discovery Audit Logs (Structured JSON)
Mọi hoạt động đăng ký, heartbeat và hủy đăng ký phải xuất ra log JSON cấu trúc chuẩn:
*   **Log Register Success:**
    `{"timestamp": "ISO-8601", "level": "info", "service": "ai-core", "message": "Service node registration completed", "action": "register", "node_ip": "{ip}", "node_port": {port}, "status": "success"}`
*   **Log Deregister Success:**
    `{"timestamp": "ISO-8601", "level": "info", "service": "ai-core", "message": "Service node deregistration completed", "action": "deregister", "node_ip": "{ip}", "node_port": {port}, "status": "success"}`
*   **Log Heartbeat Failure:**
    `{"timestamp": "ISO-8601", "level": "warn", "service": "ai-core", "message": "Heartbeat failure: {error}", "action": "heartbeat_failure", "node_ip": "{ip}", "node_port": {port}, "status": "failure"}`
