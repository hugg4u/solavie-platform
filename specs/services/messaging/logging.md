# Logging & Observability — Messaging Service

## Log Format: Structured JSON
```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "info",
  "service": "messaging",
  "trace_id": "abc123",
  "tenant_id": "tenant-uuid",
  "message": "Message routed to chatbot",
  "context": {
    "conversation_id": "conv-uuid",
    "mode": "auto",
    "channel": "facebook",
    "routing_target": "chatbot",
    "latency_ms": 5
  }
}
```

## Log Levels
| Level | Khi nào | Ví dụ |
|-------|---------|-------|
| ERROR | Security shared secret configuration missing | `"GATEWAY_SIGNING_SECRET is not configured"` |
| ERROR | gRPC call to chatbot fail, Kafka consume error, DB write fail | `"gRPC chatbot timeout after 5s"` |
| WARN | Signature validation failure, permission denied, unauthorized access attempt | `"HMAC signature verification failed: signature mismatch"` |
| WARN | Handoff triggered, WebSocket disconnect, conversation auto-closed | `"Handoff: confidence 0.45"` |
| INFO | Message received, routed, reply sent, conversation created | `"New conversation created: fb_user_123"` |
| DEBUG | Full message content, gRPC request/response, WebSocket events | `"WS broadcast to 3 clients"` |

## OpenTelemetry: Same as Channel Connector (Node.js NestJS setup)

## Trace Spans
```
[Kafka Message Consumed]
├── [parse_event] — 1ms
├── [find_or_create_conversation] — 5ms (DB)
├── [save_message] — 3ms (DB)
├── [route_message] — varies
│   ├── [grpc_call_chatbot] — 500-2000ms (if auto mode)
│   └── [websocket_broadcast] — 1ms (if manual mode)
└── [update_conversation] — 2ms (DB)

[Agent Reply]
├── [save_message] — 3ms
├── [call_channel_connector] — 5ms (REST)
└── [websocket_broadcast] — 1ms
```

## Prometheus Metrics
```typescript
// Messages
messages_received_total: Counter ['channel', 'tenant_id']
messages_sent_total: Counter ['channel', 'sender_type'] // bot/agent
message_routing_duration: Histogram ['mode'] // auto/manual

// Conversations
conversations_active: Gauge ['tenant_id', 'mode']
conversations_created_total: Counter ['channel']
handoffs_total: Counter ['reason'] // low_confidence/sentiment/timeout

// WebSocket
websocket_connections_active: Gauge ['tenant_id']
websocket_messages_broadcast: Counter []

// gRPC to Chatbot
grpc_chatbot_duration: Histogram []
grpc_chatbot_errors_total: Counter ['error_type']

// Model Context Protocol (MCP)
messaging_mcp_connections_active: Gauge ['tenant_id']
messaging_mcp_requests_total: Counter ['tool_name', 'status'] // status: success/error
messaging_mcp_execution_duration_seconds: Histogram ['tool_name']
```


// Zero-Trust Security Metrics
messaging_security_signature_failures_total: Counter [tenant_id, client_ip]
messaging_security_permission_denied_total: Counter [tenant_id, required_permission]

## Health Endpoints
```
GET /health   → {"status": "ok"}
GET /ready    → {"status": "ready", "kafka": "connected", "grpc_chatbot": "connected", "websocket_clients": 42}
GET /metrics  → Prometheus format
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| HighSignatureFailures | sum(rate(messaging_security_signature_failures_total[5m])) > 5 | critical (potential spoofing attempt or key mismatch) |
| HighPermissionDenied | sum(rate(messaging_security_permission_denied_total[5m])) > 10 | warning (user accessing forbidden resources) |
| ChatbotGrpcDown | grpc_chatbot_errors > 5 in 1m | critical |
| HighHandoffRate | handoffs / messages > 50% in 30m | warning |
| KafkaConsumerLag | consumer lag > 500 for 5m | warning |
| WebSocketDisconnectSpike | disconnect rate > 20% in 5m | warning |
