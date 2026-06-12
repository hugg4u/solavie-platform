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

**Algorithm:** Token Bucket (per tenant + per resource/tool)

**Implementation & Storage Segregation (Dynamic Tier Limits System):**
- **System Admin Configuration:** 
  - **Phân hạng gói (Tier assignment):** Gán gói cước cho Tenant (`free`, `standard`, `enterprise`, `custom_vip`) được System Admin lưu tại Redis: `tenant:{tenant_id}:tier`.
  - **Định nghĩa hạn mức gói (Dynamic Tier Limits):** Lưu tại database `config_db` (bảng `system_tier_limits`) và cache tại Redis dưới key: `tier:{tier_name}:limits` (JSON format chứa hạn mức các tài nguyên). Khi System Admin chỉnh sửa hạn mức gói trên Dashboard, sự kiện Pub/Sub `system.limits.updates` sẽ kích hoạt các service tự động tải lại hạn mức mới trong < 5 giây.
- **Tenant Admin Configuration:** 
  - Khóa API riêng (BYOK), custom prompts, thresholds của từng tenant được lưu tại bảng `tenant_configs` của `Tenant Config Service`.
- **Rate Limit Check Key format:** `ratelimit:{tenant_id}:{resource_or_tool}:{window}` (tần suất gọi tool của tenant) lưu trạng thái đếm tại Redis (atomic INCR + TTL).
- Khi exceed → return HTTP 429 + header `Retry-After: {seconds}`.

**Default Baseline limits per tier (Có thể tùy chỉnh động qua DB/Redis):**

| Resource | Free | Standard | Enterprise |
|----------|------|----------|------------|
| API requests/min (Gateway/Kong) | 60 | 200 | 1000 |
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

| Type | HTTP | Retriable |
|------|------|-----------|
| validation_error | 400 | No |
| unauthorized | 401 | No |
| forbidden | 403 | No |
| not_found | 404 | No |
| rate_limited | 429 | Yes (after Retry-After) |
| service_unavailable | 503 | Yes |
| timeout | 504 | Yes |
| publisher_failure | 503 | Yes (bọc retry trong publisher) |
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

## 11. API Scope Protection Standard (Tiêu chuẩn Bảo mật Client Scope)

Để giảm thiểu rủi ro khi token bị đánh cắp hoặc bị lạm dụng bởi các ứng dụng client khác nhau (ví dụ: Dashboard của nhân viên vs Ứng dụng tích hợp bên thứ ba), hệ thống bắt buộc áp dụng cơ chế xác thực phân quyền ở mức Client (OAuth2 Scope Validation) tại Gateway:

1. **Trách nhiệm của API Gateway (Kong):**
   - API Gateway chịu trách nhiệm đối chiếu đường dẫn của API request với cấu hình Route Scopes trong plugin `dynamic-policy`.
   - Gateway **PHẢI** kiểm tra xem access token đính kèm trong Authorization header có chứa Client Scope tương ứng với dịch vụ đích hay không.
   - Nếu thiếu scope hợp lệ, Gateway **PHẢI** từ chối request ngay lập tức với mã lỗi `403 Forbidden` và log lại cảnh báo bảo mật.

2. **Trách nhiệm của Downstream Microservices:**
   - Các microservices nghiệp vụ chạy stateless phía sau Gateway có thể hoàn toàn tin tưởng vào các header được Gateway inject (như `X-Tenant-ID`, `X-User-ID`, `X-User-Roles`).
   - Tài liệu đặc tả của mỗi microservice **PHẢI** chỉ rõ Client Scope bảo vệ các API của nó để làm cơ sở cấu hình Gateway và client.

3. **Danh mục OAuth2 Scopes mặc định per-service:**
   - Campaign Service: `campaign`
   - CRM Service: `crm`
   - Chatbot Service: `chatbot`
   - Content Service: `content`
   - Messaging Service: `messaging`
   - Knowledge Base Service: `knowledge-base`
   - AI Core Service: `ai-core`
   - Tenant Config Service: `tenant-config`
   - DMS Service: `dms`
   - Link Shortener Service: `link-shortener`
   - Analytics Service: `analytics`
   - Scheduler Service: `scheduler`
   - Comment Manager Service: `comment-manager`
   - Notification Service: `notification`
   - Channel Connector Service: `channel-connector`


## 12. Kafka Event Streaming Standard (MỚI)

Để đảm bảo các dịch vụ trao đổi thông điệp bất đồng bộ qua Kafka nhất quán và tin cậy, toàn bộ hệ thống phải tuân thủ các quy tắc sau:

### 12.1 Naming Convention cho Kafka Topics
Tên các topic bắt buộc phải tuân theo cấu trúc phân cấp bằng dấu chấm:
`{domain_hoac_service_name}.{resource_name}.{action_name_hoac_state}`

**Ví dụ:**
- `chatbot.conversation.completed` (Chatbot kết thúc lượt hội thoại RAG)
- `channel.message.received` (Nhận tin nhắn mới từ social channel)
- `content.published` (Bài viết được đăng thành công)

### 12.2 Cấu hình Topic mặc định (Production Baseline)
- **Partitions:** Tối thiểu 6 partitions để phân tải song song tốt.
- **Replication Factor:** Tối thiểu 2 trong môi trường production/staging để đảm bảo High Availability.
- **Retention Time:** Mặc định 7 ngày (`retention.ms = 604800000`) để cho phép replay dữ liệu khi có sự cố.
- **Partition Key:** Mọi message được gửi lên Kafka bắt buộc phải chỉ định **key** là `tenant_id` (hoặc prefix của tenant) để đảm bảo:
  - Tất cả tin nhắn của cùng một tenant được định tuyến về cùng một partition và xử lý theo đúng thứ tự thời gian gửi (Strict Ordering).

### 12.3 Tiêu chuẩn Publisher Failures & Resiliency
Khi một dịch vụ (Publisher) không thể gửi tin nhắn lên Kafka (do broker sập, timeout, network error):
- **Retry Policy:** Thực hiện retry tối đa 3 lần với cơ chế exponential backoff (1s, 2s, 4s).
- **Error Response:** Trả về structured error dạng `"error_type": "publisher_failure"` với HTTP 503 cho client nếu gọi sync.
- **Background Publisher (Fire-and-Forget):** Nếu gọi async, ghi nhận lỗi vào Dead Letter Log/Queue của chính service đó và nâng cảnh báo thông qua Prometheus metric `publisher_failures_total` mà không được phép làm crash tiến trình chính.



