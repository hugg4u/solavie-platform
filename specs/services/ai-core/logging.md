# Logging & Observability — AI Core Service

## Log Configuration

### Format: Structured JSON
```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
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
    "is_fallback": false
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
├── [token_optimization] — 5-50ms
│   ├── [check_prompt_cache] — 1ms (Redis)
│   ├── [compress_history] — 20ms (if needed, calls LLM)
│   └── [extract_relevant] — 5ms
├── [call_llm] — 300-1500ms ← bottleneck
│   ├── [provider: openai] — actual LLM call
│   └── [provider: anthropic] — if fallback
├── [post_process] — 2ms
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
