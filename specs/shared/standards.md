# Shared Standards — Marketing Platform

Tài liệu chuẩn chung áp dụng cho TẤT CẢ services. Mỗi team phải tuân theo để đảm bảo nhất quán toàn hệ thống.

## 1. Unified Confidence Scale

Tất cả AI decisions dùng chung thang điểm confidence (0.0 - 1.0):

| Range | Mức | Ý nghĩa | Action được phép |
|-------|-----|---------|------------------|
| 0.85 - 1.0 | Very High | Chắc chắn cao | Destructive actions (hide comment, delete, auto-publish) |
| 0.70 - 0.85 | High | Đủ tin cậy | Safe auto-actions (reply, tag, classify) |
| 0.50 - 0.70 | Medium | Không chắc | Escalate cho human review |
| 0.0 - 0.50 | Low | Không tin cậy | Reject / Handoff ngay, KHÔNG auto-action |

**Áp dụng cụ thể:**

| Service | Decision | Threshold |
|---------|----------|-----------|
| Chatbot | Reply tự động | >= 0.70 |
| Chatbot | Handoff | < 0.70 |
| Comment Manager | Hide spam (destructive) | >= 0.85 |
| Comment Manager | Auto-reply question | >= 0.70 |
| Comment Manager | Escalate negative | >= 0.60 |
| CRM | Auto-tag | >= 0.70 |
| Content | Quality pass | >= 0.70 |

## 2. Handoff / Escalation Standard

**Định nghĩa thống nhất:**
- **Handoff**: Chuyển conversation từ bot sang human agent (Chatbot/Messaging)
- **Escalate**: Đẩy 1 task/issue lên human để xử lý (Comment Manager, CRM)

**Handoff triggers (Chatbot → Human):**
1. Confidence < 0.70
2. Sentiment = angry/strongly negative
3. Response chứa "không biết"/"don't know" patterns
4. No relevant docs found (RAG score < 0.5)
5. AI Core timeout (> 5s)
6. Explicit customer request ("gặp nhân viên")

**Escalation triggers:**
- Comment Manager: comment phân loại negative (>= 0.60)
- CRM: lead score thay đổi > 10 điểm

Mọi handoff/escalation đều publish Kafka event → Notification Service.

## 3. Rate Limiting Standard

**Algorithm:** Token Bucket (per tenant + per resource)

**Implementation:**
- Backend: Redis (atomic INCR + TTL)
- Key format: `ratelimit:{tenant_id}:{resource}:{window}`
- Khi exceed → return HTTP 429 + header `Retry-After: {seconds}`

**Limits per tier:**

| Resource | Free | Standard | Enterprise |
|----------|------|----------|------------|
| API requests/min | 60 | 200 | 1000 |
| AI Core: web_search/hour | 20 | 50 | 200 |
| AI Core: generate_content/hour | 5 | 20 | 100 |
| AI Core: knowledge_base_search/hour | 100 | 500 | 5000 |
| Channel send/hour (per platform limit) | 200 | 200 | 200 |

**Khi exceed:**
- Sync calls: return 429 + Retry-After
- Agent tool calls: agent nhận structured error, tự quyết định (skip tool hoặc inform user)

## 4. Structured Error Standard

Tất cả service-to-service errors dùng format chung:

```json
{
  "status": "error",
  "code": 503,
  "error_type": "service_unavailable",
  "message": "Knowledge Base timeout",
  "retriable": true,
  "retry_after_ms": 1000,
  "trace_id": "abc123"
}
```

**Error types:**
| Type | HTTP | Retriable |
|------|------|-----------|
| validation_error | 400 | No |
| unauthorized | 401 | No |
| forbidden | 403 | No |
| not_found | 404 | No |
| rate_limited | 429 | Yes (after Retry-After) |
| service_unavailable | 503 | Yes |
| timeout | 504 | Yes |
| internal_error | 500 | Maybe |

**AI Core Tool Executor:** Tool errors PHẢI trả structured object, KHÔNG trả string để LLM không hiểu nhầm là data.

## 5. Audit Logging Standard

**Mọi destructive/sensitive action PHẢI ghi audit log.**

Actions cần audit:
- Hide/delete comment
- Merge contacts
- Delete document
- Publish/schedule post
- Change conversation mode (handoff)
- Approve/reject content
- Modify channel tokens
- Change tenant config

**Audit log format (shared table hoặc Kafka topic `audit.events`):**

