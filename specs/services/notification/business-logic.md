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

### Luồng 4: Xử lý MCP SSE JSON-RPC Requests

```
AI Core (MCP Host) ── X-Tenant-ID Header ──► Gateway (Kong) ──► Notification Service
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ 1. ROUTE TO SSE      │
                                                          │    /api/v1/          │
                                                          │    notification/mcp  │
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
                                                          │    Stream Transport  │
                                                          └──────────┬───────────┘
                                                                     │
                                                                     ▼ (POST /messages)
                                                          ┌──────────────────────┐
                                                          │ 4. OVERWRITE TENANT  │
                                                          │    Inject tenant_id  │
                                                          │    into tool arguments│
                                                          └──────────┬───────────┘
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ 5. DISPATCH NOTIF    │
                                                          │    Send notification │
                                                          │    & save DB where   │
                                                          │    tenant_id=T_ID    │
                                                          └──────────┬───────────┘
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ 6. RESPONSE          │
                                                          │    Return JSON-RPC   │
                                                          │    success payload   │
                                                          └──────────────────────┘
```

**Mẫu triển khai logic bảo mật đa thuê trên MCP NestJS Controller (Notification):**
```typescript
@Controller('api/v1/notification/mcp')
export class NotificationMcpController {
  private mcpServer: McpServer;

  constructor(private readonly notificationService: NotificationService) {
    this.initMcpServer();
  }

  private initMcpServer() {
    this.mcpServer = new McpServer({ name: 'notification_dispatcher', version: '1.0.0' });
    this.mcpServer.tool(
      'send_notification',
      {
        user_id: z.string().uuid().describe('ID người nhận thông báo'),
        title: z.string().describe('Tiêu đề thông báo'),
        message: z.string().describe('Nội dung thông báo'),
        channel: z.enum(['in-app', 'slack', 'email']).optional().describe('Kênh gửi ưu tiên'),
        priority: z.enum(['critical', 'high', 'normal', 'low']).optional().describe('Độ ưu tiên')
      },
      async ({ user_id, title, message, channel, priority }, extra) => {
        const tenantId = extra.tenantId;

        // BẢO MẬT: Bắt buộc inject tenantId và xác minh user thuộc tenant trước khi gửi
        const userExists = await this.notificationService.verifyUserInTenant(user_id, tenantId);
        if (!userExists) {
          throw new Error(`User ${user_id} does not belong to tenant ${tenantId}`);
        }

        // Thực thi gửi thông báo
        const result = await this.notificationService.sendDirect({
          tenantId,
          userId: user_id,
          title,
          body: message,
          channel: channel || 'in-app',
          priority: priority || 'normal'
        });

        return { content: [{ type: 'text', text: JSON.stringify({ success: true, notification_id: result.id }) }] };
      }
    );
  }

  @Sse()
  connect(@Req() req, @Headers('X-Tenant-ID') tenantId: string): Observable<MessageEvent> {
    const transport = new SSEServerTransport(`/api/v1/notification/mcp/messages`, req.res);
    this.mcpServer.connect(transport);
    return transport.sseStream;
  }

  @Post('messages')
  async handleMessage(@Req() req, @Body() body: any, @Headers('X-Tenant-ID') tenantId: string) {
    const transport = this.getTransportForTenant(tenantId);
    await transport.handleMessage(body, { tenantId });
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
  - `X-User-Permissions`: Chuỗi CSV chứa danh sách quyền của người dùng (ví dụ: `notification:{resource}:{action}`).
  - `X-Permissions-Signature`: Chữ ký HMAC-SHA256 dạng hex.
- Dịch vụ tính toán signature dự kiến bằng khóa bí mật `GATEWAY_SIGNING_SECRET`:
  `expected_sig = HMAC_SHA256(GATEWAY_SIGNING_SECRET, X-Tenant-ID + ":" + X-User-ID + ":" + X-User-Permissions)`
- So sánh chữ ký nhận được với `expected_sig` sử dụng hàm so sánh an toàn chống Side-channel attack (ví dụ: so sánh độ dài không đổi/safe compare). Nếu không khớp, từ chối request với mã lỗi `403 Forbidden` và tăng counter metric lỗi bảo mật.

### 2. So khớp quyền hạn In-Memory O(1)
- Sau khi chữ ký được xác thực, dịch vụ chuyển chuỗi `X-User-Permissions` thành một cấu trúc Set để tìm kiếm với độ phức tạp $O(1)$.
- Đối với mỗi API endpoint yêu cầu quyền hạn `notification:{resource}:{action}`, dịch vụ kiểm tra quyền trong Set:
  - Nếu Set chứa `*` (Super Admin), cho phép truy cập.
  - Nếu Set chứa `notification:*` (Toàn quyền trên dịch vụ), cho phép truy cập.
  - Nếu Set chứa `notification:{resource}:*` (Toàn quyền trên tài nguyên), cho phép truy cập.
  - Nếu Set chứa chính xác `notification:{resource}:{action}`, cho phép truy cập.
  - Ngược lại, từ chối truy cập và trả về mã lỗi `403 Forbidden` kèm log lỗi chi tiết.

## Error Handling

| Scenario | Xử lý |
|----------|--------|
| Slack API down | Fallback to email, then push |
| Email bounce | Mark email invalid, try push |
| FCM token expired | Remove token, try other channels |
| All channels fail | Queue for retry (max 3x, 5min interval) |
| User has no preferences | Use defaults: all channels enabled |
| Recipient not found | Log error, skip (don't crash) |
| MCP Session timeout | Hủy session và giải phóng tài nguyên transport của tenant tương ứng |
| MCP Cross-tenant access attempt | Báo lỗi JSON-RPC Invalid Request và ghi nhận vi phạm an ninh |

---

## Business Logic — Service Self-Registration

### 1. Logic Đăng ký (Startup Hook)
* BƯỚC 1: Gọi hàm `_get_internal_ip()` sử dụng socket UDP giả lập kết nối tới `8.8.8.8:80` để lấy IP nội bộ của container.
* BƯỚC 2: Định nghĩa chuỗi node dạng `{ip}:{port}`.
* BƯỚC 3: Thực hiện pipeline ghi vào Redis:
  * `SADD registry:service:notification "{ip}:{port}"`
  * `SETEX registry:service:notification:node:{ip}:{port} 15 "alive"`
* BƯỚC 4: Bắt đầu chạy vòng lặp heartbeat (mỗi 5 giây) để gửi lại gói tin `SETEX` và `SADD` để làm mới TTL.

### 2. Logic Hủy đăng ký (Shutdown Hook)
* BƯỚC 1: Dừng vòng lặp heartbeat.
* BƯỚC 2: Thực hiện pipeline dọn dẹp Redis:
  * `SREM registry:service:notification "{ip}:{port}"`
  * `DEL registry:service:notification:node:{ip}:{port}"`
