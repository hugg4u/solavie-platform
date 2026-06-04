# Business Logic — AI Core Service (ReAct Agent + MCP Tools)

## Tổng quan vai trò (CẬP NHẬT)

AI Core không chỉ là LLM wrapper nữa — nó là **ReAct Agent Platform** với MCP tool-calling:
1. **LLM Gateway**: Model routing, token optimization, provider failover (giữ nguyên)
2. **Agent Orchestrator**: LangGraph ReAct loop — reason → act → observe → repeat
3. **MCP Tool Registry**: Đăng ký và quản lý tools từ các services khác
4. **Tool Executor**: Thực thi tool calls, handle timeout/retry

## Kiến trúc mới

```
┌─────────────────────────────────────────────────────────┐
│                    AI Core Service                        │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │         Agent Orchestrator (LangGraph)            │   │
│  │                                                    │   │
│  │  User Request → Reason → Select Tool → Execute    │   │
│  │       ↑              → Observe Result → Reason    │   │
│  │       └──────────── Loop until done ──────────┘   │   │
│  └──────────────────────────────────────────────────┘   │
│                          │                               │
│              ┌───────────┼───────────┐                   │
│              ▼           ▼           ▼                   │
│  ┌────────────────┐ ┌────────┐ ┌──────────────────┐    │
│  │ LLM Gateway    │ │  MCP   │ │  Tool Executor   │    │
│  │ (model routing,│ │Registry│ │  (call services) │    │
│  │  optimization) │ │        │ │                  │    │
│  └────────────────┘ └────────┘ └──────────────────┘    │
│                                                          │
└─────────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────┐  ┌─────────────────────────────┐
│  LLM Providers  │  │  Internal Services (via MCP) │
│  OpenAI/Claude  │  │  KB, CRM, Analytics, etc.   │
└─────────────────┘  └─────────────────────────────┘
```

## MCP Tool Registry — Tất cả tools trong hệ thống

### Category 1: Information Retrieval

```python
RETRIEVAL_TOOLS = [
    {
        "name": "knowledge_base_search",
        "description": "Search internal knowledge base for product info, FAQ, brand guidelines, policies",
        "parameters": {
            "query": "string - search query",
            "tenant_id": "string - tenant identifier",
            "top_k": "int - number of results (default 5)",
            "doc_type_filter": "string[] - optional filter by doc type"
        },
        "service": "knowledge-base",
        "endpoint": "POST /api/v1/search",
        "required_permission": "kb:search",
    },
    {
        "name": "web_search",
        "description": "Search the internet for current news, trends, competitor info, market data",
        "parameters": {
            "query": "string - search query",
            "max_results": "int - max results (default 5)",
            "time_range": "string - 'day', 'week', 'month', 'year'"
        },
        "service": "external",
        "provider": "tavily",  # or serpapi
        "required_permission": "kb:search",
    },
    {
        "name": "fetch_url",
        "description": "Fetch and extract content from a specific URL",
        "parameters": {
            "url": "string - URL to fetch",
            "extract_mode": "string - 'full', 'summary', 'main_content'"
        },
        "service": "external",
        "provider": "firecrawl",  # or jina reader
        "required_permission": "kb:search",
    },
    {
        "name": "analytics_query",
        "description": "Query marketing analytics: engagement metrics, top posts, trends",
        "parameters": {
            "tenant_id": "string",
            "metric_type": "string - 'engagement', 'reach', 'messages', 'posts'",
            "channel": "string - 'facebook', 'zalo', 'tiktok', 'all'",
            "date_range": "string - 'today', '7d', '30d', '90d'",
            "top_k": "int - for top performing content"
        },
        "service": "analytics",
        "endpoint": "GET /api/v1/metrics",
        "required_permission": "crm:read",
    },
    {
        "name": "contact_lookup",
        "description": "Look up customer information, interaction history, lead score",
        "parameters": {
            "tenant_id": "string",
            "contact_id": "string - optional",
            "external_id": "string - platform user ID, optional",
            "channel": "string - optional"
        },
        "service": "crm",
        "endpoint": "GET /api/v1/contacts/:id",
        "required_permission": "crm:read",
    },
    {
        "name": "get_social_trends",
        "description": "Get trending topics and hashtags on social media platforms",
        "parameters": {
            "platform": "string - 'facebook', 'tiktok', 'all'",
            "country": "string - 'VN', 'US', etc.",
            "category": "string - optional topic category"
        },
        "service": "external",
        "provider": "social_trends_api",
        "required_permission": "kb:search",
    },
]
```

