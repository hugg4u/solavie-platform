# Business Logic — Comment Manager Service

## Tổng quan vai trò (CẬP NHẬT)

Comment Manager xử lý **bình luận trên bài đăng**: auto-classify, auto-action (hide spam, reply questions, escalate negatives), learn from human overrides.

**Thay đổi với AI Core ReAct Agent:**
- Comment Manager gọi AI Core agent (use_case="comment_management")
- AI Core tự handle: classify comment + quyết định action
- AI Core có thể gọi tools: knowledge_base_search (tìm answer cho questions), hide_comment, send_notification (escalate)
- Comment Manager chỉ lo: trigger AI Core khi comment mới đến, lưu kết quả, handle overrides

## Luồng xử lý chi tiết

### Luồng 1: Comment Classification & Auto-Action

```
Kafka: channel.comment.received
│
▼
┌─────────────────────────────────┐
│ 1. PARSE COMMENT EVENT          │
│    - Extract: content, author,  │
│      post_id, platform          │
│    - Identify tenant from post  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. CLASSIFY (AI Core)           │
│    - Call AI Core classification │
│    - Categories: spam, negative,│
│      question, praise, neutral  │
│    - Get confidence score       │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 3. SAVE COMMENT                 │
│    - Store in DB with           │
│      classification + confidence│
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 4. EXECUTE AUTO-ACTION          │
│    Based on classification:     │
│                                 │
│    spam → HIDE comment          │
│    negative → ESCALATE to agent │
│    question → AUTO-REPLY (AI)   │
│    praise → AUTO-LIKE (optional)│
│    neutral → no action          │
└─────────────────────────────────┘
```

**Classification Logic:**

```typescript
class CommentClassifier {
  async classify(comment: string, postContext: string): Promise<ClassificationResult> {
    const response = await this.aiCore.complete({
      tenant_id: this.tenantId,
      use_case: 'classification',
      system_prompt: COMMENT_CLASSIFICATION_PROMPT,
      messages: [
        { role: 'system', content: `Post context: ${postContext}` },
        { role: 'user', content: comment },
      ],
      max_tokens: 50,
      temperature: 0.0,
    });

    // Parse: {"classification": "question", "confidence": 0.91}
    return JSON.parse(response.content);
  }
}

const COMMENT_CLASSIFICATION_PROMPT = `Classify this comment on a social media post.
Categories:
- spam: Promotional, irrelevant links, bot-like repetitive text
- negative: Complaints, insults, dissatisfaction, threats
- question: Asking about product, price, availability, how-to
- praise: Compliments, positive feedback, recommendations
- neutral: General remarks, reactions, neither positive nor negative

Return JSON: {"classification": "category", "confidence": 0.0-1.0}`;
```

**Auto-Action Logic:**

```typescript
class CommentActionExecutor {
  async execute(comment: Comment, classification: ClassificationResult): Promise<void> {
    switch (classification.classification) {
      case 'spam':
        await this.hideComment(comment);
        break;

      case 'negative':
        await this.escalateComment(comment);
        break;

      case 'question':
        await this.autoReply(comment);
        break;

      case 'praise':
        // Optional: auto-like if platform supports
        await this.autoLike(comment);
        break;

      case 'neutral':
        // No action needed
        break;
    }
  }

  private async hideComment(comment: Comment): Promise<void> {
    // Call Channel Connector to hide on platform
    await this.channelConnector.hideComment(
      comment.channel_id,
      comment.platform_comment_id
    );
    
    // Update DB
    await this.commentRepo.update(comment.id, { is_hidden: true });
  }

  private async escalateComment(comment: Comment): Promise<void> {
    // Publish escalation event → Notification Service
    await this.kafka.publish('comment.escalation', {
      tenant_id: comment.tenant_id,
      comment_id: comment.id,
      post_id: comment.post_id,
      classification: 'negative',
      content: comment.content.substring(0, 200), // Preview
      author_name: comment.author_name,
    });
  }

  private async autoReply(comment: Comment): Promise<void> {
    // 1. Search Knowledge Base for answer
    const searchResults = await this.knowledgeBase.search({
      query: comment.content,
      tenant_id: comment.tenant_id,
      top_k: 3,
    });

    if (!searchResults.length || searchResults[0].score < 0.6) {
      // Can't find good answer → don't reply, let agent handle
      return;
    }

    // 2. Generate reply using AI Core
    const reply = await this.aiCore.complete({
      tenant_id: comment.tenant_id,
      use_case: 'chatbot', // Same model as chatbot
      system_prompt: `You are replying to a comment on a social media post.
