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

### Category 5: Solar & O&M Custom MCP Tools (MỚI)

Các công cụ được cung cấp động từ Custom MCP Servers tại `CRM Service` thông qua kết nối SSE:

```python
SOLAR_OM_MCP_TOOLS = [
    {
        "name": "solar_calc__calculate_solar_roi",
        "description": "Calculate solar panel system capacity, monthly generation kWh, financial savings, and ROI payback period based on location, roof area, and electricity bill.",
        "parameters": {
            "tenant_id": "string",
            "monthly_bill_vnd": "number - average monthly electricity bill in VND",
            "roof_area_sqm": "number - available roof area in square meters",
            "location_zone": "string - 'North', 'Central', 'South'",
            "roof_type": "string - 'concrete', 'tile', 'metal_sheet'",
        },
        "service": "crm",
        "required_permission": "crm:proposals:create",
    },
    {
        "name": "solar_calc__get_proposal_preview",
        "description": "Retrieve summary details and link of a previously generated solar proposal.",
        "parameters": {
            "tenant_id": "string",
            "proposal_id": "string"
        },
        "service": "crm",
        "required_permission": "crm:proposals:read",
    },
    {
        "name": "om_ticket__create_om_ticket",
        "description": "Create an Operations and Maintenance (O&M) ticket for device failure or solar system maintenance.",
        "parameters": {
            "tenant_id": "string",
            "contact_id": "string - customer contact ID",
            "title": "string - issue summary",
            "description": "string - detailed issue description",
            "priority": "string - 'low', 'medium', 'high', 'critical'"
        },
        "service": "crm",
        "required_permission": "crm:tickets:create",
    },
    {
        "name": "om_ticket__get_ticket_status",
        "description": "Retrieve the current status, assigned technician, and logs of an O&M ticket.",
        "parameters": {
            "tenant_id": "string",
            "ticket_id": "string"
        },
        "service": "crm",
        "required_permission": "crm:tickets:read",
    }
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
    total_tokens_used: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    cache_hit: bool
    cost_usd: float
    model_used: str
    provider: str
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
from gateway.mcp.manager import MCPClientManager

class ToolExecutor:
    """
    Thực thi tool calls động bằng cách định tuyến tới Custom MCP Servers nội bộ.
    """
    
    def __init__(self):
        self.mcp_manager = MCPClientManager()
        self.http_client = httpx.AsyncClient(timeout=10.0)
    
    async def execute(self, tool_name: str, args: dict, tenant_id: str, db_session) -> str:
        # BẢO MẬT: Inject tenant_id từ JWT xác thực vào arguments để đảm bảo cô lập dữ liệu
        args["tenant_id"] = tenant_id
        
        # Nếu là các tool local hoặc search hệ thống được cấu hình sẵn
        if tool_name in ["web_search", "fetch_url", "embed_text", "summarize", "translate", "analyze_sentiment"]:
            return await self._execute_local_system_tool(tool_name, args, tenant_id)
        
        # Định tuyến các cuộc gọi tool động tới Custom MCP Servers nội bộ (solar_calc, crm, om_ticket)
        # Tên tool định dạng: "{server_name}__{tool_name}" (ví dụ: "solar_calc__calculate_solar_roi")
        else:
            return await self.mcp_manager.execute_mcp_tool(
                tenant_id=tenant_id,
                full_tool_name=tool_name,
                arguments=args,
                db_session=db_session
            )
    
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

### 3. MCP Tool Mappings

Hệ thống sử dụng cấu hình ánh xạ `mcp_mapping` để tự động định tuyến các tool gọi từ chatbot tới các Custom MCP Server nội bộ tương ứng thông qua tool execution:
*   `"calculate_solar_roi"` trỏ sang `"solar_calc__calculate_solar_roi"`
*   `"get_proposal_preview"` trỏ sang `"solar_calc__get_proposal_preview"`
*   `"create_om_ticket"` trỏ sang `"om_ticket__create_om_ticket"`
*   `"get_ticket_status"` trỏ sang `"om_ticket__get_ticket_status"`
*   `"create_lead_deal"` trỏ sang `"crm__create_lead_deal"`
*   `"update_deal_stage"` trỏ sang `"crm__update_deal_stage"`

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
            
        # 2. Kiểm tra quyền hạn người dùng (RBAC in-memory O(1) matching với wildcard hỗ trợ)
        tool_def = get_tool_definition(tool_name)
        required_perm = tool_def.get("required_permission")
        if required_perm:
            perms_set = set(user_permissions)
            if not self._match_wildcard_permission(perms_set, required_perm):
                return False
        
        # 3. Kiểm tra cấu hình tắt/mở công cụ của riêng Tenant
        tenant_config = await self.get_tenant_config(tenant_id)
        if tool_name in tenant_config.get("disabled_tools", []):
            return False
        
        return True

    def _match_wildcard_permission(self, perms_set: set[str], required_perm: str) -> bool:
        if "*" in perms_set:
            return True
        if required_perm in perms_set:
            return True
        parts = required_perm.split(":")
        if len(parts) == 3:
            service, resource, action = parts
            if f"{service}:*" in perms_set:
                return True
            if f"{service}:{resource}:*" in perms_set:
                return True
        return False
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

### Use Case: Chatbot (ReAct Agent) with Semantic Cache

#### Luồng hoạt động:
1. Nhận tin nhắn từ khách hàng: *"Sản phẩm A giá bao nhiêu và có những màu nào?"*
2. Hệ thống gọi local FastEmbed `multilingual-e5-small` tạo vector embeddings 384 chiều của tin nhắn (< 20ms).
3. Thực hiện truy vấn Vector Search KNN trên Redis Stack DB 0.
4. **Trường hợp Cache Hit (similarity >= 0.92):**
   - Lập tức lấy câu trả lời lưu trong Redis cache và trả về trực tiếp cho khách hàng.
   - Bỏ qua hoàn toàn LangGraph Agent, gRPC, và các cuộc gọi LLM API.
   - Thời gian xử lý cực nhanh: < 10ms.
5. **Trường hợp Cache Miss (similarity < 0.92):**
   - Chuyển tiếp request vào đồ thị LangGraph Agent thực thi ReAct loop bình thường:
     - **Iteration 1:**
       - Thought: "Cần tìm thông tin sản phẩm A trong knowledge base"
       - Action: `knowledge_base_search(query="sản phẩm A giá màu sắc", tenant_id="abc")`
       - Observation: "Sản phẩm A: giá 500k, có 3 màu: đỏ, xanh, trắng."
     - **Iteration 2:**
       - Thought: "Đã có đủ thông tin để trả lời"
       - Final Answer: "Sản phẩm A có 3 màu (đỏ, xanh, trắng) và giá 500.000đ ạ."
       - Confidence: 0.94
   - Sau khi trả về câu trả lời cho user, hệ thống kích hoạt Background Task để lưu câu hỏi và câu trả lời kèm vector embeddings vào Redis Stack cache (TTL 24h).

Total: 2 iterations, 1 tool call (nếu cache miss) hoặc 0 iterations, 0 tool calls (nếu cache hit)

#### Thuật toán chi tiết Semantic Cache:
1. **Trích xuất câu hỏi**: Lấy nội dung câu hỏi (hoặc tin nhắn mới nhất) từ `messages[-1]`.
2. **Sinh Vector**: Gọi FastEmbed `multilingual-e5-small` sinh embedding 384 dimensions của câu hỏi tại máy chủ cục bộ.
3. **Tìm kiếm Vector KNN**: Thực hiện truy vấn trên Redis Stack DB 0 sử dụng `FT.SEARCH` với bộ lọc:
   `(@tenant_id:{tenant_id} @use_case:chatbot) => [KNN 1 @vector $query_vec AS score]`
4. **So khớp Ngưỡng (Threshold Check)**:
   - Tính toán `similarity = 1.0 - score` (với score là Cosine Distance trả về từ Redis).
   - Nếu `similarity >= 0.92` -> **Cache Hit**: Trả về `response` ngay lập tức, ghi nhận Prometheus metric và trả kết quả.
   - Nếu `similarity < 0.92` -> **Cache Miss**: Tiếp tục chạy ReAct Agent bình thường.
5. **Ghi Cache Bất đồng bộ (Async Write-Through)**:
   - Khi Agent sinh câu trả lời thành công từ LLM, kích hoạt FastAPI `BackgroundTasks` hoặc Celery task.
   - Tạo MD5 hash của câu hỏi để làm khóa phụ: `hash_val = md5(question)`.
   - Lưu Hash vào Redis với key `semantic_cache:{tenant_id}:{hash_val}` gồm các trường: `tenant_id`, `use_case`, `question`, `response`, và `vector` (nhị phân).
   - Thiết lập TTL 86400 giây (24 giờ).

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

---

## Zero-Trust Security & Dynamic RBAC Logic

AI Core thực hiện cơ chế xác thực Zero-Trust và phân quyền động (Dynamic RBAC) dựa trên HMAC Signed Headers được truyền từ API Gateway:

### 1. Quy trình xác thực chữ ký (HMAC Verification Flow)
- AI Core trích xuất các headers từ incoming HTTP/gRPC requests:
  - `X-Tenant-ID`: ID của Tenant.
  - `X-User-ID`: ID của User (hoặc Client ID).
  - `X-User-Permissions`: Chuỗi CSV chứa danh sách quyền của người dùng.
  - `X-Permissions-Signature`: Chữ ký HMAC-SHA256 dạng hex.
- Dịch vụ tính toán signature dự kiến bằng khóa bí mật `GATEWAY_SIGNING_SECRET`:
  `expected_sig = HMAC_SHA256(GATEWAY_SIGNING_SECRET, X-Tenant-ID + ":" + X-User-ID + ":" + X-User-Permissions)`
- So sánh chữ ký nhận được với `expected_sig` bằng hàm so sánh an toàn chống side-channel attacks (`hmac.compare_digest`). Nếu không khớp, từ chối request với mã lỗi `403 Forbidden` và tăng counter metric lỗi bảo mật.

### 2. So khớp quyền hạn In-Memory O(1)
- Khi thực thi các tool hoặc bảo vệ endpoints, AI Core chuyển chuỗi `X-User-Permissions` thành một cấu trúc Set để tìm kiếm với độ phức tạp $O(1)$.
- Đối với mỗi API endpoint hoặc tool yêu cầu quyền hạn `{service}:{resource}:{action}` (ví dụ: `ai-core:chats:create` hoặc `knowledge-base:documents:read`), dịch vụ so khớp quyền:
  - Nếu Set chứa `*` (Super Admin), cho phép truy cập.
  - Nếu Set chứa `{service}:*` (Toàn quyền trên dịch vụ), cho phép truy cập.
  - Nếu Set chứa `{service}:{resource}:*` (Toàn quyền trên tài nguyên), cho phép truy cập.
  - Nếu Set chứa chính xác `{service}:{resource}:{action}`, cho phép truy cập.
  - Ngược lại, từ chối truy cập và trả về mã lỗi `403 Forbidden` kèm log lỗi chi tiết.


## Vòng Đời Trạng Thái Của Dịch Vụ Đăng Ký (Service Node Lifespan) (MỚI)

Mỗi Node dịch vụ `ai-core` khi hoạt động sẽ chuyển đổi qua các trạng thái logic sau để đảm bảo tính nhất quán của bản đồ dịch vụ (Service Map):

1.  **STARTUP (Khởi tạo):**
    *   Tiến trình FastAPI khởi chạy.
    *   Tự động mở socket UDP ảo để dò tìm địa chỉ IP nội bộ của card mạng chính.
2.  **REGISTERING (Đăng ký):**
    *   Thực hiện kết nối tới Redis Cluster.
    *   Chạy lệnh `SADD registry:service:ai-core "{ip}:{port}"`.
    *   Nếu gặp lỗi kết nối Redis, tiến hành thử lại (Retry) tối đa 3 lần. Nếu vẫn lỗi, ghi log WARN và tiếp tục chạy dịch vụ ở chế độ cục bộ (không đăng ký).
3.  **ACTIVE / HEARTBEATING (Hoạt động):**
    *   Kích hoạt một luồng nền (heartbeat thread) chạy vô hạn.
    *   Mỗi 5 giây, thực hiện:
        *   `SETEX registry:service:ai-core:node:{ip}:{port} 15 "alive"`
        *   `SADD registry:service:ai-core "{ip}:{port}"` (Để phòng trường hợp key chính trong Set bị xóa nhầm hoặc Redis bị restart).
4.  **SHUTTING_DOWN (Dừng dịch vụ):**
    *   Nhận tín hiệu kết thúc (`SIGTERM`/`SIGINT`) từ Docker Engine / OS.
    *   Tạm dừng nhận requests mới.
    *   Thực hiện dọn dẹp (Cleanup):
        *   `SREM registry:service:ai-core "{ip}:{port}"`
        *   `DEL registry:service:ai-core:node:{ip}:{port}"`
    *   Đóng kết nối Redis và thoát tiến trình.




---

## Lifespan Registry Logic & Health API Flow (Tối ưu hóa)
*   **Startup Flow:**
    1. Khởi tạo ứng dụng và kết nối cơ sở dữ liệu.
    2. Gọi hàm lấy IP động -> Định danh node `{ip}:{port}`.
    3. Gửi lệnh `SADD` và `SETEX` lên Redis Registry. Nếu kết nối Redis bị lỗi, log Warning và tiếp tục chạy ứng dụng (Fail-safe), không được crash tiến trình chính.
    4. Bắt đầu Interval Heartbeat mỗi 5 giây.
*   **Shutdown Flow (Graceful):**
    1. Nhận tín hiệu `SIGTERM` hoặc `SIGINT`.
    2. Dừng Interval Heartbeat.
    3. Gửi lệnh `SREM` và `DEL` lên Redis Registry.
    4. Giải phóng các kết nối Database, Redis và exit.
