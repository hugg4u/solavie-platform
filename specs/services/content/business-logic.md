# Business Logic — Content Service

## Tổng quan vai trò (CẬP NHẬT)

Content Service quản lý **vòng đời nội dung**: từ AI generate → adapt platform → quality check → approval → schedule publish.

**Thay đổi với AI Core ReAct Agent:**
- Content Service không cần tự gọi Knowledge Base + Analytics riêng nữa
- Gọi AI Core agent (use_case="content_generation") → AI Core tự:
  - Search KB cho brand voice + product info (tool: knowledge_base_search)
  - Search web cho trends + tin tức (tool: web_search)
  - Query analytics cho top posts (tool: analytics_query)
  - Get trending hashtags (tool: get_social_trends)
  - Generate content dựa trên tất cả context thu thập được
- Content Service chỉ lo: approval workflow, versioning, scheduling

## Luồng xử lý chi tiết

### Luồng 1: AI Content Generation

```
User request: "Viết bài Facebook về sản phẩm A, target gen Z"
│
▼
┌─────────────────────────────────┐
│ 1. VALIDATE REQUEST             │
│    - topic required             │
│    - platform(s) specified      │
│    - tenant_id from JWT         │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. RETRIEVE BRAND CONTEXT (RAG) │
│    - Call Knowledge Base search  │
│    - Query: brand_voice +       │
│      product info + guidelines  │
│    - Filter: doc_type in        │
│      [brand_guide, product]     │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 3. GET TREND DATA               │
│    - Query Analytics: top posts │
│      for this tenant/platform   │
│    - Last 30 days, top 10      │
│    - Extract: what worked       │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 4. GENERATE CONTENT (AI Core)   │
│    - use_case: content_generation│
│    - Include: brand context +   │
│      trend data + user request  │
│    - Model: Claude Sonnet       │
│    - Output: text + hashtags +  │
│      CTA + suggested_time       │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 5. PLATFORM ADAPTATION          │
│    - Facebook: long, hashtags   │
│    - Zalo: formal, shorter     │
│    - TikTok: trendy, very short│
│    - Respect character limits   │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 6. QUALITY CHECK (AI Core)      │
│    - Grammar check              │
│    - Brand voice consistency    │
│    - Platform compliance        │
│    - Score: 0.0 - 1.0          │
│    - If < 0.7 → regenerate     │
└────────────┬────────────────────┘
             │
         ┌───┴───┐
         ▼       ▼
     Score>=0.7  Score<0.7
         │       │
         ▼       ▼
┌──────────┐  ┌──────────────┐
│Save draft│  │Regenerate    │
│→ approval│  │(max 2 retries)│
│queue     │  └──────────────┘
└──────────┘
```

**Platform Adaptation Logic:**

```python
PLATFORM_CONFIGS = {
    "facebook": {
        "max_chars": 63206,
        "optimal_chars": 400,  # Best engagement
        "hashtag_count": 3-5,
        "tone": "conversational, engaging",
        "features": ["emoji", "hashtags", "CTA button"],
    },
    "zalo": {
        "max_chars": 2000,
        "optimal_chars": 200,
        "hashtag_count": 0,  # Zalo doesn't use hashtags
        "tone": "professional, respectful",
        "features": ["formal language", "clear CTA"],
    },
    "tiktok": {
        "max_chars": 2200,
        "optimal_chars": 150,
        "hashtag_count": 5-8,
        "tone": "trendy, casual, fun",
        "features": ["trending hashtags", "hook in first line", "emoji"],
    },
}

async def adapt_for_platform(content: str, platform: str) -> str:
    config = PLATFORM_CONFIGS[platform]
    
    response = await ai_core.complete(
        use_case="content_generation",
        system_prompt=f"""Adapt this content for {platform}.
Rules:
- Max {config['optimal_chars']} characters
- Tone: {config['tone']}
- Include: {config['features']}
- Keep the core message intact
- {f"Add {config['hashtag_count']} relevant hashtags" if config['hashtag_count'] else "No hashtags"}""",
        messages=[{"role": "user", "content": content}],
    )
    return response.content
```

### Luồng 2: Approval Workflow

