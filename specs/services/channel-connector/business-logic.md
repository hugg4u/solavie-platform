# Business Logic — Channel Connector Service

## Tổng quan vai trò

Channel Connector là **cầu nối** giữa hệ thống nội bộ và các platform bên ngoài (Facebook, Zalo, TikTok).
Nó làm 3 việc chính:
1. **Nhận** tin nhắn/comment từ platforms (webhook)
2. **Gửi** tin nhắn/bài viết ra platforms (outbound)
3. **Quản lý** OAuth tokens per channel per tenant

## Luồng xử lý chi tiết

### Luồng 1: Nhận Webhook (Inbound)

```
Platform (Facebook/Zalo/TikTok) POST webhook
│
▼
┌─────────────────────────────────┐
│ 1. VERIFY SIGNATURE             │
│    - Facebook: SHA256 HMAC      │
│    - Zalo: MAC verification     │
│    - TikTok: HMAC SHA256        │
│    → Fail = 403, không xử lý   │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. CHECK IDEMPOTENCY           │
│    - Hash event → check Redis   │
│    - Đã xử lý = skip, return 200│
│    - Chưa = tiếp tục           │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 3. IDENTIFY TENANT             │
│    - Lookup channel by          │
│      platform_id (page_id, etc)│
│    - Get tenant_id từ DB       │
│    → Không tìm thấy = log warn │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 4. NORMALIZE MESSAGE           │
│    - Platform-specific → Unified│
│    - Extract: text, attachments │
│    - Map sender_id, timestamp   │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 5. PUBLISH TO KAFKA            │
│    - Topic: channel.message.received │
│    - hoặc: channel.comment.received │
│    - Key: conversation_id       │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 6. RESPOND 200 OK              │
│    - PHẢI respond < 5s          │
│    - Facebook timeout = 20s     │
│    - Zalo timeout = 5s          │
└─────────────────────────────────┘
```

**Chi tiết từng bước:**

```typescript
// Step 1: Verify Signature
class WebhookVerifier {
  verifyFacebook(body: Buffer, signature: string): boolean {
    // Facebook gửi header: X-Hub-Signature-256
    const expected = crypto
      .createHmac('sha256', FB_APP_SECRET)
      .update(body)
      .digest('hex');
    return crypto.timingSafeEqual(
      Buffer.from(`sha256=${expected}`),
      Buffer.from(signature)
    );
  }

  verifyZalo(body: Buffer, signature: string): boolean {
    // Zalo gửi header: X-ZaloOA-Signature
    const expected = crypto
      .createHmac('sha256', ZALO_APP_SECRET)
      .update(body)
      .digest('hex');
    return expected === signature;
  }

  verifyTiktok(body: Buffer, signature: string): boolean {
    // TikTok gửi header: X-Tiktok-Signature
    const expected = crypto
      .createHmac('sha256', TIKTOK_CLIENT_SECRET)
      .update(body)
      .digest('hex');
    return crypto.timingSafeEqual(
      Buffer.from(expected),
      Buffer.from(signature)
    );
  }
}

// Step 2: Idempotency Check
class IdempotencyChecker {
  async isDuplicate(platform: string, eventId: string): Promise<boolean> {
    const key = `webhook:${platform}:${eventId}`;
    // SETNX: set if not exists, TTL 24h
    const result = await redis.set(key, '1', 'EX', 86400, 'NX');
    return result === null; // null = key already existed = duplicate
  }
}

// Step 4: Message Normalization
class MessageNormalizer {
  normalizeFacebook(event: any): UnifiedMessage {
    return {
      platform: 'facebook',
      sender_id: event.sender.id,
      conversation_id: `fb_${event.sender.id}`,
      content: event.message?.text || '',
      content_type: this.detectContentType(event.message),
      attachments: (event.message?.attachments || []).map(a => ({
        type: a.type, // 'image', 'video', 'file'
        url: a.payload?.url,
      })),
      timestamp: new Date(event.timestamp).toISOString(),
      metadata: { mid: event.message?.mid },
    };
  }

  normalizeZalo(event: any): UnifiedMessage {
    const eventName = event.event_name;
    return {
      platform: 'zalo',
      sender_id: event.sender.id,
      conversation_id: `zalo_${event.sender.id}`,
      content: eventName === 'user_send_text' ? event.message.text : '',
      content_type: this.zaloEventToContentType(eventName),
      attachments: this.extractZaloAttachments(event),
      timestamp: new Date(event.timestamp).toISOString(),
      metadata: { msg_id: event.message?.msg_id },
    };
  }

  normalizeTiktok(event: any): UnifiedMessage {
    const data = event.content;
    return {
      platform: 'tiktok',
      sender_id: data.sender.open_id,
      conversation_id: `tiktok_${data.sender.open_id}`,
      content: data.message_type === 'text' ? data.text : '',
      content_type: data.message_type,
      attachments: data.message_type === 'image'
        ? [{ type: 'image', url: data.image.url }]
        : [],
      timestamp: new Date(event.create_time * 1000).toISOString(),
      metadata: { event_id: event.event_id },
    };
  }
}
```

