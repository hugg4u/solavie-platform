# Business Logic — Analytics Service

## Tổng quan vai trò

Analytics Service **thu thập, tổng hợp, và phân tích** dữ liệu từ toàn hệ thống:
1. Consume events từ Kafka → lưu metrics vào TimescaleDB
2. Aggregate metrics (realtime + daily/weekly)
3. Generate AI insights (weekly report)
4. Export reports (PDF/CSV)

## Luồng xử lý chi tiết

### Luồng 1: Event Consumption & Metrics Storage

```
Kafka events (from all services)
│
▼
┌─────────────────────────────────┐
│ 1. CONSUME & CLASSIFY EVENT     │
│    - channel.message.received   │
│      → message_count metric     │
│    - content.published          │
│      → post_count metric        │
│    - messaging.handoff.requested│
│      → handoff_rate metric      │
│    - campaign.event.*           │
│      → campaign metrics         │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. EXTRACT METRIC DATA          │
│    - tenant_id                  │
│    - channel                    │
│    - metric_type                │
│    - value                      │
│    - timestamp                  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 3. INSERT INTO TIMESCALEDB      │
│    - Hypertable: metrics        │
│    - Auto-partitioned by time   │
│    - Continuous aggregates      │
│      auto-refresh daily         │
└─────────────────────────────────┘
```

```java
@KafkaListener(topics = {
    "channel.message.received",
    "channel.message.sent",
    "content.published",
    "messaging.handoff.requested",
    "campaign.event.*",
    "crm.lead.score.changed"
})
public void consumeEvent(ConsumerRecord<String, String> record) {
    String topic = record.topic();
    JsonNode event = objectMapper.readTree(record.value());
    
    String tenantId = event.get("tenant_id").asText();
    Instant timestamp = Instant.parse(event.get("timestamp").asText());
    
    switch (topic) {
        case "channel.message.received":
            insertMetric(tenantId, event.get("channel").asText(), 
                "messages_received", 1, timestamp);
            break;
            
        case "channel.message.sent":
            insertMetric(tenantId, event.get("channel").asText(),
                "messages_sent", 1, timestamp);
            // Also track response time if available
            if (event.has("response_time_ms")) {
                insertMetric(tenantId, event.get("channel").asText(),
                    "response_time_ms", event.get("response_time_ms").asLong(), timestamp);
            }
            break;
            
        case "content.published":
            insertMetric(tenantId, event.get("platform").asText(),
                "posts_published", 1, timestamp);
            break;
            
        case "messaging.handoff.requested":
            insertMetric(tenantId, "all",
                "handoffs", 1, timestamp);
            break;
    }
}
```

### Luồng 2: Engagement Metrics (from Platform APIs)

```
Cron job: mỗi 5 phút pull engagement data từ platforms
│
▼
┌─────────────────────────────────┐
│ 1. GET PUBLISHED POSTS          │
│    - Query posts published in   │
│      last 7 days                │
│    - Group by platform          │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. CALL PLATFORM APIs           │
│    - Facebook: GET /{post_id}   │
│      ?fields=likes,comments,    │
│      shares,reach               │
│    - Zalo: GET /article/stats   │
│    - TikTok: GET /video/stats   │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 3. CALCULATE DELTAS             │
│    - Compare with last pull     │
│    - New likes = current - prev │
│    - Store incremental metrics  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 4. STORE METRICS                │
│    - Insert into TimescaleDB    │
│    - Update post performance    │
│      summary                    │
└─────────────────────────────────┘
```

### Luồng 3: AI Weekly Insights

```
Cron: Every Monday 8:00 AM (per tenant timezone)
│
▼
┌─────────────────────────────────┐
│ 1. AGGREGATE WEEKLY DATA        │
│    - Total messages, posts,     │
│      engagement per channel     │
│    - Compare vs previous week   │
│    - Top performing posts       │
│    - Handoff rate trend         │
│    - Lead score distribution    │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. CALL AI CORE (summarization) │
│    - Input: weekly data summary │
│    - Output: human-readable     │
│      insights + recommendations │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 3. GENERATE REPORT              │
│    - Format: structured JSON    │
│    - Sections: overview, per-   │
│      channel, top content,      │
│      recommendations            │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 4. NOTIFY & STORE               │
│    - Save report to DB          │
│    - Notify managers via        │
│      Notification Service       │
│    - Available in Dashboard     │
└─────────────────────────────────┘
```

**AI Insight Prompt:**

```java
String insightPrompt = """
Analyze this weekly marketing data and provide actionable insights.

Data:
- Messages received: {messages_received} ({messages_change}% vs last week)
- Messages sent: {messages_sent}
- Handoff rate: {handoff_rate}%
- Posts published: {posts_published}
- Top post engagement: {top_post_engagement}
- Average response time: {avg_response_time}ms
- New leads: {new_leads}
- Hot leads (score>80): {hot_leads}

Provide:
1. Key highlights (what went well)
2. Areas of concern (what needs attention)
3. Recommendations (specific actions to take)
4. Best posting times based on engagement data

Return JSON: {
  "highlights": ["..."],
  "concerns": ["..."],
  "recommendations": ["..."],
  "best_posting_times": {"facebook": "...", "zalo": "...", "tiktok": "..."}
}""";
```

