# Business Logic — Scheduler Service

## Tổng quan vai trò

Scheduler Service quản lý **thời gian publish** và **automation flows**:
1. Nhận content đã approved → lên lịch publish
2. Khi đến giờ → trigger Channel Connector publish
3. Quản lý automation workflows (trigger → action chains)
4. Retry logic khi publish fail

## Luồng xử lý chi tiết

### Luồng 1: Schedule Post

```
Content approved (Kafka: content.approved)
hoặc User tạo schedule thủ công
│
▼
┌─────────────────────────────────┐
│ 1. CREATE SCHEDULE              │
│    - post_id, channel_ids       │
│    - scheduled_at (UTC)         │
│    - timezone (tenant config)   │
│    - status = 'pending'         │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. REGISTER QUARTZ JOB         │
│    - Create trigger at          │
│      scheduled_at time          │
│    - Job: PublishJob            │
│    - Store schedule_id in       │
│      job data                   │
└────────────┬────────────────────┘
             │
             ▼ (khi đến giờ)
┌─────────────────────────────────┐
│ 3. QUARTZ FIRES JOB            │
│    - Load schedule from DB      │
│    - Verify still pending       │
│    - Set status = 'publishing'  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 4. PUBLISH TO KAFKA             │
│    - Topic: scheduler.post.due  │
│    - Channel Connector consumes │
│      and publishes to platform  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 5. WAIT FOR CONFIRMATION        │
│    - Listen for                 │
│      channel.message.sent event │
│    - Timeout: 60s              │
└────────────┬────────────────────┘
             │
         ┌───┴───┐
         ▼       ▼
      Success   Failure
         │       │
         ▼       ▼
┌──────────┐  ┌──────────────────┐
│status =  │  │ RETRY LOGIC      │
│'published'│  │ retry_count++    │
└──────────┘  │ if < 3 → reschedule│
              │ if >= 3 → 'failed'│
              │ + notify user     │
              └──────────────────┘
```

**Quartz Job Implementation:**

```java
@Component
public class PublishJob implements Job {
    
    @Override
    public void execute(JobExecutionContext context) {
        String scheduleId = context.getJobDetail()
            .getJobDataMap().getString("scheduleId");
        
        Schedule schedule = scheduleRepo.findById(scheduleId)
            .orElseThrow(() -> new ScheduleNotFound(scheduleId));
        
        // Verify still pending (might have been cancelled)
        if (!schedule.getStatus().equals("pending")) {
            return; // Skip
        }
        
        // Update status
        schedule.setStatus("publishing");
        scheduleRepo.save(schedule);
        
        // Publish Kafka event
        kafkaTemplate.send("scheduler.post.due", ScheduleEvent.builder()
            .eventId(UUID.randomUUID().toString())
            .tenantId(schedule.getTenantId())
            .scheduleId(schedule.getId())
            .postId(schedule.getPostId())
            .channelIds(schedule.getChannelIds())
            .action("publish")
            .build());
    }
}

// Polling job (backup): chạy mỗi 30s kiểm tra schedules bị miss
// TỐI ƯU: chỉ query trong "missed window" (2-5 phút) thay vì TẤT CẢ pending
// Cần index: CREATE INDEX idx_schedules_pending_time ON schedules(status, scheduled_at) WHERE status='pending'
@Scheduled(fixedRate = 30000)
public void checkMissedSchedules() {
    Instant now = Instant.now();
    List<Schedule> missed = scheduleRepo.findMissedInWindow(
        now.minus(Duration.ofMinutes(5)),  // không quá cũ
        now.minus(Duration.ofMinutes(2)),  // grace period 2 min
        "pending",
        1000  // LIMIT 1000 — tránh load toàn bộ
    );

    for (Schedule s : missed) {
        publishSchedule(s);
    }
}
// Query: WHERE status='pending' AND scheduled_at BETWEEN (now-5m) AND (now-2m) LIMIT 1000
// Giảm 80% chi phí query so với quét toàn bộ pending schedules
```