### Luồng 2: Gửi Message (Outbound)

```
Internal Service gọi: POST /api/v1/channels/:id/send
│
▼
┌─────────────────────────────────┐
│ 1. VALIDATE REQUEST             │
│    - Channel exists & active?   │
│    - Tenant owns this channel?  │
│    - Message format valid?      │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. GET ACCESS TOKEN             │
│    - Check Redis cache first    │
│    - If expired → refresh       │
│    - If refresh fail → error    │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 3. CONVERT TO PLATFORM FORMAT   │
│    - Unified → Facebook/Zalo/TT │
│    - Handle character limits    │
│    - Handle attachment upload   │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 4. CALL PLATFORM API            │
│    (via Circuit Breaker)        │
│    - Success → publish sent event│
│    - Fail → retry (max 3)      │
│    - All retries fail → error   │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 5. PUBLISH KAFKA EVENT          │
│    - channel.message.sent       │
│    - status: delivered/failed   │
└─────────────────────────────────┘
```

**Platform-specific send logic:**

```typescript
class OutboundSender {
  async sendFacebook(channelId: string, message: UnifiedOutbound): Promise<SendResult> {
    const token = await this.tokenManager.getToken(channelId);
    const url = `https://graph.facebook.com/v18.0/me/messages`;

    const payload: any = {
      recipient: { id: message.recipient_id },
      message: {},
    };

    // Convert content type
    if (message.content_type === 'text') {
      payload.message.text = message.content;
    } else if (message.content_type === 'image') {
      payload.message.attachment = {
        type: 'image',
        payload: { url: message.attachments[0].url },
      };
    }

    const response = await this.httpClient.post(url, payload, {
      params: { access_token: token },
    });

    return { platform_message_id: response.data.message_id, status: 'delivered' };
  }

  async sendZalo(channelId: string, message: UnifiedOutbound): Promise<SendResult> {
    const token = await this.tokenManager.getToken(channelId);
    const url = 'https://openapi.zalo.me/v3.0/oa/message/cs';

    const payload = {
      recipient: { user_id: message.recipient_id },
      message: { text: message.content },
    };

    const response = await this.httpClient.post(url, payload, {
      headers: { access_token: token },
    });

    return { platform_message_id: response.data.message_id, status: 'delivered' };
  }

  async sendTiktok(channelId: string, message: UnifiedOutbound): Promise<SendResult> {
    const token = await this.tokenManager.getToken(channelId);
    const url = 'https://open.tiktokapis.com/v2/im/message/send/';

    const payload = {
      recipient: { open_id: message.recipient_id },
      message_type: 'text',
      text: { text: message.content },
    };

    const response = await this.httpClient.post(url, payload, {
      headers: { Authorization: `Bearer ${token}` },
    });

    return { platform_message_id: response.data.message_id, status: 'delivered' };
  }
}
```

### Luồng 3: Token Management

```
Background Cron Job (mỗi 10 phút)
│
▼
┌─────────────────────────────────┐
│ 1. QUERY EXPIRING TOKENS        │
│    - WHERE token_expires_at      │
│      < NOW() + 15 minutes       │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. REFRESH EACH TOKEN           │
│    - Facebook: exchange token   │
│    - Zalo: POST refresh_token   │
│    - TikTok: POST refresh       │
└────────────┬────────────────────┘
             │
         ┌───┴───┐
         ▼       ▼
      Success   Failure
         │       │
         ▼       ▼
┌──────────┐  ┌──────────────────┐
│Update DB │  │ Retry 1 lần      │
│Update    │  │ If still fail:   │
│Redis     │  │ - Mark channel   │
│cache     │  │   status='error' │
└──────────┘  │ - Notify admin   │
              └──────────────────┘