### Category 2: Actions

```python
ACTION_TOOLS = [
    {
        "name": "send_message",
        "description": "Send a message to a customer on their platform",
        "parameters": {
            "conversation_id": "string",
            "content": "string - message text",
            "content_type": "string - 'text', 'image'"
        },
        "service": "messaging",
        "endpoint": "POST /api/v1/conversations/:id/messages",
        "requires_confirmation": False,  # Chatbot can auto-send
        "required_permission": "messaging:chat",
    },
    {
        "name": "handoff_to_agent",
        "description": "Transfer conversation to human agent immediately",
        "parameters": {
            "conversation_id": "string",
            "reason": "string - why handoff is needed",
            "priority": "string - 'normal', 'high', 'critical'"
        },
        "service": "messaging",
        "endpoint": "PUT /api/v1/conversations/:id/mode",
        "required_permission": "messaging:chat",
    },
    {
        "name": "tag_contact",
        "description": "Add tags to a customer contact for segmentation",
        "parameters": {
            "contact_id": "string",
            "tags": "string[] - tags to add"
        },
        "service": "crm",
        "endpoint": "POST /api/v1/contacts/:id/tags",
        "required_permission": "crm:update",
    },
    {
        "name": "create_schedule",
        "description": "Schedule a post for publishing at a specific time",
        "parameters": {
            "post_id": "string",
            "channel_ids": "string[]",
            "scheduled_at": "string - ISO8601 datetime",
            "timezone": "string - default 'Asia/Ho_Chi_Minh'"
        },
        "service": "scheduler",
        "endpoint": "POST /api/v1/schedules",
        "requires_confirmation": True,  # Need human approval
        "required_permission": "scheduler:publish",
    },
    {
        "name": "hide_comment",
        "description": "Hide a spam or inappropriate comment on a post",
        "parameters": {
            "comment_id": "string",
            "reason": "string"
        },
        "service": "comment-manager",
        "endpoint": "PUT /api/v1/comments/:id/hide",
        "required_permission": "comments:update",
    },
    {
        "name": "send_notification",
        "description": "Send notification to team member",
        "parameters": {
            "user_id": "string - recipient",
            "title": "string",
            "body": "string",
            "priority": "string - 'low', 'normal', 'high', 'critical'"
        },
        "service": "notification",
        "endpoint": "POST /api/v1/notifications/send",
        "required_permission": "messaging:chat",
    },
]
```

### Category 3: Content Creation

```python
CONTENT_TOOLS = [
    {
        "name": "generate_content",
        "description": "Generate social media content using AI with brand context",
        "parameters": {
            "topic": "string - content topic",
            "platform": "string - target platform",
            "audience": "string - target audience description",
            "tone": "string - optional tone override",
            "include_web_research": "bool - search web for current info"
        },
        "service": "content",
        "endpoint": "POST /api/v1/content/generate",
        "requires_confirmation": True,
        "required_permission": "kb:search",
    },
    {
        "name": "adapt_content",
        "description": "Adapt existing content for a different platform",
        "parameters": {
            "content": "string - original content",
            "target_platform": "string",
            "max_length": "int - optional"
        },
        "service": "content",
        "endpoint": "POST /api/v1/content/adapt",
        "required_permission": "kb:search",
    },
]
```

### Category 4: Data Processing

