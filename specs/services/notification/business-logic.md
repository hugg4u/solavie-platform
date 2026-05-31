# Business Logic — Notification Service

## Tổng quan vai trò

Notification Service đảm bảo **thông báo đến đúng người, đúng lúc, đúng kênh**:
1. Consume events từ Kafka (handoff, lead score, failures)
2. Resolve recipient + preferences
3. Deliver qua Slack/email/push (với fallback)
4. Track delivery status, respect quiet hours

## Luồng xử lý chi tiết

### Luồng 1: Process Notification Event

```
Kafka event (handoff/score_change/failure/escalation)
│
▼
┌─────────────────────────────────┐
│ 1. PARSE EVENT                  │
│    - Determine notification type│
│    - Extract: tenant_id,        │
│      target_user_id, priority   │
│    - Build notification content │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. RESOLVE RECIPIENT            │
│    - Who should receive?        │
│    - Handoff → assigned agent   │
│    - Score change → assigned    │
│      agent or sales team        │
│    - Failure → post creator     │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 3. CHECK PREFERENCES            │
│    - Load user preferences      │
│    - Which channels enabled?    │
│    - Is it quiet hours?         │
│    - Priority filter?           │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 4. QUIET HOURS CHECK            │
│    - If priority = critical →   │
│      IGNORE quiet hours (send)  │
│    - If priority = normal/low   │
│      AND in quiet hours →       │
│      QUEUE for later            │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 5. DELIVER                      │
│    - Try primary channel first  │
│    - If fail → try next channel │
│    - If all fail → queue retry  │
│    - Save delivery status       │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 6. SAVE & TRACK                 │
│    - Save to notifications table│
│    - In-app notification always │
│    - Track delivery_status      │
└─────────────────────────────────┘
```

**Delivery Logic:**

```typescript
class NotificationDelivery {
  private channelHandlers = {
    slack: new SlackHandler(),
    email: new EmailHandler(),
    push: new PushHandler(),
  };

  async deliver(notification: Notification, preferences: UserPreferences): Promise<DeliveryResult> {
    // Determine channel order based on priority
    const channels = this.getChannelOrder(notification.priority, preferences);
    
    for (const channel of channels) {
      if (!preferences.channels[channel]) continue; // Channel disabled
      
      try {
        await this.channelHandlers[channel].send(notification);
        return { status: 'delivered', channel, attempts: 1 };
      } catch (error) {
        // Channel failed, try next
        logger.warn(`${channel} delivery failed: ${error.message}`);
        continue;
      }
    }
    
    // All channels failed
    return { status: 'failed', attempts: channels.length };
  }

  private getChannelOrder(priority: string, prefs: UserPreferences): string[] {
    // Critical: try all channels simultaneously
    if (priority === 'critical') {
      return ['slack', 'push', 'email']; // Fastest first
    }
    // Normal: respect user preference order
    return prefs.channel_order || ['slack', 'email', 'push'];
  }
}

// Slack Handler
class SlackHandler {
  async send(notification: Notification): Promise<void> {
    const slackUserId = await this.resolveSlackUser(notification.user_id);
    
    await this.slackClient.chat.postMessage({
      channel: slackUserId, // DM
      text: notification.title,
      blocks: [
        { type: 'header', text: { type: 'plain_text', text: notification.title } },
        { type: 'section', text: { type: 'mrkdwn', text: notification.body } },
        // Action button (e.g., "View Conversation")
        ...(notification.action_url ? [{
          type: 'actions',
          elements: [{
            type: 'button',
            text: { type: 'plain_text', text: 'View' },
            url: notification.action_url,
          }]
        }] : []),
      ],
    });
  }
}

// Email Handler
class EmailHandler {
  async send(notification: Notification): Promise<void> {
    await this.mailer.send({
      to: notification.user_email,
      subject: notification.title,
      html: this.renderTemplate(notification),
    });
  }
}

// Push Handler (Firebase Cloud Messaging)
class PushHandler {
  async send(notification: Notification): Promise<void> {
    const fcmToken = await this.getFCMToken(notification.user_id);
    if (!fcmToken) throw new Error('No FCM token registered');
    
    await this.fcm.send({
      token: fcmToken,
      notification: {
        title: notification.title,
        body: notification.body,
      },
      data: {
        type: notification.type,
        action_url: notification.action_url || '',
      },
    });
  }
}
```

### Luồng 2: Quiet Hours

```typescript
class QuietHoursChecker {
  isQuietHours(preferences: UserPreferences): boolean {
    const { start, end, timezone } = preferences.quiet_hours;
    // e.g., start: "22:00", end: "08:00", timezone: "Asia/Ho_Chi_Minh"
    
    const now = moment().tz(timezone);
    const startTime = moment.tz(start, 'HH:mm', timezone);
    const endTime = moment.tz(end, 'HH:mm', timezone);
    
    // Handle overnight (22:00 → 08:00)
    if (startTime.isAfter(endTime)) {
      return now.isAfter(startTime) || now.isBefore(endTime);
    }
    return now.isAfter(startTime) && now.isBefore(endTime);
  }
}

// Queued notifications delivered when quiet hours end
@Cron('0 * * * *') // Every hour
async deliverQueuedNotifications() {
  const queued = await this.notifRepo.findQueued();
  
  for (const notif of queued) {
    const prefs = await this.getPreferences(notif.user_id);
    if (!this.quietHoursChecker.isQuietHours(prefs)) {
      await this.deliver(notif, prefs);
    }
  }
}
```

### Luồng 3: SLA Tracking

```typescript
// Handoff notifications MUST be delivered within 3 seconds
class SLATracker {
  private SLA_TARGETS = {
    critical: 3000,   // 3s
    high: 30000,      // 30s
    normal: 300000,   // 5 min
    low: 3600000,     // 1 hour (batched)
  };

  async trackDelivery(notification: Notification, deliveredAt: Date): void {
    const elapsed = deliveredAt.getTime() - notification.created_at.getTime();
    const target = this.SLA_TARGETS[notification.priority];
    
    if (elapsed > target) {
      // SLA breached
      metrics.slaBreach.inc({ priority: notification.priority });
      logger.warn(`SLA breach: ${notification.type}, ${elapsed}ms > ${target}ms`);
    } else {
      metrics.slaMet.inc({ priority: notification.priority });
    }
  }
}
```

---

## Notification Types & Templates

| Event | Type | Priority | Template |
|-------|------|----------|----------|
| Handoff | handoff | critical | "Khách hàng {name} cần hỗ trợ trên {channel}" |
| Lead score change | lead_score | high | "Lead {name} score tăng lên {score} (Hot!)" |
| Publish failed | publish_failed | high | "Bài viết '{title}' publish thất bại: {error}" |
| Comment escalation | escalation | high | "Comment tiêu cực trên bài '{post}': {preview}" |
| Campaign goal reached | goal_reached | normal | "Campaign '{name}' đạt mục tiêu {metric}" |
| Weekly report ready | report_ready | low | "Báo cáo tuần đã sẵn sàng" |

---

## Error Handling

| Scenario | Xử lý |
|----------|--------|
| Slack API down | Fallback to email, then push |
| Email bounce | Mark email invalid, try push |
| FCM token expired | Remove token, try other channels |
| All channels fail | Queue for retry (max 3x, 5min interval) |
| User has no preferences | Use defaults: all channels enabled |
| Recipient not found | Log error, skip (don't crash) |