```

```typescript
class TokenManager {
  // Token refresh strategies per platform
  private refreshStrategies = {
    facebook: {
      // Facebook long-lived token: 60 days
      // Refresh 7 days before expiry
      refreshBefore: 7 * 24 * 60 * 60 * 1000, // 7 days in ms
      async refresh(channel: Channel): Promise<TokenResult> {
        const url = `https://graph.facebook.com/v18.0/oauth/access_token`;
        const response = await httpClient.get(url, {
          params: {
            grant_type: 'fb_exchange_token',
            client_id: FB_APP_ID,
            client_secret: FB_APP_SECRET,
            fb_exchange_token: channel.access_token,
          },
        });
        return {
          access_token: response.data.access_token,
          expires_in: response.data.expires_in, // seconds
        };
      },
    },

    zalo: {
      // Zalo access token: 1 hour
      // Refresh every 50 minutes
      refreshBefore: 10 * 60 * 1000, // 10 minutes before expiry
      async refresh(channel: Channel): Promise<TokenResult> {
        const url = 'https://oauth.zaloapp.com/v4/oa/access_token';
        const response = await httpClient.post(url, {
          refresh_token: channel.refresh_token,
          app_id: ZALO_APP_ID,
          grant_type: 'refresh_token',
        });
        return {
          access_token: response.data.access_token,
          refresh_token: response.data.refresh_token, // Zalo issues new refresh token
          expires_in: 3600,
        };
      },
    },

    tiktok: {
      // TikTok access token: 24 hours
      // Refresh 2 hours before expiry
      refreshBefore: 2 * 60 * 60 * 1000,
      async refresh(channel: Channel): Promise<TokenResult> {
        const url = 'https://open.tiktokapis.com/v2/oauth/token/';
        const response = await httpClient.post(url, {
          client_key: TIKTOK_CLIENT_KEY,
          client_secret: TIKTOK_CLIENT_SECRET,
          grant_type: 'refresh_token',
          refresh_token: channel.refresh_token,
        });
        return {
          access_token: response.data.access_token,
          refresh_token: response.data.refresh_token,
          expires_in: response.data.expires_in,
        };
      },
    },
  };

  async getToken(channelId: string): Promise<string> {
    // 1. Check Redis cache
    const cached = await redis.get(`token:${channelId}`);
    if (cached) return cached;

    // 2. Get from DB
    const channel = await channelRepo.findById(channelId);
    if (!channel) throw new ChannelNotFound(channelId);

    // 3. Check if expired
    if (channel.token_expires_at < new Date()) {
      // Token expired, need refresh
      const result = await this.refreshToken(channel);
      return result.access_token;
    }

    // 4. Cache and return
    const ttl = Math.floor((channel.token_expires_at.getTime() - Date.now()) / 1000);
    await redis.setex(`token:${channelId}`, ttl, channel.access_token);
    return channel.access_token;
  }
}
```

### Luồng 4: Circuit Breaker per Platform

```typescript
class PlatformCircuitBreaker {
  private breakers: Map<string, CircuitBreaker> = new Map();

  constructor() {
    // 1 circuit breaker per platform (not per channel)
    ['facebook', 'zalo', 'tiktok'].forEach(platform => {
      this.breakers.set(platform, new CircuitBreaker({
        timeout: 10000,              // 10s timeout per request
        errorThresholdPercentage: 50, // 50% errors → trip
        resetTimeout: 60000,          // 60s before half-open
        volumeThreshold: 5,           // min 5 requests before evaluating
      }));
    });
  }

  async callPlatform(platform: string, fn: () => Promise<any>): Promise<any> {
    const breaker = this.breakers.get(platform);

    try {
      return await breaker.fire(fn);
    } catch (error) {
      if (error instanceof CircuitBreakerOpenError) {
        // Circuit is OPEN — platform is down
        // Queue message for retry later
        await this.queueForRetry(platform, fn);
        throw new PlatformUnavailable(platform);
      }
      throw error;
    }
  }

  // Khi circuit opens → notify
  onCircuitOpen(platform: string) {
    // Publish event cho Notification Service
    kafka.publish('channel.platform.down', {
      platform,
      timestamp: new Date().toISOString(),
    });
    // Update metrics
    metrics.circuitBreakerState.set({ platform }, 1); // 1 = open
  }
}
```

---

## Unified Message Format

```typescript
interface UnifiedMessage {
  platform: 'facebook' | 'zalo' | 'tiktok';
  sender_id: string;           // Platform user ID
  conversation_id: string;     // Unique per sender per platform
  content: string;             // Text content
  content_type: 'text' | 'image' | 'video' | 'file' | 'sticker';
  attachments: Attachment[];
  timestamp: string;           // ISO8601
  metadata: Record<string, any>; // Platform-specific data
}