```python
PROCESSING_TOOLS = [
    {
        "name": "embed_text",
        "description": "Convert text to vector embedding",
        "parameters": {
            "texts": "string[] - texts to embed",
            "dimensions": "int - default 512"
        },
        "service": "internal",  # AI Core handles directly
        "required_permission": "kb:search",
    },
    {
        "name": "summarize",
        "description": "Summarize long text into concise version",
        "parameters": {
            "text": "string",
            "max_length": "int - max tokens for summary",
            "style": "string - 'bullet_points', 'paragraph', 'key_facts'"
        },
        "service": "internal",
        "required_permission": "kb:search",
    },
    {
        "name": "translate",
        "description": "Translate text between languages",
        "parameters": {
            "text": "string",
            "source_language": "string - 'auto' for detection",
            "target_language": "string"
        },
        "service": "internal",
        "required_permission": "kb:search",
    },
    {
        "name": "analyze_sentiment",
        "description": "Analyze sentiment of text",
        "parameters": {
            "text": "string"
        },
        "service": "internal",
        "returns": "{'sentiment': 'positive|neutral|negative|angry', 'confidence': 0.0-1.0}",
        "required_permission": "kb:search",
    },
    {
        "name": "calculate_lead_score",
        "description": "Calculate lead score based on customer behavior data",
        "parameters": {
            "contact_id": "string",
            "behavior_data": "object - message frequency, interests, etc."
        },
        "service": "internal",
        "required_permission": "crm:update",
    },
]
```

---

## ReAct Agent Loop (LangGraph)

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from typing import TypedDict, Annotated, Literal, List, Dict, Any
import operator

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    tenant_id: str
    conversation_id: str
    use_case: str  # "chatbot", "content", "analysis"
    tools_called: list  # Track which tools were used
    iteration_count: int  # Prevent infinite loops
    final_response: str
    confidence: float
    pii_map: Dict[str, str]  # PII placeholders to real values mapping dict (local)
    user_permissions: List[str]  # User Keycloak permissions from Redis cache

MAX_ITERATIONS = 5  # Safety: max tool calls per request

# === NODES ===

async def reason(state: AgentState) -> dict:
    """
    LLM decides: should I call a tool, or give final answer?
    
    ReAct pattern:
    - Thought: "I need to find product info to answer this question"
    - Action: knowledge_base_search(query="sản phẩm A giá")
    - Observation: "Sản phẩm A giá 500k, có 3 size..."
    - Thought: "I have enough info to answer"
    - Final Answer: "Sản phẩm A có giá 500.000đ ạ."
    """
    # Check iteration limit
    if state["iteration_count"] >= MAX_ITERATIONS:
        return {"final_response": "Xin lỗi, tôi không thể xử lý yêu cầu này.", "confidence": 0.0}
    
    # Get available tools for this use case
    tools = get_tools_for_use_case(state["use_case"], state["tenant_id"])
    
    # Call LLM with tool definitions
    response = await llm_gateway.complete(
        tenant_id=state["tenant_id"],
        use_case=state["use_case"],
        messages=state["messages"],
        tools=tools,  # MCP tool definitions
        tool_choice="auto",  # LLM decides
    )
    
    if response.tool_calls:
        # LLM wants to call a tool
        return {
            "messages": [response.message],  # includes tool_call
            "iteration_count": state["iteration_count"] + 1,
        }
    else:
        # LLM gives final answer
        return {
            "messages": [response.message],
            "final_response": response.content,
            "confidence": response.confidence,
        }

