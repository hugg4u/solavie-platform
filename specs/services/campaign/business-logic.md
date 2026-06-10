# Business Logic — Campaign Service

## Tổng quan vai trò

Campaign Service quản lý **chiến dịch marketing**: tạo campaign multi-post, A/B testing với statistical significance, lifecycle management, performance tracking.

## Luồng xử lý chi tiết

### Luồng 1: Campaign Lifecycle

```
Draft → Active → Paused → Completed
         ↑         ↓
         └─────────┘ (resume)

Rules:
- Draft: Có thể edit, add/remove posts, chưa publish gì
- Active: Posts đang được schedule/publish, metrics collecting
- Paused: Tạm dừng publish, giữ metrics
- Completed: Kết thúc, generate final report
```

```java
public class CampaignLifecycleManager {
    
    public void activate(Campaign campaign) {
        // Validate: must have at least 1 post linked
        if (campaign.getPosts().isEmpty()) {
            throw new ValidationException("Campaign must have at least 1 post");
        }
        
        campaign.setStatus("active");
        campaign.setStartDate(Instant.now());
        campaignRepo.save(campaign);
        
        // Schedule all linked posts
        for (CampaignPost post : campaign.getPosts()) {
            schedulerClient.createSchedule(post.getPostId(), post.getScheduledAt());
        }
        
        // Publish event
        kafkaTemplate.send("campaign.started", CampaignEvent.of(campaign));
    }
    
    public void complete(Campaign campaign) {
        campaign.setStatus("completed");
        campaign.setEndDate(Instant.now());
        campaignRepo.save(campaign);
        
        // Generate performance report
        analyticsClient.generateCampaignReport(campaign.getId());
        
        // Publish event
        kafkaTemplate.send("campaign.completed", CampaignEvent.of(campaign));
    }
}
```

### Luồng 2: A/B Testing

```
Create A/B Test
│
▼
┌─────────────────────────────────┐
│ 1. SETUP VARIANTS               │
│    - Variant A: post_id_1       │
│    - Variant B: post_id_2       │
│    - Traffic split: 50/50       │
│    - Min sample: 100 per variant│
│    - Max duration: 14 days      │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. DISTRIBUTE TRAFFIC           │
│    - Random assignment          │
│    - Track which audience sees  │
│      which variant              │
└────────────┬────────────────────┘
             │
             ▼ (collect metrics over time)
┌─────────────────────────────────┐
│ 3. STATISTICAL ANALYSIS         │
│    - Metric: engagement rate    │
│    - Test: Chi-square or Z-test │
│    - Check every 6 hours        │
│    - p-value < 0.05 = significant│
└────────────┬────────────────────┘
             │
         ┌───┴───┐
         ▼       ▼
    Significant  Not yet
         │       │
         ▼       ▼
┌──────────┐  ┌──────────────────┐
│ CONCLUDE │  │ Continue         │
│ Winner!  │  │ (until max days) │
└──────────┘  └──────────────────┘
```

**Statistical Significance Logic:**

```java
public class ABTestAnalyzer {
    
    private static final double SIGNIFICANCE_LEVEL = 0.05; // p < 0.05
    private static final int MIN_SAMPLE_SIZE = 100;
    
    @Scheduled(fixedRate = 6 * 60 * 60 * 1000) // Every 6 hours
    public void analyzeRunningTests() {
        List<ABTest> running = abTestRepo.findByStatus("running");
        
        for (ABTest test : running) {
            analyzeTest(test);
        }
    }
    
    public void analyzeTest(ABTest test) {
        // Get metrics for each variant
        Map<String, VariantMetrics> metrics = getVariantMetrics(test);
        
        // Check minimum sample size
        boolean enoughData = metrics.values().stream()
            .allMatch(m -> m.getSampleSize() >= MIN_SAMPLE_SIZE);
        
        if (!enoughData) {
            // Check if max duration exceeded
            if (test.getCreatedAt().plus(Duration.ofDays(14)).isBefore(Instant.now())) {
                concludeInconclusive(test);
            }
            return; // Not enough data yet
        }
        
        // Perform statistical test (Z-test for proportions)
        VariantMetrics varA = metrics.get("A");
        VariantMetrics varB = metrics.get("B");
        
        double pValue = calculateZTestPValue(
            varA.getEngagementRate(), varA.getSampleSize(),
            varB.getEngagementRate(), varB.getSampleSize()
        );
        
        if (pValue < SIGNIFICANCE_LEVEL) {
            // Statistically significant!
            String winner = varA.getEngagementRate() > varB.getEngagementRate() ? "A" : "B";
            concludeWithWinner(test, winner, 1 - pValue);
        }
    }
    
    private double calculateZTestPValue(
        double p1, int n1, double p2, int n2
    ) {
        // Pooled proportion
        double p = (p1 * n1 + p2 * n2) / (n1 + n2);
        double se = Math.sqrt(p * (1 - p) * (1.0/n1 + 1.0/n2));
        double z = (p1 - p2) / se;
        
        // Two-tailed p-value
        return 2 * (1 - normalCDF(Math.abs(z)));
    }
    
    private void concludeWithWinner(ABTest test, String winner, double confidence) {
        test.setStatus("concluded");
        test.setWinnerVariant(winner);
        test.setConfidenceLevel(confidence);
        test.setConcludedAt(Instant.now());
        abTestRepo.save(test);
        
        // Scale winner to 100% traffic
        // Pause loser variant
        kafkaTemplate.send("campaign.ab_test.concluded", ...);
    }
}
```