interface Attachment {
  type: 'image' | 'video' | 'file' | 'audio';
  url: string;
  filename?: string;
  size_bytes?: number;
}

interface UnifiedOutbound {
  recipient_id: string;        // Platform user ID to send to
  content: string;
  content_type: 'text' | 'image' | 'video' | 'file';
  attachments?: Attachment[];
}
```

---


## Zero-Trust Security & Dynamic RBAC Logic

Dịch vụ thực hiện cơ chế xác thực Zero-Trust và phân quyền động (Dynamic RBAC) dựa trên HMAC Signed Headers được truyền từ API Gateway:

### 1. Quy trình xác thực chữ ký (HMAC Verification Flow)
- Dịch vụ trích xuất các headers từ request:
  - `X-Tenant-ID`: ID của Tenant.
  - `X-User-ID`: ID của User.
  - `X-User-Permissions`: Chuỗi CSV chứa danh sách quyền của người dùng (ví dụ: `channel-connector:{resource}:{action}`).
  - `X-Permissions-Signature`: Chữ ký HMAC-SHA256 dạng hex.
- Dịch vụ tính toán signature dự kiến bằng khóa bí mật `GATEWAY_SIGNING_SECRET`:
  `expected_sig = HMAC_SHA256(GATEWAY_SIGNING_SECRET, X-Tenant-ID + ":" + X-User-ID + ":" + X-User-Permissions)`
- So sánh chữ ký nhận được với `expected_sig` sử dụng hàm so sánh an toàn chống Side-channel attack (ví dụ: so sánh độ dài không đổi/safe compare). Nếu không khớp, từ chối request với mã lỗi `403 Forbidden` và tăng counter metric lỗi bảo mật.

### 2. So khớp quyền hạn In-Memory O(1)
- Sau khi chữ ký được xác thực, dịch vụ chuyển chuỗi `X-User-Permissions` thành một cấu trúc Set để tìm kiếm với độ phức tạp $O(1)$.
- Đối với mỗi API endpoint yêu cầu quyền hạn `channel-connector:{resource}:{action}`, dịch vụ kiểm tra quyền trong Set:
  - Nếu Set chứa `*` (Super Admin), cho phép truy cập.
  - Nếu Set chứa `channel-connector:*` (Toàn quyền trên dịch vụ), cho phép truy cập.
  - Nếu Set chứa `channel-connector:{resource}:*` (Toàn quyền trên tài nguyên), cho phép truy cập.
  - Nếu Set chứa chính xác `channel-connector:{resource}:{action}`, cho phép truy cập.
  - Ngược lại, từ chối truy cập và trả về mã lỗi `403 Forbidden` kèm log lỗi chi tiết.

## Error Handling

| Scenario | Xử lý |
|----------|--------|
| Webhook signature invalid | Return 403, log security warning |
| Duplicate webhook | Return 200 (idempotent), skip processing |
| Channel not found for webhook | Log warn, return 200 (don't retry) |
| Kafka publish fail | Retry 3x, if still fail → log error + return 500 (platform will retry webhook) |
| Send message: platform 429 (rate limit) | Queue, retry after Retry-After header |
| Send message: platform 500 | Retry 3x exponential backoff |
| Send message: circuit open | Queue for later, return error to caller |
| Token refresh fail | Retry 1x, mark channel status='error', notify admin |

---

## Business Logic — Service Self-Registration

### 1. Logic Đăng ký (Startup Hook)
* BƯỚC 1: Gọi hàm `_get_internal_ip()` sử dụng socket UDP giả lập kết nối tới `8.8.8.8:80` để lấy IP nội bộ của container.
* BƯỚC 2: Định nghĩa chuỗi node dạng `{ip}:{port}`.
* BƯỚC 3: Thực hiện pipeline ghi vào Redis:
  * `SADD registry:service:channel-connector "{ip}:{port}"`
  * `SETEX registry:service:channel-connector:node:{ip}:{port} 15 "alive"`
* BƯỚC 4: Bắt đầu chạy vòng lặp heartbeat (mỗi 5 giây) để gửi lại gói tin `SETEX` và `SADD` để làm mới TTL.

### 2. Logic Hủy đăng ký (Shutdown Hook)
* BƯỚC 1: Dừng vòng lặp heartbeat.
* BƯỚC 2: Thực hiện pipeline dọn dẹp Redis:
  * `SREM registry:service:channel-connector "{ip}:{port}"`
  * `DEL registry:service:channel-connector:node:{ip}:{port}"`