async def execute_tools(state: AgentState) -> dict:
    """
    Execute tool calls from LLM decision.
    Each tool call → HTTP/gRPC to the owning service.
    """
    last_message = state["messages"][-1]
    tool_results = []
    
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["arguments"]
        
        # 1. Permission check (RBAC module:action check from user_permissions)
        tool_def = get_tool_definition(tool_name)
        required_perm = tool_def.get("required_permission")
        if required_perm and required_perm not in state["user_permissions"]:
            tool_results.append({
                "tool_call_id": tool_call["id"],
                "result": f"Permission denied for tool '{tool_name}' (requires {required_perm})",
                "error": True,
            })
            continue
            
        # 2. Redis Rate limit check
        if not await check_rate_limit(state["tenant_id"], tool_name):
            tool_results.append({
                "tool_call_id": tool_call["id"],
                "result": f"Rate limit exceeded for tool '{tool_name}'",
                "error": True,
            })
            continue
            
        # 3. PII Re-identification Interceptor (Rule 3.1)
        # Restore real PII values to arguments before execution
        resolved_args = tool_args.copy()
        for k, v in resolved_args.items():
            if isinstance(v, str) and v in state["pii_map"]:
                resolved_args[k] = state["pii_map"][v]  # replace e.g. [PHONE_1] -> 0912345678
        
        # Determine dynamic timeout: hot-path interactive tools (<= 2s) vs background heavy tools (<= 10s)
        tool_timeout = 2.0 if tool_name in ["knowledge_base_search", "contact_lookup", "analyze_sentiment", "send_message", "tag_contact"] else 10.0
        
        # Execute with timeout and resolved arguments
        try:
            result = await asyncio.wait_for(
                tool_executor.execute(tool_name, resolved_args, state["tenant_id"]),
                timeout=tool_timeout
            )
            tool_results.append({
                "tool_call_id": tool_call["id"],
                "result": result,
            })
        except asyncio.TimeoutError:
            tool_results.append({
                "tool_call_id": tool_call["id"],
                "result": "Tool execution timed out",
                "error": True,
            })
        except Exception as e:
            tool_results.append({
                "tool_call_id": tool_call["id"],
                "result": f"Tool error: {str(e)}",
                "error": True,
            })
    
    # Add tool results as messages
    return {
        "messages": [{"role": "tool", "content": json.dumps(r)} for r in tool_results],
        "tools_called": [tc["name"] for tc in last_message.tool_calls],
    }