### Luồng 4: Report Export

```java
public class ReportGenerator {
    
    public byte[] generatePDF(String tenantId, DateRange range) {
        // 1. Query aggregated metrics
        List<DailyMetric> metrics = metricRepo.findByRange(tenantId, range);
        
        // 2. Build report sections
        ReportData data = ReportData.builder()
            .overview(buildOverview(metrics))
            .channelBreakdown(buildChannelBreakdown(metrics))
            .topContent(buildTopContent(tenantId, range))
            .charts(buildChartData(metrics))
            .build();
        
        // 3. Render PDF (iText)
        return pdfRenderer.render(data);
    }
    
    public byte[] generateCSV(String tenantId, DateRange range) {
        List<DailyMetric> metrics = metricRepo.findByRange(tenantId, range);
        return csvWriter.write(metrics);
    }
}
```

---

## TimescaleDB Continuous Aggregates

```sql
-- Real-time 1-hour aggregate (TỐI ƯU cho dashboard realtime)
-- Refresh mỗi 5 phút thay vì daily → dashboard nhanh 10x
CREATE MATERIALIZED VIEW hourly_metrics
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS hour,
    tenant_id,
    channel,
    metric_type,
    SUM(value) AS total
FROM metrics
GROUP BY hour, tenant_id, channel, metric_type
WITH NO DATA;

SELECT add_continuous_aggregate_policy('hourly_metrics',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes');

-- Auto-refreshed daily aggregate
CREATE MATERIALIZED VIEW daily_metrics
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS day,
    tenant_id,
    channel,
    metric_type,
    SUM(value) AS total,
    AVG(value) AS average,
    COUNT(*) AS count
FROM metrics
GROUP BY day, tenant_id, channel, metric_type
WITH NO DATA;

-- Refresh policy: refresh daily, keep 90 days
SELECT add_continuous_aggregate_policy('daily_metrics',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

-- Retention: drop raw data after 30 days, keep aggregates 1 year
SELECT add_retention_policy('metrics', INTERVAL '30 days');
```

---

### Luồng 5: Xử lý MCP SSE JSON-RPC Requests

```
AI Core (MCP Host) ── X-Tenant-ID Header ──► Gateway (Kong) ──► Analytics Service (Spring Boot)
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ 1. ROUTE TO SSE      │
                                                          │    /api/v1/analytics/│
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
                                                          │    into query params │
                                                          └──────────┬───────────┘
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ 5. TIMESCALEDB QUERY │
                                                          │    Query continuous  │
                                                          │    aggregates view   │
                                                          │    where tenant_id=  │
                                                          │    T_ID              │
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

**Mẫu triển khai logic bảo mật đa thuê trên MCP Spring Boot Endpoint:**
```java
@RestController
@RequestMapping("/api/v1/analytics/mcp")
public class McpController {

    private final Map<String, SseEmitter> emitters = new ConcurrentHashMap<>();
    private final AnalyticsMcpService analyticsMcpService;

    @GetMapping(produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter connectMcp(@RequestHeader("X-Tenant-ID") String tenantId) {
        SseEmitter emitter = new SseEmitter(600000L); // 10 minutes timeout
        emitters.put(tenantId, emitter);
        
        emitter.onCompletion(() -> emitters.remove(tenantId));
        emitter.onTimeout(() -> emitters.remove(tenantId));
        
        // Gửi handshake event thành công
        try {
            emitter.send(SseEmitter.event().name("endpoint").data("/api/v1/analytics/mcp/messages"));
        } catch (IOException e) {
            emitter.completeWithError(e);
        }
        return emitter;
    }

    @PostMapping("/messages")
    public ResponseEntity<Void> handleMessage(
            @RequestHeader("X-Tenant-ID") String tenantId,
            @RequestBody String jsonRpcMessage) {
        
        // BẢO MẬT: Bắt buộc inject tenantId và phân tích JSON-RPC message
        analyticsMcpService.processJsonRpc(tenantId, jsonRpcMessage, emitters.get(tenantId));
        return ResponseEntity.accepted().build();
    }
}
```

---

## Error Handling

| Scenario | Xử lý |
|----------|--------|
| Kafka consumer lag high | Scale consumer instances, alert |
| Platform API rate limit (engagement pull) | Backoff, reduce pull frequency |
| TimescaleDB disk full | Alert critical, retention policy should prevent |
| AI insight generation fail | Skip this week, retry next day |
| Report generation timeout | Async job, notify when ready |
| Missing data gaps | Mark in report, don't interpolate |
| MCP SSE Emitter Timeout | Đóng emitter, giải phóng session của tenant |
| Unauthorized Tenant Access | Trả về HTTP 403 ngay từ tầng controller và log lỗi bảo mật |

