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

## Error Handling

| Scenario | Xử lý |
|----------|--------|
| A/B test: not enough data after 14 days | Conclude as "inconclusive", notify user |
| Campaign activate with no posts | Reject, return validation error |
| Metrics event for deleted campaign | Skip, log debug |
| Statistical calculation error | Log error, skip this analysis cycle |
| Goal check: Analytics unavailable | Skip, retry next cycle |