```
Content draft created
│
▼
┌─────────────────────────────────┐
│ 1. DETERMINE APPROVAL FLOW      │
│    - Check tenant config        │
│    - Default: 1 approver        │
│    - Custom: multi-step         │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. NOTIFY APPROVERS             │
│    - Publish event for          │
│      Notification Service       │
│    - Show in Dashboard queue    │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 3. APPROVER ACTION              │
│    ┌─────────┬─────────┐       │
│    ▼         ▼         ▼       │
│  Approve   Reject   Edit       │
│    │         │         │       │
│    ▼         ▼         ▼       │
│  Next step  Back to   Save new │
│  or done    creator   version  │
└─────────────────────────────────┘
             │
             ▼ (approved)
┌─────────────────────────────────┐
│ 4. SCHEDULE OR PUBLISH          │
│    - If suggested_time → create │
│      schedule via Scheduler     │
│    - If immediate → publish now │
│    - Publish Kafka:             │
│      content.approved           │
└─────────────────────────────────┘
```

### Luồng 3: Content Versioning

```python
class ContentVersionManager:
    async def save_version(self, post_id: str, new_body: str, 
                           changed_by: str, reason: str):
        """
        Mỗi lần content thay đổi → lưu version mới.
        Cho phép rollback về bất kỳ version nào.
        """
        # Get current version number
        latest = await self.version_repo.get_latest(post_id)
        new_version = (latest.version_number if latest else 0) + 1
        
        # Save new version
        await self.version_repo.create({
            "post_id": post_id,
            "version_number": new_version,
            "body": new_body,
            "change_reason": reason,
            "changed_by": changed_by,
        })
        
        # Update post with new body
        await self.post_repo.update(post_id, {"body": new_body})

    async def rollback(self, post_id: str, target_version: int):
        """Rollback post content to a specific version."""
        version = await self.version_repo.get(post_id, target_version)
        if not version:
            raise VersionNotFound(post_id, target_version)
        
        await self.save_version(
            post_id, version.body,
            changed_by="system",
            reason=f"Rollback to version {target_version}"
        )
```

---

### Luồng 4: Xử lý MCP SSE JSON-RPC Requests

```
AI Core (MCP Host) ── X-Tenant-ID Header ──► Gateway (Kong) ──► Content Service (FastAPI)
                                                                     │
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │ 1. ROUTE TO SSE      │
                                                          │    /api/v1/content/  │
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
                                                          │    EventSource Stream│
                                                          └──────────┬───────────┘
                                                                     │
                                         ┌───────────────────────────┴───────────────────────────┐
                                         ▼ (POST /messages)                                      ▼ (POST /messages)
                                 Tool: generate_content                                  Tool: adapt_content
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
                            │ 4.2 GENERATION LOGIC   │                              │ 5.2 ADAPTATION LOGIC   │
                            │     Call Generator,    │                              │     Call Adapter,      │
                            │     RAG brand voice,   │                              │     check constraints, │
                            │     where tenant_id=   │                              │     where tenant_id=   │
                            │     T_ID               │                              │     T_ID               │
                            └──────────┬─────────────┘                              └──────────┬─────────────┘
                                       │                                                       │
                                       ▼                                                       ▼
                            ┌────────────────────────┐                              ┌────────────────────────┐
                            │ 4.3 RESPONSE           │                              │ 5.3 RESPONSE           │
                            │     Return JSON-RPC    │                              │     Return JSON-RPC    │
                            │     success payload    │                              │     success payload    │
                            └────────────────────────┘                              └────────────────────────────────┘
```