Be brief (1-2 sentences). Be helpful and friendly.
Language: match the commenter's language.`,
      messages: [
        { role: 'system', content: `Context: ${searchResults.map(r => r.content).join('\n')}` },
        { role: 'user', content: comment.content },
      ],
      max_tokens: 150,
    });

    // 3. Post reply via Channel Connector
    await this.channelConnector.replyToComment(
      comment.channel_id,
      comment.platform_comment_id,
      reply.content
    );

    // 4. Update DB
    await this.commentRepo.update(comment.id, {
      auto_reply_sent: true,
      auto_reply_text: reply.content,
    });
  }
}
```

### Luồng 2: Human Override & Learning

```
Agent overrides classification (e.g., "spam" → "neutral")
│
▼
┌─────────────────────────────────┐
│ 1. SAVE OVERRIDE                │
│    - Record: original → new     │
│    - Who overrode, when         │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. UNDO AUTO-ACTION (if needed) │
│    - Was spam → hidden?         │
│      → Unhide comment           │
│    - Was question → auto-replied?│
│      → Can't undo (already sent)│
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 3. LEARNING (future improvement)│
│    - Store override as training │
│      data                       │
│    - When override rate > 20%   │
│      → alert: model needs       │
│      improvement                │
│    - Future: fine-tune or update│
│      classification prompt      │
└─────────────────────────────────┘
```

```typescript
class OverrideLearner {
  async recordOverride(commentId: string, newClassification: string, agentId: string) {
    const comment = await this.commentRepo.findById(commentId);
    
    // Save override record
    await this.overrideRepo.create({
      comment_id: commentId,
      tenant_id: comment.tenant_id,
      original_classification: comment.classification,
      new_classification: newClassification,
      overridden_by: agentId,
    });

    // Update comment
    await this.commentRepo.update(commentId, {
      classification: newClassification,
      is_override: true,
    });

    // Undo action if needed
    if (comment.classification === 'spam' && comment.is_hidden) {
      await this.channelConnector.unhideComment(
        comment.channel_id,
        comment.platform_comment_id
      );
      await this.commentRepo.update(commentId, { is_hidden: false });
    }

    // Check override rate
    await this.checkOverrideRate(comment.tenant_id);
  }

  private async checkOverrideRate(tenantId: string) {
    const stats = await this.getOverrideStats(tenantId, '7d');
    const overrideRate = stats.overrides / stats.total;

    if (overrideRate > 0.20) {
      // Alert: classification accuracy is low
      logger.warn(`High override rate for tenant ${tenantId}: ${(overrideRate * 100).toFixed(1)}%`);
      // Could trigger prompt update or model retraining
    }
  }
}
```

---

## Confidence Threshold

```typescript
// Only auto-act when confidence is high enough
const ACTION_THRESHOLDS = {
  spam: 0.85,      // High threshold — hiding is destructive
  negative: 0.70,  // Medium — escalation is safe (agent reviews)
  question: 0.80,  // High — auto-reply should be accurate
  praise: 0.60,    // Low — auto-like is harmless
};

async function shouldAutoAct(classification: string, confidence: number): boolean {
  const threshold = ACTION_THRESHOLDS[classification];
  return confidence >= threshold;
}