### Luồng 3: Performance Tracking

```java
// Consume metrics events from Analytics
@KafkaListener(topics = "analytics.metrics.updated")
public void handleMetricsUpdate(MetricsEvent event) {
    if (event.getCampaignId() == null) return;
    
    // Update campaign_metrics table
    CampaignMetric metric = metricRepo.findOrCreate(
        event.getCampaignId(), event.getDate()
    );
    
    switch (event.getMetricType()) {
        case "reach": metric.setReach(metric.getReach() + event.getValue()); break;
        case "engagement": metric.setEngagement(metric.getEngagement() + event.getValue()); break;
        case "clicks": metric.setClicks(metric.getClicks() + event.getValue()); break;
        case "conversions": metric.setConversions(metric.getConversions() + event.getValue()); break;
    }
    
    metricRepo.save(metric);
    
    // Check against campaign goals
    checkGoalProgress(event.getCampaignId());
}

private void checkGoalProgress(String campaignId) {
    Campaign campaign = campaignRepo.findById(campaignId);
    JsonNode goals = campaign.getGoals();
    
    long totalReach = metricRepo.sumReach(campaignId);
    
    if (goals.has("reach") && totalReach >= goals.get("reach").asLong()) {
        // Goal reached! Notify
        kafkaTemplate.send("notification.send", NotificationEvent.builder()
            .type("campaign_goal_reached")
            .message(String.format("Campaign '%s' reached goal: %d reach", 
                campaign.getName(), totalReach))
            .build());
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
  - `X-User-Permissions`: Chuỗi CSV chứa danh sách quyền của người dùng (ví dụ: `campaign:{resource}:{action}`).
  - `X-Permissions-Signature`: Chữ ký HMAC-SHA256 dạng hex.
- Dịch vụ tính toán signature dự kiến bằng khóa bí mật `GATEWAY_SIGNING_SECRET`:
  `expected_sig = HMAC_SHA256(GATEWAY_SIGNING_SECRET, X-Tenant-ID + ":" + X-User-ID + ":" + X-User-Permissions)`
- So sánh chữ ký nhận được với `expected_sig` sử dụng hàm so sánh an toàn chống Side-channel attack (ví dụ: so sánh độ dài không đổi/safe compare). Nếu không khớp, từ chối request với mã lỗi `403 Forbidden` và tăng counter metric lỗi bảo mật.

### 2. So khớp quyền hạn In-Memory O(1)
- Sau khi chữ ký được xác thực, dịch vụ chuyển chuỗi `X-User-Permissions` thành một cấu trúc Set để tìm kiếm với độ phức tạp $O(1)$.
- Đối với mỗi API endpoint yêu cầu quyền hạn `campaign:{resource}:{action}`, dịch vụ kiểm tra quyền trong Set:
  - Nếu Set chứa `*` (Super Admin), cho phép truy cập.
  - Nếu Set chứa `campaign:*` (Toàn quyền trên dịch vụ), cho phép truy cập.
  - Nếu Set chứa `campaign:{resource}:*` (Toàn quyền trên tài nguyên), cho phép truy cập.
  - Nếu Set chứa chính xác `campaign:{resource}:{action}`, cho phép truy cập.
  - Ngược lại, từ chối truy cập và trả về mã lỗi `403 Forbidden` kèm log lỗi chi tiết.

## Error Handling

| Scenario | Xử lý |
|----------|--------|
| A/B test: not enough data after 14 days | Conclude as "inconclusive", notify user |
| Campaign activate with no posts | Reject, return validation error |
| Metrics event for deleted campaign | Skip, log debug |
| Statistical calculation error | Log error, skip this analysis cycle |
| Goal check: Analytics unavailable | Skip, retry next cycle |

---

## Business Logic — Service Self-Registration

### 1. Logic Đăng ký (Startup Hook)
* BƯỚC 1: Gọi hàm `_get_internal_ip()` sử dụng socket UDP giả lập kết nối tới `8.8.8.8:80` để lấy IP nội bộ của container.
* BƯỚC 2: Định nghĩa chuỗi node dạng `{ip}:{port}`.
* BƯỚC 3: Thực hiện pipeline ghi vào Redis:
  * `SADD registry:service:campaign "{ip}:{port}"`
  * `SETEX registry:service:campaign:node:{ip}:{port} 15 "alive"`
* BƯỚC 4: Bắt đầu chạy vòng lặp heartbeat (mỗi 5 giây) để gửi lại gói tin `SETEX` và `SADD` để làm mới TTL.

### 2. Logic Hủy đăng ký (Shutdown Hook)
* BƯỚC 1: Dừng vòng lặp heartbeat.
* BƯỚC 2: Thực hiện pipeline dọn dẹp Redis:
  * `SREM registry:service:campaign "{ip}:{port}"`
  * `DEL registry:service:campaign:node:{ip}:{port}"`