**Mẫu triển khai logic bảo mật đa thuê trên MCP FastAPI Endpoint (Content):**
```python
import asyncio
from fastapi import APIRouter, Request, Header, HTTPException
from sse_starlette.sse import EventSourceResponse
from mcp.server.fastapi import McpServerTransport

router = APIRouter(prefix="/api/v1/content/mcp")

# Giả định mcp_server đã được khai báo
@router.get("")
async def connect_mcp(request: Request, x_tenant_id: str = Header(...)):
    # Đăng ký sse transport kết nối
    transport = McpServerTransport(request)
    
    # BẢO MẬT: Ghi nhận context tenantId cho phiên kết nối này
    request.state.tenant_id = x_tenant_id
    
    async def event_generator():
        async for event in transport.connect():
            yield event
            
    return EventSourceResponse(event_generator())

@router.post("/messages")
async def handle_message(request: Request, x_tenant_id: str = Header(...)):
    # BẢO MẬT: Ràng buộc tenantId vào logic xử lý JSON-RPC
    extra_context = {"tenant_id": x_tenant_id}
    await mcp_server.handle_message(await request.json(), extra_context)
    return {"status": "accepted"}

# Định nghĩa Tool Handler
@mcp_server.tool("generate_content")
async def generate_content_handler(topic: str, platform: str = None, context: str = None, extra: dict = None):
    tenant_id = extra["tenant_id"]
    
    # Thực hiện gọi RAG và AI Core để tạo bài viết cô lập theo tenant_id
    post = await content_generator.generate(
        tenant_id=tenant_id,
        topic=topic,
        platform=platform,
        context=context
    )
    return {"content": [{"type": "text", "text": post.body}]}
```

---


## Zero-Trust Security & Dynamic RBAC Logic

Dịch vụ thực hiện cơ chế xác thực Zero-Trust và phân quyền động (Dynamic RBAC) dựa trên HMAC Signed Headers được truyền từ API Gateway:

### 1. Quy trình xác thực chữ ký (HMAC Verification Flow)
- Dịch vụ trích xuất các headers từ request:
  - `X-Tenant-ID`: ID của Tenant.
  - `X-User-ID`: ID của User.
  - `X-User-Permissions`: Chuỗi CSV chứa danh sách quyền của người dùng (ví dụ: `content:{resource}:{action}`).
  - `X-Permissions-Signature`: Chữ ký HMAC-SHA256 dạng hex.
- Dịch vụ tính toán signature dự kiến bằng khóa bí mật `GATEWAY_SIGNING_SECRET`:
  `expected_sig = HMAC_SHA256(GATEWAY_SIGNING_SECRET, X-Tenant-ID + ":" + X-User-ID + ":" + X-User-Permissions)`
- So sánh chữ ký nhận được với `expected_sig` sử dụng hàm so sánh an toàn chống Side-channel attack (ví dụ: so sánh độ dài không đổi/safe compare). Nếu không khớp, từ chối request với mã lỗi `403 Forbidden` và tăng counter metric lỗi bảo mật.

### 2. So khớp quyền hạn In-Memory O(1)
- Sau khi chữ ký được xác thực, dịch vụ chuyển chuỗi `X-User-Permissions` thành một cấu trúc Set để tìm kiếm với độ phức tạp $O(1)$.
- Đối với mỗi API endpoint yêu cầu quyền hạn `content:{resource}:{action}`, dịch vụ kiểm tra quyền trong Set:
  - Nếu Set chứa `*` (Super Admin), cho phép truy cập.
  - Nếu Set chứa `content:*` (Toàn quyền trên dịch vụ), cho phép truy cập.
  - Nếu Set chứa `content:{resource}:*` (Toàn quyền trên tài nguyên), cho phép truy cập.
  - Nếu Set chứa chính xác `content:{resource}:{action}`, cho phép truy cập.
  - Ngược lại, từ chối truy cập và trả về mã lỗi `403 Forbidden` kèm log lỗi chi tiết.

## Error Handling

| Scenario | Xử lý |
|----------|--------|
| Knowledge Base unreachable | Generate without brand context (lower quality), warn user |
| AI Core timeout | Return error, suggest retry |
| Quality check < 0.7 | Auto-regenerate (max 2 times), then save as draft with warning |
| All regenerations fail | Save best attempt as draft, flag for manual edit |
| Approval timeout (> 7 days) | Notify approver reminder |
| Platform publish fail | Handled by Scheduler (retry), Content just tracks status |
| MCP SSE Stream Failure | Hủy phiên làm việc và dọn dẹp bộ nhớ đệm tạo bài nháp của tenant |
| Unauthorized Cross-Tenant Access | Báo lỗi JSON-RPC Method Error và lưu vết cảnh báo bảo mật hệ thống |