```json
{
  "audit_id": "uuid",
  "tenant_id": "uuid",
  "actor_type": "user|system|ai_agent",
  "actor_id": "uuid",
  "action": "comment.hide",
  "resource_type": "comment",
  "resource_id": "uuid",
  "before": {},
  "after": {},
  "reason": "spam detected, confidence 0.92",
  "trace_id": "abc123",
  "timestamp": "ISO8601"
}
```

Audit logs lưu tối thiểu 1 năm (compliance).

## 6. Saga Pattern Standard (Distributed Transactions)

**Áp dụng cho flows spanning nhiều services:**

### Saga 1: Chatbot Reply Flow
```
1. Messaging: save incoming message
2. Chatbot: generate reply
3. Channel Connector: send to platform
   - Success → save outgoing message, done
   - Fail → compensating: mark message failed, retry queue, notify agent
```

### Saga 2: Content Publish Flow
```
1. Content: mark approved
2. Scheduler: create schedule
3. Channel Connector: publish at time
   - Success → mark published, update analytics
   - Fail → retry 3x, then mark failed, notify creator, rollback schedule
```

**Nguyên tắc:**
- Mỗi step publish event khi done
- Mỗi step có compensating action khi fail
- Dùng Kafka cho reliability (at-least-once delivery)
- Idempotency keys để tránh double-processing

## 7. Health Check Standard

Mọi service expose:
```
GET /health   → {"status": "ok", "uptime": seconds}          # Liveness
GET /ready     → {"status": "ready", "dependencies": {...}}   # Readiness
GET /metrics   → Prometheus format                            # Metrics
```

Java services dùng Spring Actuator: `/actuator/health`, `/actuator/prometheus`

## 8. Multi-tenancy Standard

- Mọi DB query PHẢI filter `tenant_id`
- Mọi Kafka message PHẢI có header `tenant_id`
- Mọi cache key PHẢI prefix `{tenant_id}:`
- Mọi tool call trong AI Core PHẢI inject `tenant_id` từ JWT (không tin client)
- Qdrant: filter metadata `tenant_id`
- MinIO: path prefix `{tenant_id}/`

## 9. Tracing Standard

- Mọi request có `trace_id` (W3C Trace Context)
- Propagate qua tất cả service calls (REST header, gRPC metadata, Kafka header)
- Log mọi entry kèm `trace_id`
- OpenTelemetry SDK cho tất cả services

## 10. Platform Independence & Portability Standards (Quy chuẩn Tách biệt & Di động)

Để đảm bảo các service có khả năng tái sử dụng độc lập và dễ dàng tách thành các repo riêng biệt trong tương lai khi hệ thống mở rộng, TẤT CẢ các service phải tuyệt đối tuân thủ 3 nguyên tắc sau:

### Nguyên tắc 1: Không Hardcode Địa chỉ IP / Domain (Service Discovery qua Env)
- **Quy định:** Không được phép viết cứng địa chỉ IP, hostname hoặc domain của bất kỳ service nào khác trong mã nguồn. 
- **Giải pháp:** Mọi kết nối đến các service khác (REST, gRPC, Redis, Kafka, Postgres) bắt buộc phải cấu hình qua biến môi trường (Environment Variables) trong file cấu hình `.env` hoặc Docker/K8s Env (Ví dụ: `AI_CORE_GRPC_URL=http://ai-core:50052`, `REDIS_HOST=redis`).

### Nguyên tắc 2: Stateless APIs & Gateway Header Injections
- **Quy định:** Các service nghiệp vụ (backend services) phải hoàn toàn stateless đối với danh tính của Tenant và User.
- **Giải pháp:** Backend service KHÔNG tự giải mã JWT hay giao tiếp chéo để xác thực quyền truy cập tài nguyên của Tenant. Chỉ dựa duy nhất vào các headers chuẩn do Gateway (Kong) đã xác thực và inject vào:
  - `X-Tenant-ID`: Xác định tenant hiện tại.
  - `X-User-ID`: Xác định ID của user thực hiện hành động.
  - `X-User-Roles`: Danh sách vai trò để check RBAC (ví dụ: `admin,agent`).

### Nguyên tắc 3: Database-per-service Isolation (Cô lập Database hoàn toàn)
- **Quy định:** Mỗi microservice sở hữu cơ sở dữ liệu riêng (schema/database riêng). Tuyệt đối cấm hành vi chọc chéo vào DB của service khác (ví dụ: CRM service cấm query trực tiếp vào bảng `user` của Keycloak DB hay bảng `config` của Tenant Config DB).
- **Giải pháp:** Mọi việc đọc/ghi dữ liệu liên quan đến service khác bắt buộc phải thông qua API REST, gRPC client, hoặc truyền nhận tin nhắn bất đồng bộ qua Kafka.

