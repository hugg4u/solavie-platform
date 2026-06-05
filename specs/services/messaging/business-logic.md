# Business Logic — Messaging Service

## Tổng quan vai trò

Messaging Service là **trung tâm quản lý hội thoại**. Nó:
1. Consume messages từ Kafka (đã normalize bởi Channel Connector)
2. Lưu vào DB, gắn vào conversation đúng
3. Route: gọi Chatbot (auto) hoặc push cho Agent (manual)
4. Nhận reply từ Agent → forward cho Channel Connector
5. Push realtime qua WebSocket

## Luồng xử lý chi tiết

### Luồng 1: Nhận Message Mới (Kafka Consumer)

```
Kafka: channel.message.received
│
▼
┌─────────────────────────────────┐
│ 1. PARSE EVENT                  │
│    - Deserialize Kafka message  │
│    - Validate schema            │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. FIND OR CREATE CONVERSATION  │
│    - Lookup by tenant_id +      │
│      platform + sender_id       │
│    - If not exists → create new │
│    - Update last_message_at     │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 3. FIND OR CREATE CONTACT       │
│    - Lookup by platform +       │
│      sender_id                  │
│    - If new → create + publish  │
│      crm.contact.created event  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 4. SAVE MESSAGE                 │
│    - Insert into messages table │
│    - Update conversation preview│
│    - Increment unread_count     │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 5. ROUTE MESSAGE                │
│    - Check conversation.mode    │
│    - "auto" → gRPC Chatbot     │
│    - "manual" → WebSocket push  │
└────────────┬────────────────────┘
             │
         ┌───┴───────┐
         ▼           ▼
      Mode=auto   Mode=manual
         │           │
         ▼           ▼
┌──────────────┐  ┌──────────────┐
│ Call Chatbot │  │ WS Broadcast │
│ via gRPC    │  │ to Agent     │
└──────┬───────┘  └──────────────┘
       │
       ▼
┌──────────────────────────────────┐
│ 6. HANDLE CHATBOT RESPONSE      │
│    - action=REPLY → save bot msg│
│      + send via Channel Connector│
│    - action=HANDOFF → switch to │
│      manual + notify agent      │
│    - action=CLARIFY → save bot  │
│      msg (asking for more info) │
└──────────────────────────────────┘
```

**Chi tiết routing logic:**

