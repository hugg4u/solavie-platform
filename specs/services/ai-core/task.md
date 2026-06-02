# Task Checklist — AI-CORE Service

## Overview
This document tracks the implementation checklist for **AI-CORE Service** based on the system specifications.

### Technical Stack & Configuration
- **Language:** Python 3.12
- **Framework:** FastAPI + gRPC + LangGraph
- **Database:** PostgreSQL
- **LLM Providers:** OpenAI, Anthropic
- **Web Search:** Tavily API
- **URL Fetch:** Firecrawl / Jina Reader

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/ai-core/requirements.md)
- [Design](file:///specs/solavie-system/services/ai-core/design.md)
- [Logging](file:///specs/solavie-system/services/ai-core/logging.md)
- [Business Logic](file:///specs/solavie-system/services/ai-core/business-logic.md)

---

## Tasks Checklist

### Task 1: 1: Unified LLM API
> *User Story: Là developer, tôi muốn gọi AI qua 1 API duy nhất bất kể model nào.*

**Acceptance Criteria Implementation:**
- [ ] AC 1.1: THE AI_Core SHALL cung cấp unified API (REST + gRPC) cho tất cả LLM calls
- [ ] AC 1.2: THE AI_Core SHALL abstract provider-specific details (OpenAI, Anthropic, local)
- [ ] AC 1.3: THE AI_Core SHALL hỗ trợ streaming responses
- [ ] AC 1.4: THE AI_Core SHALL cung cấp gRPC interface cho hot-path (Chatbot)

### Task 2: Model Routing & Dynamic Configurations
> *User Story: Là system, tôi cần chọn model phù hợp theo use case để tối ưu cost/quality và có thể thay đổi cấu hình runtime từ trang quản trị (Admin Dashboard).*

**Acceptance Criteria Implementation:**
- [ ] AC 2.1: THE AI_Core SHALL route requests theo use case (chatbot → GPT-4o-mini, content → Claude Sonnet)
- [ ] AC 2.2: THE AI_Core SHALL hỗ trợ override model per-request qua tham số API
- [ ] AC 2.3: THE AI_Core SHALL lưu trữ cấu hình định tuyến động (models, temperature, max_tokens) trong bảng cơ sở dữ liệu `llm_route_configs` per-tenant và use case
- [ ] AC 2.4: THE AI_Core SHALL quản lý và bảo mật API Keys cùng Custom Endpoint URL trong bảng `api_key_configs` sử dụng mã hóa đối xứng (AES-256)
- [ ] AC 2.5: THE AI_Core SHALL áp dụng caching (Redis TTL 5 phút) cho các cấu hình định tuyến động để tránh độ trễ truy vấn database trên hot-path
- [ ] AC 2.6: THE AI_Core SHALL đăng ký (subscribe) kênh Redis Pub/Sub `config.updates` để nhận thông báo thay đổi cấu hình thời gian thực và thực hiện hot-reload

### Task 3: 3: Token Optimization
> *User Story: Là business owner, tôi muốn chi phí AI thấp nhất có thể.*

**Acceptance Criteria Implementation:**
- [ ] AC 3.1: THE AI_Core SHALL áp dụng prompt caching (giảm 50% cost cho system prompts)
- [ ] AC 3.2: THE AI_Core SHALL compress conversation history (summarize old messages)
- [ ] AC 3.3: THE AI_Core SHALL extract only relevant sentences từ context documents
- [ ] AC 3.4: THE AI_Core SHALL control response length per use case
- [ ] AC 3.5: Token cost trung bình SHALL < $0.005 per message

### Task 4: 4: Provider Failover
> *User Story: Là hệ thống, tôi cần AI luôn available dù provider nào down.*

**Acceptance Criteria Implementation:**
- [ ] AC 4.1: IF primary provider timeout (> 10s), THEN fallback sang secondary provider
- [ ] AC 4.2: THE AI_Core SHALL implement circuit breaker per provider
- [ ] AC 4.3: THE AI_Core SHALL log all failover events
- [ ] AC 4.4: Failover SHALL transparent cho caller (same response format)

### Task 5: Cost Tracking & Cost Simulator
> *User Story: Là admin, tôi muốn biết chi phí AI theo thời gian và có thể giả lập mô phỏng chi phí khi chuyển đổi giữa các API/Model để tối ưu hóa tài chính.*

**Acceptance Criteria Implementation:**
- [ ] AC 5.1: THE AI_Core SHALL log mọi LLM call vào bảng `llm_usage_logs`: model, tokens, latency, cost_usd, cache_hit, is_fallback
- [ ] AC 5.2: THE AI_Core SHALL cung cấp API báo cáo sử dụng (`GET /api/v1/analytics/usage-summary`) gom nhóm theo tenant, use_case, model, provider
- [ ] AC 5.3: THE AI_Core SHALL hỗ trợ bộ giả lập chi phí (`POST /api/v1/analytics/simulate-cost`) để ước tính chênh lệch tài chính và thay đổi latency dự kiến khi đổi cấu hình định tuyến dựa trên lịch sử token của 30 ngày gần nhất
- [ ] AC 5.4: THE AI_Core SHALL alert khi cost vượt threshold cấu hình của tenant
- [ ] AC 5.5: THE AI_Core SHALL expose metrics cho Prometheus

### Task 6: 6: Prompt Management
> *User Story: Là admin, tôi muốn quản lý và version prompt templates.*

**Acceptance Criteria Implementation:**
- [ ] AC 6.1: THE AI_Core SHALL lưu trữ prompt templates per-tenant
- [ ] AC 6.2: THE AI_Core SHALL hỗ trợ prompt versioning
- [ ] AC 6.3: THE AI_Core SHALL hỗ trợ A/B testing prompts

### Task 7: 7: ReAct Agent Orchestration (MỚI)
> *User Story: Là hệ thống, tôi cần AI tự quyết định gọi tools nào để hoàn thành tác vụ.*

**Acceptance Criteria Implementation:**
- [ ] AC 7.1: THE AI_Core SHALL implement ReAct agent loop (Reason → Act → Observe → Repeat)
- [ ] AC 7.2: THE AI_Core SHALL hỗ trợ tối đa 5 iterations per request (safety limit)
- [ ] AC 7.3: THE AI_Core SHALL tự quyết định tool nào cần gọi dựa trên context
- [ ] AC 7.4: THE AI_Core SHALL handle tool execution timeout (10s per tool)
- [ ] AC 7.5: IF agent loop vượt max iterations, THEN trả về best-effort response

### Task 8: 8: MCP Tool Registry (MỚI)
> *User Story: Là developer, tôi muốn đăng ký tools từ service của mình cho AI sử dụng.*

**Acceptance Criteria Implementation:**
- [ ] AC 8.1: THE AI_Core SHALL maintain registry của tất cả available tools
- [ ] AC 8.2: THE AI_Core SHALL phân loại tools: retrieval, action, content, processing
- [ ] AC 8.3: THE AI_Core SHALL restrict tools per use case (permission matrix)
- [ ] AC 8.4: THE AI_Core SHALL rate limit tool calls (per tool, per tenant)
- [ ] AC 8.5: THE AI_Core SHALL log tất cả tool calls cho audit

### Task 9: 9: Web Search Integration (MỚI)
> *User Story: Là content creator, tôi muốn AI tìm thông tin mới nhất trên internet.*

**Acceptance Criteria Implementation:**
- [ ] AC 9.1: THE AI_Core SHALL hỗ trợ web search tool (Tavily/SerpAPI)
- [ ] AC 9.2: THE AI_Core SHALL hỗ trợ URL fetch tool (đọc nội dung trang web)
- [ ] AC 9.3: THE AI_Core SHALL hỗ trợ social trends tool (trending topics per platform)
- [ ] AC 9.4: Web search SHALL rate limited: max 3 per request, 50 per hour per tenant
- [ ] AC 9.5: THE AI_Core SHALL hiển thị sources cho user review

### Task 10: 10: Agent Safety & Guardrails (MỚI)
> *User Story: Là admin, tôi muốn AI agent không thực hiện hành động nguy hiểm.*

**Acceptance Criteria Implementation:**
- [ ] AC 10.1: THE AI_Core SHALL require human confirmation cho destructive actions (publish, delete)
- [ ] AC 10.2: THE AI_Core SHALL prevent infinite loops (max iterations + anti-loop rules)
- [ ] AC 10.3: THE AI_Core SHALL enforce tenant isolation (agent chỉ access data của tenant mình)
- [ ] AC 10.4: THE AI_Core SHALL cap total tokens per session (10000 tokens max)
- [ ] AC 10.5: THE AI_Core SHALL log tất cả agent decisions cho audit trail

### Task 11: Implement Business Logic Rules
**Business Validations:**
- [ ] Tổng quan vai trò (CẬP NHẬT): **LLM Gateway**: Model routing, token optimization, provider failover (giữ nguyên)
- [ ] Tổng quan vai trò (CẬP NHẬT): **Agent Orchestrator**: LangGraph ReAct loop — reason → act → observe → repeat
- [ ] Tổng quan vai trò (CẬP NHẬT): **MCP Tool Registry**: Đăng ký và quản lý tools từ các services khác
- [ ] Tổng quan vai trò (CẬP NHẬT): **Tool Executor**: Thực thi tool calls, handle timeout/retry
- [ ] ReAct Agent Loop (LangGraph): Thought: "I need to find product info to answer this question"
- [ ] ReAct Agent Loop (LangGraph): Action: knowledge_base_search(query="sản phẩm A giá")
- [ ] ReAct Agent Loop (LangGraph): Observation: "Sản phẩm A giá 500k, có 3 size..."
- [ ] ReAct Agent Loop (LangGraph): Thought: "I have enough info to answer"
- [ ] ReAct Agent Loop (LangGraph): Final Answer: "Sản phẩm A có giá 500.000đ ạ."
- [ ] Ảnh hưởng đến các service khác: Nhận message từ Messaging (gRPC)
- [ ] Ảnh hưởng đến các service khác: Forward cho AI Core agent (use_case="chatbot")
- [ ] Ảnh hưởng đến các service khác: Nhận response → return cho Messaging
- [ ] Ảnh hưởng đến các service khác: Vẫn giữ checkpoint management (conversation state)
- [ ] LLM Gateway (giữ nguyên từ trước): Model routing (GPT-4o-mini cho chatbot, Claude cho content)
- [ ] LLM Gateway (giữ nguyên từ trước): Token optimization (prompt caching, history compression)
- [ ] LLM Gateway (giữ nguyên từ trước): Provider failover (circuit breaker)
- [ ] LLM Gateway (giữ nguyên từ trước): Cost tracking
- [ ] Luồng đồng bộ cấu hình (MỚI): Triển khai background listener thread/task lắng nghe kênh Redis Pub/Sub `config.updates`
- [ ] Luồng đồng bộ cấu hình (MỚI): Thực hiện gọi gRPC/REST sang Tenant Config Service lấy thông tin config mới khi nhận event
- [ ] Luồng đồng bộ cấu hình (MỚI): Ghi đè thông tin mới vào database `ai_core_db` (`api_key_configs` và `llm_route_configs`)
- [ ] Luồng đồng bộ cấu hình (MỚI): Giải mã API Keys bằng thuật toán đối xứng AES-256 trước khi gọi các LLM APIs ngoại vi
- [ ] Luồng đồng bộ cấu hình (MỚI): Thực hiện invalidate cache Redis của AI Core ngay sau khi reload config thành công
- [ ] API Endpoints (MỚI): Triển khai GET /api/v1/configs/routes trả về cấu hình định tuyến động của tenant
- [ ] API Endpoints (MỚI): Triển khai POST /api/v1/configs/routes cập nhật/tạo mới cấu hình định tuyến động
- [ ] API Endpoints (MỚI): Triển khai GET /api/v1/configs/keys trả về cấu hình khóa API hoạt động
- [ ] API Endpoints (MỚI): Triển khai POST /api/v1/configs/keys cập nhật/tạo khóa API mới (mã hóa AES-256)

### Task 12: Implement Structured Logging & Auditing
**Logging Requirements:**
- [ ] Sensitive Data Rules: NEVER log full prompt content ở level INFO (chỉ DEBUG)
- [ ] Sensitive Data Rules: NEVER log API keys
- [ ] Sensitive Data Rules: Log tenant_id nhưng KHÔNG log user PII
- [ ] Sensitive Data Rules: Truncate long content (max 200 chars in logs)

## Verification & Testing

### Automated Tests
- [ ] Write unit tests verifying core logic of each Requirement (including unified API, routing, token optimization, and failover).
- [ ] Write integration tests for all API endpoints (configs, analytics, prompt templates).
- [ ] Verify tenant isolation by querying data and sending API requests across different tenant IDs (Property 1).
- [ ] Verify circuit breaker triggers when LLM providers timeout/fail (Property 4).
- [ ] Verify local database consistency and compensation logic (Property 5).

### Manual Verification
- [ ] Deploy service to local Docker / Kubernetes cluster.
- [ ] Perform end-to-end tests using the Gateway (Kong) routing.
- [ ] Test the real-time configuration hot-reload via Redis Pub/Sub events and measure propagation latency (< 5 seconds).
- [ ] Test LLM cost simulation reporting with 30 days of mock token logs.

## Done When

- [ ] All Acceptance Criteria for Requirements are implemented and verified.
- [ ] Unit test coverage is >80%.
- [ ] Logs are formatted as structured JSON and trace context is propagated.
- [ ] Tenant isolation (RLS / metadata filtering) is strictly enforced.

### Task: Security Integration (MỚI)
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `ai-core`
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`
