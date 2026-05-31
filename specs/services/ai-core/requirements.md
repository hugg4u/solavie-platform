# Requirements — AI Core Service

## Overview
Dịch vụ AI trung tâm — ReAct Agent Platform với MCP tool-calling. Bao gồm: LLM Gateway (model routing, token optimization, failover), Agent Orchestrator (LangGraph ReAct loop), MCP Tool Registry (quản lý tools từ các services), Tool Executor (thực thi tool calls).

## Tech Stack
- **Language:** Python 3.12
- **Framework:** FastAPI + gRPC + LangGraph
- **Database:** PostgreSQL (ai_core_db)
- **LLM Providers:** OpenAI, Anthropic (configurable)
- **Web Search:** Tavily API
- **URL Fetch:** Firecrawl / Jina Reader

## Requirements

### Requirement 1: Unified LLM API

**User Story:** Là developer, tôi muốn gọi AI qua 1 API duy nhất bất kể model nào.

#### Acceptance Criteria
1. THE AI_Core SHALL cung cấp unified API (REST + gRPC) cho tất cả LLM calls
2. THE AI_Core SHALL abstract provider-specific details (OpenAI, Anthropic, local)
3. THE AI_Core SHALL hỗ trợ streaming responses
4. THE AI_Core SHALL cung cấp gRPC interface cho hot-path (Chatbot)

### Requirement 2: Model Routing & Dynamic Configurations

**User Story:** Là system, tôi cần chọn model phù hợp theo use case để tối ưu cost/quality và có thể thay đổi cấu hình runtime từ trang quản trị (Admin Dashboard).

#### Acceptance Criteria
1. THE AI_Core SHALL route requests theo use case (chatbot → GPT-4o-mini, content → Claude Sonnet).
2. THE AI_Core SHALL hỗ trợ override model per-request qua tham số API.
3. THE AI_Core SHALL lưu trữ cấu hình định tuyến động (models, temperature, max_tokens) trong bảng cơ sở dữ liệu `llm_route_configs` per-tenant và use case.
4. THE AI_Core SHALL quản lý và bảo mật API Keys cùng Custom Endpoint URL (như vLLM/Ollama local) trong bảng `api_key_configs` sử dụng mã hóa đối xứng (AES-256).
5. THE AI_Core SHALL áp dụng caching (Redis TTL 5 phút) cho các cấu hình định tuyến động để tránh độ trễ truy vấn database trên hot-path.
6. THE AI_Core SHALL lắng nghe sự kiện cập nhật cấu hình từ Tenant Config Service qua kênh Redis Pub/Sub `config.updates` để tự động đồng bộ (hot-reload) cấu hình định tuyến và API keys mới về database cục bộ và làm trống (invalidate) cache hiện tại.

### Requirement 3: Token Optimization

**User Story:** Là business owner, tôi muốn chi phí AI thấp nhất có thể.

#### Acceptance Criteria
1. THE AI_Core SHALL áp dụng prompt caching (giảm 50% cost cho system prompts)
2. THE AI_Core SHALL compress conversation history (summarize old messages)
3. THE AI_Core SHALL extract only relevant sentences từ context documents
4. THE AI_Core SHALL control response length per use case
5. Token cost trung bình SHALL < $0.005 per message

### Requirement 4: Provider Failover

**User Story:** Là hệ thống, tôi cần AI luôn available dù provider nào down.

#### Acceptance Criteria
1. IF primary provider timeout (> 10s), THEN fallback sang secondary provider
2. THE AI_Core SHALL implement circuit breaker per provider
3. THE AI_Core SHALL log all failover events
4. Failover SHALL transparent cho caller (same response format)

### Requirement 5: Cost Tracking & Cost Simulator

**User Story:** Là admin, tôi muốn biết chi phí AI theo thời gian và có thể giả lập mô phỏng chi phí khi chuyển đổi giữa các API/Model để tối ưu hóa tài chính.

#### Acceptance Criteria
1. THE AI_Core SHALL log mọi LLM call vào bảng `llm_usage_logs`: model, tokens, latency, cost_usd, cache_hit, is_fallback.
2. THE AI_Core SHALL cung cấp API báo cáo sử dụng (`GET /api/v1/analytics/usage-summary`) gom nhóm theo tenant, use_case, model, provider.
3. THE AI_Core SHALL hỗ trợ bộ giả lập chi phí (`POST /api/v1/analytics/simulate-cost`) để ước tính chênh lệch tài chính và thay đổi latency dự kiến khi đổi cấu hình định tuyến dựa trên lịch sử token của 30 ngày gần nhất.
4. THE AI_Core SHALL alert khi cost vượt threshold cấu hình của tenant.
5. THE AI_Core SHALL expose metrics cho Prometheus.

### Requirement 6: Prompt Management

**User Story:** Là admin, tôi muốn quản lý và version prompt templates.

#### Acceptance Criteria
1. THE AI_Core SHALL lưu trữ prompt templates per-tenant
2. THE AI_Core SHALL hỗ trợ prompt versioning
3. THE AI_Core SHALL hỗ trợ A/B testing prompts

### Requirement 7: ReAct Agent Orchestration (MỚI)

**User Story:** Là hệ thống, tôi cần AI tự quyết định gọi tools nào để hoàn thành tác vụ.

#### Acceptance Criteria
1. THE AI_Core SHALL implement ReAct agent loop (Reason → Act → Observe → Repeat)
2. THE AI_Core SHALL hỗ trợ tối đa 5 iterations per request (safety limit)
3. THE AI_Core SHALL tự quyết định tool nào cần gọi dựa trên context
4. THE AI_Core SHALL handle tool execution timeout (10s per tool)
5. IF agent loop vượt max iterations, THEN trả về best-effort response

### Requirement 8: MCP Tool Registry (MỚI)

**User Story:** Là developer, tôi muốn đăng ký tools từ service của mình cho AI sử dụng.

#### Acceptance Criteria
1. THE AI_Core SHALL maintain registry của tất cả available tools
2. THE AI_Core SHALL phân loại tools: retrieval, action, content, processing
3. THE AI_Core SHALL restrict tools per use case (permission matrix)
4. THE AI_Core SHALL rate limit tool calls (per tool, per tenant)
5. THE AI_Core SHALL log tất cả tool calls cho audit

### Requirement 9: Web Search Integration (MỚI)

**User Story:** Là content creator, tôi muốn AI tìm thông tin mới nhất trên internet.

#### Acceptance Criteria
1. THE AI_Core SHALL hỗ trợ web search tool (Tavily/SerpAPI)
2. THE AI_Core SHALL hỗ trợ URL fetch tool (đọc nội dung trang web)
3. THE AI_Core SHALL hỗ trợ social trends tool (trending topics per platform)
4. Web search SHALL rate limited: max 3 per request, 50 per hour per tenant
5. THE AI_Core SHALL hiển thị sources cho user review

### Requirement 10: Agent Safety & Guardrails (MỚI)

**User Story:** Là admin, tôi muốn AI agent không thực hiện hành động nguy hiểm.

#### Acceptance Criteria
1. THE AI_Core SHALL require human confirmation cho destructive actions (publish, delete)
2. THE AI_Core SHALL prevent infinite loops (max iterations + anti-loop rules)
3. THE AI_Core SHALL enforce tenant isolation (agent chỉ access data của tenant mình)
4. THE AI_Core SHALL cap total tokens per session (10000 tokens max)
5. THE AI_Core SHALL log tất cả agent decisions cho audit trail
