# Logging & Observability — Channel Connector Service

## Log Configuration

### Format: Structured JSON
```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "info",
  "service": "channel-connector",
  "trace_id": "abc123",
  "span_id": "span456",
  "tenant_id": "tenant-uuid",
  "message": "Webhook received",
  "context": {
    "platform": "facebook",
    "event_type": "message.received",
    "sender_id": "fb_user_123",
    "idempotency_key": "evt_abc",
    "processing_time_ms": 15
  }
}
```

### Log Levels
| Level | Khi nào | Ví dụ |
|-------|---------|-------|
| ERROR | Security shared secret configuration missing | `"GATEWAY_SIGNING_SECRET is not configured"` |
| ERROR | Webhook verify fail, send message fail after retries, token refresh fail | `"Facebook send failed after 3 retries"` |
| WARN | Signature validation failure, permission denied, unauthorized access attempt | `"HMAC signature verification failed: signature mismatch"` |
| WARN | Circuit breaker trip, token expiring soon, retry attempt | `"Zalo circuit breaker OPEN"` |
| INFO | Webhook received, message sent, token refreshed | `"Message sent to facebook, delivery: ok"` |
| DEBUG | Raw webhook payload, normalized message, API response | `"Webhook payload: {truncated}"` |

### Sensitive Data Rules
- NEVER log access_tokens hoặc refresh_tokens
- Log sender_id nhưng KHÔNG log message content ở INFO
- Log platform_message_id cho tracing

## OpenTelemetry SDK Config

```typescript
// Node.js: @opentelemetry/sdk-node
import { NodeSDK } from '@opentelemetry/sdk-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-grpc';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-grpc';
import { NestInstrumentation } from '@opentelemetry/instrumentation-nestjs-core';
import { HttpInstrumentation } from '@opentelemetry/instrumentation-http';
import { KafkaJsInstrumentation } from 'opentelemetry-instrumentation-kafkajs';

const sdk = new NodeSDK({
  traceExporter: new OTLPTraceExporter({ url: 'otel-collector:4317' }),
  metricReader: new PeriodicExportingMetricReader({
    exporter: new OTLPMetricExporter({ url: 'otel-collector:4317' }),
    exportIntervalMillis: 15000,
  }),
  instrumentations: [
    new NestInstrumentation(),
    new HttpInstrumentation(),
    new KafkaJsInstrumentation(),
  ],
});
sdk.start();
```

## Trace Spans

```
[Webhook Received] (root)
├── [verify_signature] — 1ms
├── [check_idempotency] — 2ms (Redis lookup)
├── [normalize_message] — 1ms
├── [publish_kafka] — 5ms
└── [respond_200] — 0ms

[Send Message] (root)
├── [convert_to_platform_format] — 1ms
├── [call_platform_api] — 200-500ms ← external call
│   └── [circuit_breaker_check] — 0ms
├── [publish_sent_event] — 5ms
└── [log_delivery_status] — 1ms

[Token Refresh] (cron job)
├── [check_expiring_tokens] — 5ms (DB query)
├── [refresh_token_api_call] — 300ms (per token)
└── [update_token_db] — 5ms
```

## Prometheus Metrics

```typescript
// prom-client metrics
import { Counter, Histogram, Gauge } from 'prom-client';

// Webhook metrics
const webhooksReceived = new Counter({
  name: 'channel_connector_webhooks_received_total',
  help: 'Total webhooks received',
  labelNames: ['platform', 'event_type', 'status'], // status: processed/duplicate/invalid
});

const webhookProcessingDuration = new Histogram({
  name: 'channel_connector_webhook_processing_seconds',
  help: 'Webhook processing duration',
  labelNames: ['platform'],
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.5, 1.0],
});

// Outbound message metrics
const messagesSent = new Counter({
  name: 'channel_connector_messages_sent_total',
  help: 'Total messages sent to platforms',
  labelNames: ['platform', 'status'], // status: delivered/failed
});

const sendLatency = new Histogram({
  name: 'channel_connector_send_latency_seconds',
  help: 'Platform API call latency',
  labelNames: ['platform'],
  buckets: [0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
});

// Circuit breaker
const circuitBreakerState = new Gauge({
  name: 'channel_connector_circuit_breaker_state',
  help: 'Circuit breaker state per platform (0=closed, 1=open, 2=half-open)',
  labelNames: ['platform'],
});

// Token health
const tokenExpiresIn = new Gauge({
  name: 'channel_connector_token_expires_in_seconds',
  help: 'Seconds until token expires',
  labelNames: ['platform', 'tenant_id'],
});

const tokenRefreshTotal = new Counter({
  name: 'channel_connector_token_refresh_total',
  help: 'Token refresh attempts',
  labelNames: ['platform', 'status'], // status: success/failed
});

// Kafka publish
const kafkaPublishTotal = new Counter({
  name: 'channel_connector_kafka_publish_total',
  help: 'Kafka events published',
  labelNames: ['topic', 'status'],
});
```


// Zero-Trust Security Metrics
channel_connector_security_signature_failures_total: Counter [tenant_id, client_ip]
channel_connector_security_permission_denied_total: Counter [tenant_id, required_permission]

## Health Endpoints

```
GET /health   → {"status": "ok", "uptime": 3600}
GET /ready    → {"status": "ready", "platforms": {"facebook": "connected", "zalo": "connected", "tiktok": "connected"}}
GET /metrics  → Prometheus format
```

## Alert Rules

| Alert | Condition | Severity |
|-------|-----------|----------|
| HighSignatureFailures | sum(rate(channel_connector_security_signature_failures_total[5m])) > 5 | critical (potential spoofing attempt or key mismatch) |
| HighPermissionDenied | sum(rate(channel_connector_security_permission_denied_total[5m])) > 10 | warning (user accessing forbidden resources) |
| PlatformDisconnected | circuit_breaker_state == 1 for > 5m | critical |
| HighSendFailRate | messages_sent{status=failed} / total > 10% | warning |
| TokenRefreshFailing | token_refresh{status=failed} > 0 for 10m | critical |
| WebhookProcessingSlow | webhook_processing p95 > 1s | warning |
| KafkaPublishFailing | kafka_publish{status=failed} > 0 for 5m | critical |

---

## Service Discovery Audit Logs

Khi `ServiceRegistryClient` thực hiện đăng ký hoặc hủy đăng ký trên Redis, nó phải ghi nhận log có cấu trúc JSON như sau:

### 1. Log Đăng ký Thành công (register)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "channel-connector",
  "message": "Service node registration completed",
  "action": "register",
  "node_ip": "172.20.0.10",
  "node_port": 3001,
  "status": "success",
  "context": {
    "redis_key": "registry:service:channel-connector"
  }
}
```

### 2. Log Hủy Đăng ký Thành công (deregister)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "channel-connector",
  "message": "Service node deregistration completed",
  "action": "deregister",
  "node_ip": "172.20.0.10",
  "node_port": 3001,
  "status": "success",
  "context": {
    "redis_key": "registry:service:channel-connector"
  }
}
```