```typescript
class MessageRouter {
  async route(conversation: Conversation, message: Message): Promise<void> {
    if (conversation.mode === 'auto') {
      await this.routeToChatbot(conversation, message);
    } else {
      // mode === 'manual'
      await this.routeToAgent(conversation, message);
    }
  }

  private async routeToChatbot(conv: Conversation, msg: Message): Promise<void> {
    // Get recent history for context
    const history = await this.messageRepo.getRecent(conv.id, 10);

    // Call Chatbot via gRPC
    const response = await this.chatbotClient.processMessage({
      tenant_id: conv.tenant_id,
      conversation_id: conv.id,
      message_content: msg.content,
      language: conv.detected_language || 'auto',
      history: history.map(m => ({
        role: m.sender_type,
        content: m.content,
        timestamp: m.created_at.toISOString(),
      })),
    });

    // Handle response based on action
    switch (response.action) {
      case 'REPLY':
        // Save bot message
        const botMsg = await this.saveMessage({
          conversation_id: conv.id,
          tenant_id: conv.tenant_id,
          sender_type: 'bot',
          sender_id: 'chatbot',
          content: response.response_text,
          confidence_score: response.confidence_score,
          sentiment: response.sentiment,
        });

        // Send to customer via Channel Connector
        await this.channelConnector.send(conv.channel_id, {
          recipient_id: conv.contact_external_id,
          content: response.response_text,
          content_type: 'text',
        });

        // Broadcast to dashboard (agent can see bot replies)
        await this.wsBroadcast(conv.id, botMsg);
        break;

      case 'HANDOFF':
        await this.executeHandoff(conv, response);
        break;

      case 'CLARIFY':
        // Bot asks clarifying question — same as REPLY but different intent
        // Save and send the clarification question
        await this.saveAndSend(conv, response.response_text, 'bot');
        break;
    }
  }

  private async executeHandoff(conv: Conversation, response: ChatResponse): Promise<void> {
    // 1. Switch conversation to manual mode
    await this.conversationRepo.update(conv.id, { mode: 'manual' });

    // 2. Auto-assign to available agent (round-robin or least-busy)
    const agent = await this.findAvailableAgent(conv.tenant_id);
    if (agent) {
      await this.conversationRepo.update(conv.id, { assigned_agent_id: agent.id });
    }

    // 3. Publish handoff event → Notification Service
    await this.kafka.publish('messaging.handoff.requested', {
      tenant_id: conv.tenant_id,
      conversation_id: conv.id,
      assigned_agent_id: agent?.id,
      reason: response.confidence_score < 0.7 ? 'low_confidence' : 'sentiment_negative',
      confidence_score: response.confidence_score,
    });

    // 4. Send handoff message to customer
    const handoffMsg = this.getHandoffMessage(conv.detected_language);
    await this.saveAndSend(conv, handoffMsg, 'bot');

    // 5. WebSocket notify agent
    await this.wsBroadcast(conv.id, {
      type: 'handoff',
      conversation: conv,
      reason: 'low_confidence',
    });
  }

  private async routeToAgent(conv: Conversation, msg: Message): Promise<void> {
    // Just broadcast to assigned agent via WebSocket
    await this.wsBroadcast(conv.id, msg);
  }

  private getHandoffMessage(language: string): string {
    const messages = {
      vi: 'Mình sẽ chuyển bạn cho nhân viên hỗ trợ. Vui lòng đợi trong giây lát.',
      en: 'Let me connect you with a support agent. Please hold on.',
    };
    return messages[language] || messages['vi'];
  }
}
```

### Luồng 2: Agent Reply

```
Agent gửi reply qua Dashboard
│
▼
┌─────────────────────────────────┐
│ 1. VALIDATE                     │
│    - Agent assigned to conv?    │
│    - Conversation is open?      │
│    - Content not empty?         │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. SAVE MESSAGE                 │
│    - sender_type = 'agent'      │
│    - Update conversation        │
│      last_message_at            │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 3. SEND VIA CHANNEL CONNECTOR   │
│    - REST call to send endpoint │
│    - Include channel_id +       │
│      recipient_id               │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 4. BROADCAST WEBSOCKET          │
│    - Notify other agents viewing│
│      same conversation          │
└─────────────────────────────────┘
```

### Luồng 3: WebSocket Connection

```typescript
class WebSocketGateway {
  // Agent connects
  async handleConnection(client: Socket): Promise<void> {
    // 1. Validate JWT token from handshake
    const token = client.handshake.auth.token;
    const user = await this.validateToken(token);
    if (!user) { client.disconnect(); return; }

    // 2. Join tenant room
    client.join(`tenant:${user.tenant_id}`);

    // 3. Join assigned conversations
    const conversations = await this.getAgentConversations(user.id);
    conversations.forEach(conv => {
      client.join(`conversation:${conv.id}`);
    });
  }

  // Subscribe to specific conversations
  async handleSubscribe(client: Socket, conversationIds: string[]): Promise<void> {
    conversationIds.forEach(id => {
      client.join(`conversation:${id}`);
    });
  }

  // Broadcast new message to conversation room
  async broadcastMessage(conversationId: string, message: any): Promise<void> {
    // Redis Pub/Sub ensures broadcast across all instances
    await this.redisPublisher.publish(
      `ws:conversation:${conversationId}`,
      JSON.stringify({ type: 'message.new', data: message })
    );
  }
}

// Redis subscriber (handles cross-instance broadcast)
class RedisWsSubscriber {
  async onMessage(channel: string, data: string): Promise<void> {
    const parsed = JSON.parse(data);
    const conversationId = channel.replace('ws:conversation:', '');
    // Emit to all local WebSocket clients in this conversation room
    this.io.to(`conversation:${conversationId}`).emit(parsed.type, parsed.data);
  }
}
```