// If confidence below threshold → save classification but DON'T auto-act
// Agent will see it in queue and decide manually
```

---

## Audit Logging

Các action sau PHẢI ghi audit log (theo `shared/standards.md`), publish lên Kafka topic `audit.events`:

| Action | Khi nào | Ghi gì |
|--------|---------|--------|
| `comment.hide` | Ẩn comment (auto hoặc manual) | comment_id, classification, confidence, actor (ai_agent/user), reason |
| `comment.unhide` | Bỏ ẩn comment | comment_id, actor, reason |
| `comment.classification.override` | Human override classification | comment_id, original → new, agent_id |
| `comment.auto_reply` | Auto-reply gửi đi | comment_id, reply_text, confidence |

Vì hide comment là **destructive action**, audit log cho phép trace lại "AI ẩn comment nào, vì sao, confidence bao nhiêu" — quan trọng khi khách khiếu nại bị ẩn nhầm.

### Luồng 3: Xử lý MCP SSE JSON-RPC Requests

```
AI Core (MCP Host) ── X-Tenant-ID Header ──► Gateway (Kong) ──► Comment Manager Service (NestJS)
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ 1. ROUTE TO SSE      │
                                                          │    /api/v1/comments/ │
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
                                                                     ▼ (POST /messages)
                                                          ┌──────────────────────┐
                                                          │ 4. OVERWRITE TENANT  │
                                                          │    Inject tenant_id  │
                                                          │    into tool arguments│
                                                          └──────────┬───────────┘
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ 5. EXECUTE ACTION    │
                                                          │    Hide comment &    │
                                                          │    update DB where   │
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

**Mẫu triển khai logic bảo mật đa thuê trên MCP NestJS Controller (Comment Manager):**
```typescript
@Controller('api/v1/comments/mcp')
export class CommentMcpController {
  private mcpServer: McpServer;

  constructor(private readonly commentService: CommentService) {
    this.initMcpServer();
  }

  private initMcpServer() {
    this.mcpServer = new McpServer({ name: 'comment_moderator', version: '1.0.0' });
    this.mcpServer.tool(
      'hide_comment',
      {
        comment_id: z.string().uuid().describe('ID của bình luận trong hệ thống'),
        is_hidden: z.boolean().optional().default(true).describe('Trạng thái ẩn'),
        reason: z.string().optional().describe('Lý do kiểm duyệt')
      },
      async ({ comment_id, is_hidden, reason }, extra) => {
        const tenantId = extra.tenantId;

        // BẢO MẬT: Bắt buộc truy vấn có tenant_id để cấm truy cập chéo tenant
        const comment = await this.commentService.findOneAndVerify(comment_id, tenantId);
        if (!comment) {
          throw new Error('Comment not found or access denied');
        }

        // Thực thi ẩn trên platform và lưu DB
        await this.commentService.hide(comment.id, is_hidden, reason, tenantId);
        return { content: [{ type: 'text', text: JSON.stringify({ success: true }) }] };
      }
    );
  }

  @Sse()
  connect(@Req() req, @Headers('X-Tenant-ID') tenantId: string): Observable<MessageEvent> {
    const transport = new SSEServerTransport(`/api/v1/comments/mcp/messages`, req.res);
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

## Error Handling

| Scenario | Xử lý |
|----------|--------|
| AI Core classification fail | Save comment as "unclassified", queue for manual review |
| Auto-reply: KB no results | Don't reply, leave for agent |
| Auto-reply: AI Core fail | Don't reply, log error |
| Hide comment: platform API fail | Retry 1x, if fail → mark as "hide_pending" |
| Override: comment already actioned | Undo if possible (unhide), log if can't (reply already sent) |
| MCP Session timeout | Hủy session và giải phóng tài nguyên transport của tenant tương ứng |
| MCP Cross-tenant access attempt | Trả về lỗi JSON-RPC và ghi nhận hành vi xâm phạm an ninh |