### Luồng 2: Retry Logic

```java
@KafkaListener(topics = "channel.publish.result")
public void handlePublishResult(PublishResultEvent event) {
    Schedule schedule = scheduleRepo.findById(event.getScheduleId());
    
    if (event.getStatus().equals("success")) {
        schedule.setStatus("published");
        schedule.setPublishedAt(Instant.now());
        scheduleRepo.save(schedule);
        
        // Notify content service
        kafkaTemplate.send("content.published", ...);
        
    } else {
        // Failed
        schedule.setRetryCount(schedule.getRetryCount() + 1);
        schedule.setLastError(event.getError());
        
        if (schedule.getRetryCount() >= schedule.getMaxRetries()) {
            // All retries exhausted
            schedule.setStatus("failed");
            scheduleRepo.save(schedule);
            
            // Notify user
            kafkaTemplate.send("scheduler.post.failed", FailureEvent.builder()
                .tenantId(schedule.getTenantId())
                .scheduleId(schedule.getId())
                .error(event.getError())
                .retryCount(schedule.getRetryCount())
                .build());
        } else {
            // Retry with exponential backoff
            Duration delay = Duration.ofSeconds(
                (long) Math.pow(2, schedule.getRetryCount()) * 30 // 30s, 60s, 120s
            );
            Instant retryAt = Instant.now().plus(delay);
            
            schedule.setStatus("pending");
            schedule.setScheduledAt(retryAt);
            scheduleRepo.save(schedule);
            
            // Re-register Quartz job
            rescheduleQuartzJob(schedule, retryAt);
        }
    }
}
```

### Luồng 3: Automation Flows

```
Automation Flow = Trigger + Actions chain

Trigger types:
- schedule: Cron expression (e.g., "every Monday 9am")
- event: Kafka event (e.g., "new lead score > 80")
- condition: Data condition (e.g., "inbox unread > 50")

Action types:
- generate_content: Call Content Service AI generate
- publish_post: Schedule a post
- send_notification: Notify team
- update_crm: Tag contacts
```

```java
@Component
public class AutomationEngine {
    
    // Evaluate automation triggers
    @Scheduled(fixedRate = 60000) // Every minute
    public void evaluateScheduleTriggers() {
        List<AutomationFlow> flows = flowRepo.findEnabled();
        
        for (AutomationFlow flow : flows) {
            if (flow.getTriggerType().equals("schedule")) {
                CronExpression cron = CronExpression.parse(
                    flow.getTriggerConfig().get("cron").asText()
                );
                if (cron.matches(Instant.now())) {
                    executeFlow(flow);
                }
            }
        }
    }
    
    // Execute automation flow
    public void executeFlow(AutomationFlow flow) {
        AutomationExecution execution = new AutomationExecution();
        execution.setFlowId(flow.getId());
        execution.setTenantId(flow.getTenantId());
        execution.setTriggeredAt(Instant.now());
        
        try {
            JsonNode actions = flow.getActions(); // Ordered list
            
            for (JsonNode action : actions) {
                String type = action.get("type").asText();
                
                switch (type) {
                    case "generate_content":
                        // Call Content Service
                        contentClient.generate(
                            flow.getTenantId(),
                            action.get("topic").asText(),
                            action.get("platform").asText()
                        );
                        break;
                        
                    case "publish_post":
                        // Create schedule
                        createSchedule(flow.getTenantId(), action);
                        break;
                        
                    case "send_notification":
                        kafkaTemplate.send("notification.send", ...);
                        break;
                }
            }
            
            execution.setStatus("success");
        } catch (Exception e) {
            execution.setStatus("failed");
            execution.setError(e.getMessage());
        }
        
        executionRepo.save(execution);
    }
}
```

---

## Timezone Handling