### Luồng 4: Conversation Auto-Close

```typescript
// Cron job chạy mỗi 1 giờ
class ConversationAutoCloser {
  async run(): Promise<void> {
    // Find conversations inactive > 24h
    const stale = await this.conversationRepo.findStale({
      last_message_at: { lt: new Date(Date.now() - 24 * 60 * 60 * 1000) },
      status: 'open',
    });

    for (const conv of stale) {
      await this.conversationRepo.update(conv.id, { status: 'closed' });
      // Notify via WebSocket
      await this.wsBroadcast(conv.id, { type: 'conversation.closed', reason: 'inactivity' });
    }
  }
}
```

### Luồng 5: Agent Assignment (Round-Robin)

```typescript
class AgentAssigner {
  async findAvailableAgent(tenantId: string): Promise<Agent | null> {
    // 1. Get online agents for this tenant
    const onlineAgents = await this.getOnlineAgents(tenantId);
    if (onlineAgents.length === 0) return null;

    // 2. Get current assignment counts
    const counts = await this.getAssignmentCounts(onlineAgents.map(a => a.id));

    // 3. Pick agent with least active conversations (least-busy)
    const sorted = onlineAgents.sort((a, b) => 
      (counts[a.id] || 0) - (counts[b.id] || 0)
    );

    return sorted[0];
  }

  private async getOnlineAgents(tenantId: string): Promise<Agent[]> {
    // Check Redis for online status (set by WebSocket connection)
    const agentIds = await redis.smembers(`online_agents:${tenantId}`);
    return this.agentRepo.findByIds(agentIds);
  }
}
```

---

## Batch Processing (Tối ưu)

Thay vì xử lý từng message 1-by-1 từ Kafka, batch nhiều messages để giảm DB round-trips.

```typescript
class MessageBatchConsumer {
  private batch: KafkaMessage[] = [];
  private readonly BATCH_SIZE = 100;
  private readonly FLUSH_INTERVAL_MS = 200; // flush mỗi 200ms dù chưa đủ batch

  async onMessages(messages: KafkaMessage[]) {
    this.batch.push(...messages);
    if (this.batch.length >= this.BATCH_SIZE) {
      await this.flush();
    }
  }

  // Timer flush để đảm bảo latency thấp khi traffic ít
  startFlushTimer() {
    setInterval(() => this.flush(), this.FLUSH_INTERVAL_MS);
  }

  private async flush() {
    if (this.batch.length === 0) return;
    const toProcess = this.batch.splice(0, this.batch.length);

    // Bulk operations trong 1 transaction
    await this.db.transaction(async (tx) => {
      // 1. Bulk upsert conversations (1 query thay vì N)
      await tx.conversations.bulkUpsert(extractConversations(toProcess));
      // 2. Bulk insert messages
      await tx.messages.bulkInsert(extractMessages(toProcess));
    });

    // 3. Route mỗi message (gRPC/WebSocket — không batch được vì cần realtime)
    await Promise.all(toProcess.map(m => this.router.route(m)));
  }
}
// Lợi ích: giảm 30-40% DB latency khi traffic cao.
// Trade-off: thêm tối đa 200ms latency khi traffic thấp (chấp nhận được).
```

**Lưu ý:** Routing (gọi Chatbot gRPC / WebSocket push) KHÔNG batch — vẫn xử lý per-message để giữ realtime. Chỉ batch phần DB writes.

## Error Handling

### Luồng 6: Xử lý MCP SSE JSON-RPC Requests