def should_continue(state: AgentState) -> Literal["execute_tools", "end"]:
    """Route: if LLM called tools → execute. If final answer → end."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "execute_tools"
    return "end"

# === BUILD GRAPH ===
workflow = StateGraph(AgentState)
workflow.add_node("reason", reason)
workflow.add_node("execute_tools", execute_tools)

workflow.set_entry_point("reason")
workflow.add_conditional_edges("reason", should_continue, {
    "execute_tools": "execute_tools",
    "end": END,
})
workflow.add_edge("execute_tools", "reason")  # Loop back after tool execution

agent = workflow.compile()
```

---

## Tool Executor — Gọi services qua MCP

```python
class ToolExecutor:
    """
    Thực thi tool calls bằng cách gọi đến service tương ứng.
    Mỗi tool map đến 1 service endpoint.
    """
    
    def __init__(self):
        self.tool_registry = load_tool_registry()
        self.http_client = httpx.AsyncClient(timeout=10.0)
        self.grpc_clients = {}
    
    async def execute(self, tool_name: str, args: dict, tenant_id: str) -> str:
        tool_def = self.tool_registry[tool_name]
        
        # Inject tenant_id into args (security: always use authenticated tenant)
        args["tenant_id"] = tenant_id
        
        if tool_def["service"] == "internal":
            # Internal tools (embed, summarize, translate) — handle locally
            return await self._execute_internal(tool_name, args)
        
        elif tool_def["service"] == "external":
            # External APIs (web search, social trends)
            return await self._execute_external(tool_name, args, tool_def["provider"])
        
        else:
            # Internal service call (KB, CRM, Analytics, etc.)
            return await self._execute_service_call(tool_name, args, tool_def)
    
    async def _execute_service_call(self, tool_name: str, args: dict, tool_def: dict) -> str:
        """Call internal microservice via REST."""
        service = tool_def["service"]
        endpoint = tool_def["endpoint"]
        
        # Build URL from service registry
        base_url = SERVICE_URLS[service]  # e.g., "http://knowledge-base:8004"
        url = f"{base_url}{endpoint}"
        
        # Replace path params
        for key, value in args.items():
            if f":{key}" in url:
                url = url.replace(f":{key}", str(value))
        
        # Make request
        method = "POST" if "POST" in tool_def.get("method", "POST") else "GET"
        if method == "POST":
            response = await self.http_client.post(url, json=args)
        else:
            response = await self.http_client.get(url, params=args)
        
        if response.status_code >= 400:
            return {
                "status": "error",
                "code": response.status_code,
                "error_type": self._classify_error(response.status_code),
                "message": response.text[:200],
                "retriable": response.status_code in (429, 503, 504),
                "tool": tool_name,
            }

        return {"status": "success", "data": response.text[:2000]}

    def _classify_error(self, code: int) -> str:
        """Map HTTP code → error type (theo shared/standards.md)."""
        return {
            400: "validation_error", 401: "unauthorized", 403: "forbidden",
            404: "not_found", 429: "rate_limited", 503: "service_unavailable",
            504: "timeout",
        }.get(code, "internal_error")
    
    async def _execute_external(self, tool_name: str, args: dict, provider: str) -> str:
        """Call external APIs (web search, etc.)."""
        if provider == "tavily":
            return await self._tavily_search(args["query"], args.get("max_results", 5))
        elif provider == "firecrawl":
            return await self._firecrawl_fetch(args["url"])
        elif provider == "social_trends_api":
            return await self._get_trends(args)
    
    async def _tavily_search(self, query: str, max_results: int) -> str:
        """Web search via Tavily API."""
        response = await self.http_client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": max_results,
                "include_answer": True,
            }
        )
        data = response.json()
        # Format results for LLM consumption
        results = []
        if data.get("answer"):
            results.append(f"Summary: {data['answer']}")
        for r in data.get("results", [])[:max_results]:
            results.append(f"- {r['title']}: {r['content'][:200]}")
        return "\n".join(results)
```

---

## Tool Permission System

```python
class ToolPermissionManager:
    """
    Quản lý phân quyền gọi công cụ.
    Đảm bảo kiểm tra chéo hai tầng:
    1. Usecase Mapping: use_case tương ứng có được phép gọi tool này không.
    2. RBAC check: Người dùng hiện tại có đủ mã quyền hạn `module:action` của tool này không (tra cứu từ cache Redis Keycloak).
    3. Tenant restrictions: Tenant có vô hiệu hóa tool này không.
    """
    
    PERMISSIONS = {
        "chatbot": [
            "knowledge_base_search",  # Tìm thông tin trả lời
            "contact_lookup",          # Xem info khách đang chat
            "send_message",            # Reply
            "handoff_to_agent",        # Chuyển cho người
            "tag_contact",             # Auto-tag based on conversation
            "analyze_sentiment",       # Detect mood
            "translate",               # Multi-language
            "summarize",               # Compress history
        ],
        "content_generation": [
            "knowledge_base_search",   # Brand voice, product info
            "web_search",              # Current trends, news
            "fetch_url",               # Research specific pages
            "analytics_query",         # Top performing posts
            "get_social_trends",       # Trending hashtags
            "generate_content",        # Self-call for adaptation
            "adapt_content",           # Platform adaptation
            "translate",               # Multi-language content
        ],
        "comment_management": [
            "knowledge_base_search",   # Find answers for questions
            "analyze_sentiment",       # Classify comment
            "hide_comment",            # Auto-hide spam
            "send_notification",       # Escalate
        ],
        "lead_scoring": [
            "contact_lookup",          # Get behavior data
            "analytics_query",         # Engagement metrics
            "calculate_lead_score",    # Score calculation
            "tag_contact",             # Update tags
            "send_notification",       # Alert sales
        ],
        "analytics_insights": [
            "analytics_query",         # Get all metrics
            "summarize",               # Summarize data
            "web_search",              # Industry benchmarks
        ],
    }
    
    async def check_permission(self, tenant_id: str, use_case: str, tool_name: str, user_permissions: List[str]) -> bool:
        # 1. Kiểm tra ánh xạ Use Case
        allowed_tools = self.PERMISSIONS.get(use_case, [])
        if tool_name not in allowed_tools:
            return False
            
        # 2. Kiểm tra quyền hạn người dùng (RBAC module:action)
        tool_def = get_tool_definition(tool_name)
        required_perm = tool_def.get("required_permission")
        if required_perm and required_perm not in user_permissions:
            return False
        
        # 3. Kiểm tra cấu hình tắt/mở công cụ của riêng Tenant
        tenant_config = await self.get_tenant_config(tenant_id)
        if tool_name in tenant_config.get("disabled_tools", []):
            return False
        
        return True
```

---

## Rate Limiting per Tool

```python
TOOL_RATE_LIMITS = {
    "web_search": {"per_request": 3, "per_hour": 50},      # Expensive
    "fetch_url": {"per_request": 2, "per_hour": 30},       # Expensive
    "knowledge_base_search": {"per_request": 5, "per_hour": 500},  # Cheap
    "send_message": {"per_request": 1, "per_hour": 100},   # Action
    "analytics_query": {"per_request": 3, "per_hour": 200},
    "generate_content": {"per_request": 1, "per_hour": 20}, # Very expensive
}
```

### Enforcement: Token Bucket trên Redis (theo shared/standards.md)

```python
class ToolRateLimiter:
    """
    Token bucket per (tenant + tool + window).
    Dùng Redis atomic INCR + TTL — distributed, không cần lock.
    """
    async def check_and_consume(self, tenant_id: str, tool_name: str) -> RateLimitResult:
        limit = TOOL_RATE_LIMITS.get(tool_name, {}).get("per_hour")
        if not limit:
            return RateLimitResult(allowed=True)

        # Sliding window theo giờ
        window = int(time.time() // 3600)
        key = f"ratelimit:{tenant_id}:{tool_name}:{window}"

        # Atomic increment
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 3600)  # TTL 1h

        if count > limit:
            ttl = await redis.ttl(key)
            return RateLimitResult(
                allowed=False,
                retry_after_seconds=ttl,
                limit=limit,
                used=count,
            )
        return RateLimitResult(allowed=True, used=count, limit=limit)
```

**Khi tool bị rate limited:** Tool Executor trả structured error cho agent:
```json
{"status": "error", "error_type": "rate_limited", "code": 429,
 "message": "Tool web_search limit reached (50/hour)", "retriable": true, "retry_after_ms": 1200000}
```
Agent nhận error → tự quyết định: skip tool đó và trả lời với info đã có, hoặc inform user.

---

## Luồng xử lý theo Use Case

### Use Case: Chatbot (ReAct Agent)

```
Customer: "Sản phẩm A có mấy màu và giá bao nhiêu?"

Agent Loop:
  Iteration 1:
    Thought: "Cần tìm thông tin sản phẩm A trong knowledge base"
    Action: knowledge_base_search(query="sản phẩm A màu giá", tenant_id="abc")
    Observation: "Sản phẩm A: giá 500k, có 3 màu: đỏ, xanh, trắng. Size S/M/L."
  
  Iteration 2:
    Thought: "Đã có đủ thông tin để trả lời"
    Final Answer: "Sản phẩm A có 3 màu (đỏ, xanh, trắng) và giá 500.000đ ạ."
    Confidence: 0.92

Total: 2 iterations, 1 tool call
```

### Use Case: Content Generation (ReAct Agent)

```
Marketer: "Viết bài Facebook về xu hướng skincare 2025, target gen Z"

Agent Loop:
  Iteration 1:
    Thought: "Cần brand voice và product info"
    Action: knowledge_base_search(query="brand voice skincare products", tenant_id="abc")
    Observation: "Brand voice: trẻ trung, gần gũi. Products: serum A, kem B..."
  
  Iteration 2:
    Thought: "Cần trends hiện tại về skincare"
    Action: web_search(query="skincare trends 2025 gen Z Vietnam")
    Observation: "Trending: glass skin, barrier repair, minimalist routine..."
  
  Iteration 3:
    Thought: "Cần biết bài nào perform tốt gần đây"
    Action: analytics_query(metric_type="engagement", channel="facebook", date_range="30d", top_k=5)
    Observation: "Top posts: video ngắn, before/after, user testimonials..."
  
  Iteration 4:
    Thought: "Đủ context, giờ viết bài"
    Final Answer: "🌟 Glass Skin không còn là giấc mơ!..."
    Confidence: 0.88

Total: 4 iterations, 3 tool calls
```

---

## Safety & Guardrails

```python
class AgentGuardrails:
    """
    Prevent AI agent from doing harmful things.
    """
    
    # Tools that need human confirmation before execution
    CONFIRMATION_REQUIRED = [
        "create_schedule",      # Don't auto-publish without approval
        "generate_content",     # Content needs review
    ]
    
    # Max iterations to prevent infinite loops
    MAX_ITERATIONS = 5
    
    # Max total tokens per agent session
    MAX_SESSION_TOKENS = 10000
    
    # Tools that can't be called in sequence (prevent loops)
    ANTI_LOOP_RULES = {
        "web_search": {"max_consecutive": 2},
        "knowledge_base_search": {"max_consecutive": 3},
    }
    
    async def validate_tool_call(self, tool_name: str, state: AgentState) -> ValidationResult:
        # Check confirmation requirement
        if tool_name in self.CONFIRMATION_REQUIRED:
            if state["use_case"] == "chatbot":
                return ValidationResult(allowed=False, reason="Requires human confirmation")
        
        # Check anti-loop
        recent_tools = state["tools_called"][-3:]
        rule = self.ANTI_LOOP_RULES.get(tool_name)
        if rule:
            consecutive = sum(1 for t in recent_tools if t == tool_name)
            if consecutive >= rule["max_consecutive"]:
                return ValidationResult(allowed=False, reason="Too many consecutive calls")
        
        return ValidationResult(allowed=True)
```

---

## Ảnh hưởng đến các service khác

Với AI Core trở thành ReAct Agent, các service khác cần:

| Service | Thay đổi |
|---------|----------|
| **Chatbot** | Đơn giản hóa — không cần LangGraph riêng nữa. Gọi AI Core agent với use_case="chatbot", AI Core tự handle RAG + response + handoff decision |
| **Content** | Đơn giản hóa — gọi AI Core agent với use_case="content_generation", AI Core tự research + generate |
| **Comment Manager** | Đơn giản hóa — gọi AI Core agent với use_case="comment_management" |
| **CRM** | Expose REST endpoints cho AI Core tool calls (đã có) |
| **Knowledge Base** | Expose REST endpoints cho AI Core tool calls (đã có) |
| **Analytics** | Expose REST endpoints cho AI Core tool calls (đã có) |
| **Messaging** | Vẫn giữ gRPC interface, nhưng AI Core gọi qua tool executor |

**Chatbot Service giờ trở thành thin wrapper:**
- Nhận message từ Messaging (gRPC)
- Forward cho AI Core agent (use_case="chatbot")
- Nhận response → return cho Messaging
- Vẫn giữ checkpoint management (conversation state)

---

## LLM Gateway (giữ nguyên từ trước)

LLM Gateway vẫn là sub-component bên trong AI Core:
- Model routing (GPT-4o-mini cho chatbot, Claude cho content)
- Token optimization (prompt caching, history compression)
- Provider failover (circuit breaker)
- Cost tracking

Agent Orchestrator gọi LLM Gateway khi cần "reason" (mỗi iteration).

---

## Performance Impact

| Metric | Trước (fixed pipeline) | Sau (ReAct agent) | Trade-off |
|--------|----------------------|-------------------|-----------|
| Chatbot simple Q&A | ~1.3s | ~1.5s (+1 LLM call for reasoning) | Slightly slower |
| Chatbot complex Q&A | ~1.3s (might fail) | ~2.5s (2-3 iterations, more accurate) | Slower but better |
| Content generation | ~4s | ~8s (3-4 tool calls) | Slower but much richer |
| Classification | ~300ms | ~300ms (1 iteration, no tools) | Same |

Trade-off: **Chậm hơn một chút nhưng thông minh hơn nhiều**. Agent tự biết khi nào cần thêm info, khi nào đủ.