```java
public class TimezoneHelper {
    /**
     * Tất cả thời gian trong DB lưu UTC.
     * Khi hiển thị cho user → convert sang tenant timezone.
     * Khi user tạo schedule → convert từ tenant timezone sang UTC.
     */
    public Instant toUTC(LocalDateTime localTime, String timezone) {
        ZoneId zone = ZoneId.of(timezone); // e.g., "Asia/Ho_Chi_Minh"
        return localTime.atZone(zone).toInstant();
    }
    
    public LocalDateTime toLocal(Instant utcTime, String timezone) {
        ZoneId zone = ZoneId.of(timezone);
        return utcTime.atZone(zone).toLocalDateTime();
    }
}
```

---

### Luồng 4: Xử lý MCP SSE JSON-RPC Requests

```
AI Core (MCP Host) ── X-Tenant-ID Header ──► Gateway (Kong) ──► Scheduler Service (Spring Boot)
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ 1. ROUTE TO SSE      │
                                                          │    /api/v1/scheduler/│
                                                          │    mcp               │
                                                          └──────────┬───────────┘
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ 2. VALIDATE TENANT   │
                                                          │    Ensure tenant_id  │
                                                          │    is present in     │
                                                          │    headers           │
                                                          └──────────┬───────────┘
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ 3. HANDSHAKE / SSE   │
                                                          │    Establish SSE     │
                                                          │    SseEmitter Stream │
                                                          └──────────┬───────────┘
                                                                     │
                                                                     ▼ (POST /messages)
                                                          ┌──────────────────────┐
                                                          │ 4. OVERWRITE TENANT  │
                                                          │    Inject tenant_id  │
                                                          │    into schedule params│
                                                          └──────────┬───────────┘
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ 5. SAVE & REGISTER   │
                                                          │    Save schedule &   │
                                                          │    register Quartz   │
                                                          │    job with tenant_id│
                                                          └──────────┬───────────┘
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ 6. RESPONSE          │
                                                          │    Return JSON-RPC   │
                                                          │    success payload   │
                                                          │    via SseEmitter    │
                                                          └──────────────────────┘
```

**Mẫu triển khai logic bảo mật đa thuê trên MCP Spring Boot Controller (Scheduler):**
```java
@RestController
@RequestMapping("/api/v1/scheduler/mcp")
public class SchedulerMcpController {

    private final Map<String, SseEmitter> emitters = new ConcurrentHashMap<>();
    private final SchedulerMcpService schedulerMcpService;

    @GetMapping(produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter connectMcp(@RequestHeader("X-Tenant-ID") String tenantId) {
        SseEmitter emitter = new SseEmitter(600000L); // 10 minutes timeout
        emitters.put(tenantId, emitter);
        
        emitter.onCompletion(() -> emitters.remove(tenantId));
        emitter.onTimeout(() -> emitters.remove(tenantId));
        
        try {
            emitter.send(SseEmitter.event().name("endpoint").data("/api/v1/scheduler/mcp/messages"));
        } catch (IOException e) {
            emitter.completeWithError(e);
        }
        return emitter;
    }

    @PostMapping("/messages")
    public ResponseEntity<Void> handleMessage(
            @RequestHeader("X-Tenant-ID") String tenantId,
            @RequestBody String jsonRpcMessage) {
        
        // BẢO MẬT: Inject tenantId từ gateway header vào logic xử lý JSON-RPC
        schedulerMcpService.processJsonRpc(tenantId, jsonRpcMessage, emitters.get(tenantId));
        return ResponseEntity.accepted().build();
    }
}
```

---


## Zero-Trust Security & Dynamic RBAC Logic

Dịch vụ thực hiện cơ chế xác thực Zero-Trust và phân quyền động (Dynamic RBAC) dựa trên HMAC Signed Headers được truyền từ API Gateway:

### 1. Quy trình xác thực chữ ký (HMAC Verification Flow)
- Dịch vụ trích xuất các headers từ request:
  - `X-Tenant-ID`: ID của Tenant.
  - `X-User-ID`: ID của User.
  - `X-User-Permissions`: Chuỗi CSV chứa danh sách quyền của người dùng (ví dụ: `scheduler:{resource}:{action}`).
  - `X-Permissions-Signature`: Chữ ký HMAC-SHA256 dạng hex.
- Dịch vụ tính toán signature dự kiến bằng khóa bí mật `GATEWAY_SIGNING_SECRET`:
  `expected_sig = HMAC_SHA256(GATEWAY_SIGNING_SECRET, X-Tenant-ID + ":" + X-User-ID + ":" + X-User-Permissions)`
- So sánh chữ ký nhận được với `expected_sig` sử dụng hàm so sánh an toàn chống Side-channel attack (ví dụ: so sánh độ dài không đổi/safe compare). Nếu không khớp, từ chối request với mã lỗi `403 Forbidden` và tăng counter metric lỗi bảo mật.

### 2. So khớp quyền hạn In-Memory O(1)
- Sau khi chữ ký được xác thực, dịch vụ chuyển chuỗi `X-User-Permissions` thành một cấu trúc Set để tìm kiếm với độ phức tạp $O(1)$.
- Đối với mỗi API endpoint yêu cầu quyền hạn `scheduler:{resource}:{action}`, dịch vụ kiểm tra quyền trong Set:
  - Nếu Set chứa `*` (Super Admin), cho phép truy cập.
  - Nếu Set chứa `scheduler:*` (Toàn quyền trên dịch vụ), cho phép truy cập.
  - Nếu Set chứa `scheduler:{resource}:*` (Toàn quyền trên tài nguyên), cho phép truy cập.
  - Nếu Set chứa chính xác `scheduler:{resource}:{action}`, cho phép truy cập.
  - Ngược lại, từ chối truy cập và trả về mã lỗi `403 Forbidden` kèm log lỗi chi tiết.

## Error Handling

| Scenario | Xử lý |
|----------|--------|
| Quartz job miss (server restart) | Polling job catches missed schedules within 2 min |
| Channel Connector unavailable | Retry 3x exponential backoff, then fail + notify |
| Post deleted before publish time | Check post exists before publish, skip if deleted |
| Timezone invalid | Default to UTC, log warning |
| Automation flow action fails | Log error, continue next action (partial success) |
| Concurrent schedule modification | Optimistic locking (version column) |
| MCP SSE Session Timeout | Hủy phiên kết nối và giải phóng Quartz Listener context tương ứng của tenant |
| Tenant ID Validation Failure | Trả về lỗi JSON-RPC Invalid Request và ghi nhận vi phạm an ninh |

---

## Business Logic — Service Self-Registration

### 1. Logic Đăng ký (Startup Hook)
* BƯỚC 1: Gọi hàm `_get_internal_ip()` sử dụng socket UDP giả lập kết nối tới `8.8.8.8:80` để lấy IP nội bộ của container.
* BƯỚC 2: Định nghĩa chuỗi node dạng `{ip}:{port}`.
* BƯỚC 3: Thực hiện pipeline ghi vào Redis:
  * `SADD registry:service:scheduler "{ip}:{port}"`
  * `SETEX registry:service:scheduler:node:{ip}:{port} 15 "alive"`
* BƯỚC 4: Bắt đầu chạy vòng lặp heartbeat (mỗi 5 giây) để gửi lại gói tin `SETEX` và `SADD` để làm mới TTL.

### 2. Logic Hủy đăng ký (Shutdown Hook)
* BƯỚC 1: Dừng vòng lặp heartbeat.
* BƯỚC 2: Thực hiện pipeline dọn dẹp Redis:
  * `SREM registry:service:scheduler "{ip}:{port}"`
  * `DEL registry:service:scheduler:node:{ip}:{port}"`