```
AI Core (MCP Host) ── X-Tenant-ID Header ──► Gateway (Kong) ──► Messaging Service
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ 1. ROUTE TO SSE      │
                                                          │    /api/v1/messaging/│
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
                                                          │    Stream Transport  │
                                                          └──────────┬───────────┘
                                                                     │
                                         ┌───────────────────────────┴───────────────────────────┐
                                         ▼ (POST /messages)                                      ▼ (POST /messages)
                                 Tool: send_message                                      Tool: handoff_to_agent
                                         │                                                       │
                                         ▼                                                       ▼
                            ┌────────────────────────┐                              ┌────────────────────────┐
                            │ 4.1 OVERWRITE TENANT   │                              │ 5.1 OVERWRITE TENANT   │
                            │     Inject tenant_id   │                              │     Inject tenant_id   │
                            │     into arguments     │                              │     into arguments     │
                            └──────────┬─────────────┘                              └──────────┬─────────────┘
                                       │                                                       │
                                       ▼                                                       ▼
                            ┌────────────────────────┐                              ┌────────────────────────┐
                            │ 4.2 DB VALIDATION      │                              │ 5.2 CHUYỂN ĐỔI CHẾ ĐỘ  │
                            │     Query conversation │                              │     Cập nhật conv      │
                            │     where id=conv_id   │                              │     mode='manual'      │
                            │     AND tenant_id=T_ID │                              │     where tenant_id=   │
                            └──────────┬─────────────┘                              │     T_ID               │
                                       │                                            └──────────┬─────────────┘
                                       ▼                                                       │
                            ┌────────────────────────┐                                         ▼
                            │ 4.3 THỰC THI GỬI TIN   │                              ┌────────────────────────┐
                            │     Gửi qua Channel    │                              │ 5.3 ASSIGN & NOTIFY    │
                            │     Connector          │                              │     Tìm Agent khả dụng │
                            └──────────┬─────────────┘                              │     và gửi event       │
                                       │                                            └──────────┬─────────────┘
                                       ▼                                                       │
                            ┌────────────────────────┐                                         ▼
                            │ 4.4 RESPONSE           │                              ┌────────────────────────┐
                            │     Return JSON-RPC    │                              │ 5.4 RESPONSE           │
                            │     success payload    │                              │     Return JSON-RPC    │
                            └────────────────────────┘                              │     success payload    │
                                                                                    └────────────────────────┘
```

**Mẫu triển khai logic bảo mật đa thuê trên MCP Tools:**
```typescript
// Định nghĩa tools nghiệp vụ trong NestJS MCP Server
this.mcpServer.tool(
  'send_message',
  {
    conversation_id: z.string().uuid().describe('ID cuộc hội thoại'),
    content: z.string().describe('Nội dung tin nhắn'),
    content_type: z.enum(['text', 'image', 'file']).optional()
  },
  async ({ conversation_id, content, content_type }, extra) => {
    // Trích xuất tenantId được tự động inject bởi Controller từ header X-Tenant-ID
    const tenantId = extra.tenantId;

    // BẢO MẬT: Bắt buộc truy vấn kèm tenantId để ngăn chặn rò rỉ chéo tenant
    const conversation = await this.prisma.conversation.findFirst({
      where: {
        id: conversation_id,
        tenant_id: tenantId
      }
    });

    if (!conversation) {
      throw new Error(`Conversation not found or access denied for tenant ${tenantId}`);
    }

    // Thực thi logic gửi tin nhắn
    const message = await this.messageService.createAndSend({
      conversationId: conversation.id,
      tenantId,
      senderType: 'bot',
      senderId: 'mcp-agent',
      content,
      contentType: content_type || 'text'
    });

    return {
      content: [{ type: 'text', text: JSON.stringify({ success: true, message_id: message.id }) }]
    };
  }
);
```

---

## Error Handling

| Scenario | Xử lý |
|----------|--------|
| Chatbot gRPC timeout (> 5s) | Auto-handoff, log timeout |
| Chatbot gRPC unavailable | Auto-handoff, circuit breaker |
| Channel Connector send fail | Log error, mark message as failed, notify agent |
| Kafka consume error | Retry (Kafka built-in), DLQ after 3 failures |
| WebSocket disconnect | Remove from rooms, update online status |
| DB write fail | Retry 1x, if fail → return error to Kafka (will redeliver) |
| No agent available for handoff | Queue conversation, send "agent will respond soon" to customer |
| MCP Session timeout | Hủy session và giải phóng tài nguyên transport của tenant tương ứng |
| MCP Cross-tenant access attempt | Báo lỗi JSON-RPC và ghi nhận vào audit logs cảnh báo bảo mật |

