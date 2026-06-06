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
- [Requirements](file:///d:/workspace/project/solavie-system/specs/services/ai-core/requirements.md)
- [Design](file:///d:/workspace/project/solavie-system/specs/services/ai-core/design.md)
- [Logging](file:///d:/workspace/project/solavie-system/specs/services/ai-core/logging.md)
- [Business Logic](file:///d:/workspace/project/solavie-system/specs/services/ai-core/business-logic.md)

---

## Tasks Checklist

### Task 1: 1: Unified LLM API
> *User Story: Là developer, tôi muốn gọi AI qua 1 API duy nhất bất kể model nào.*

**Acceptance Criteria Implementation:**
- [x] AC 1.1: THE AI_Core SHALL cung cấp unified API (REST + gRPC) cho tất cả LLM calls
- [x] AC 1.2: THE AI_Core SHALL abstract provider-specific details (OpenAI, Anthropic, local)
- [x] AC 1.3: THE AI_Core SHALL hỗ trợ streaming responses
- [x] AC 1.4: THE AI_Core SHALL cung cấp gRPC interface cho hot-path (Chatbot)

### Task 2: Model Routing & Dynamic Configurations
> *User Story: Là system, tôi cần chọn model phù hợp theo use case để tối ưu cost/quality và có thể thay đổi cấu hình runtime từ trang quản trị (Admin Dashboard).*

**Acceptance Criteria Implementation:**
- [x] AC 2.1: THE AI_Core SHALL route requests theo use case (chatbot → GPT-4o-mini, content → Claude Sonnet)
- [x] AC 2.2: THE AI_Core SHALL hỗ trợ override model per-request qua tham số API
- [x] AC 2.3: THE AI_Core SHALL lưu trữ cấu hình định tuyến động (models, temperature, max_tokens) trong bảng cơ sở dữ liệu `llm_route_configs` per-tenant và use case
- [x] AC 2.4: THE AI_Core SHALL quản lý và bảo mật API Keys cùng Custom Endpoint URL trong bảng `api_key_configs` sử dụng mã hóa đối xứng (AES-256 Fernet với Fernet key được sinh bằng cách băm SHA-256 của ENCRYPTION_SECRET_KEY)
- [x] AC 2.5: THE AI_Core SHALL áp dụng caching (Redis TTL 5 phút) cho các cấu hình định tuyến động để tránh độ trễ truy vấn database trên hot-path
- [x] AC 2.6: THE AI_Core SHALL đăng ký (subscribe) kênh Redis Pub/Sub `config.updates` để nhận thông báo thay đổi cấu hình thời gian thực và thực hiện hot-reload
- [x] AC 2.7: THE AI_Core SHALL chặn cuộc gọi LLM và trả về lỗi 400 rõ ràng khi không tìm thấy Custom API Key riêng của Tenant (BYOK) trong DB (Ngăn chặn hoàn toàn việc sử dụng khóa fallback dùng chung)

### Task 3: 3: Token Optimization
> *User Story: Là business owner, tôi muốn chi phí AI thấp nhất có thể.*

**Acceptance Criteria Implementation:**
- [x] AC 3.1: THE AI_Core SHALL áp dụng prompt caching (giảm 50% cost cho system prompts)
- [x] AC 3.2: THE AI_Core SHALL compress conversation history (summarize old messages)
  - [x] Baseline: Trích xuất 100 ký tự đầu tiên của tin nhắn cũ và nối lại
  - [x] Production-ready: Gọi LLM phụ chạy ngầm để sinh tóm tắt hội thoại cũ
  - [x] Dynamic Provider & Model Resolution: Phân giải provider từ Route Config của Tenant và tự động tra cứu mô hình rẻ nhất của provider đó từ LiteLLM registry, lưu RAM cache `_cheapest_models_cache` để tối ưu hóa hiệu năng, loại bỏ hoàn toàn việc fix cứng tên mô hình trong mã nguồn.
- [x] AC 3.3: THE AI_Core SHALL extract only relevant sentences từ context documents
- [x] AC 3.4: THE AI_Core SHALL control response length per use case
- [x] AC 3.5: Token cost trung bình SHALL < $0.005 per message

### Task 4: 4: Provider Failover
> *User Story: Là hệ thống, tôi cần AI luôn available dù provider nào down.*

**Acceptance Criteria Implementation:**
- [x] AC 4.1: IF primary provider timeout (> 10s), THEN fallback sang secondary provider
- [x] AC 4.2: THE AI_Core SHALL implement circuit breaker per provider
- [x] AC 4.3: THE AI_Core SHALL log all failover events
- [x] AC 4.4: Failover SHALL transparent cho caller (same response format)

### Task 5: Cost Tracking & Cost Simulator
> *User Story: Là admin, tôi muốn biết chi phí AI theo thời gian và có thể giả lập mô phỏng chi phí khi chuyển đổi giữa các API/Model để tối ưu hóa tài chính.*

**Acceptance Criteria Implementation:**
- [x] AC 5.1: THE AI_Core SHALL log mọi LLM call vào bảng `llm_usage_logs`: model, tokens, latency, cost_usd, cache_hit, is_fallback
- [x] AC 5.2: THE AI_Core SHALL cung cấp API báo cáo sử dụng (`GET /api/v1/analytics/usage-summary`) gom nhóm theo tenant, use_case, model, provider
- [x] AC 5.3: THE AI_Core SHALL hỗ trợ bộ giả lập chi phí (`POST /api/v1/analytics/simulate-cost`) để ước tính chênh lệch tài chính và thay đổi latency dự kiến khi đổi cấu hình định tuyến dựa trên lịch sử token của 30 ngày gần nhất
- [x] AC 5.4: THE AI_Core SHALL alert khi cost vượt threshold cấu hình của tenant: theo dõi chi phí tích lũy trong 30 ngày qua của tenant, so sánh với hạn mức chi phí (`cost_limit_usd` được định nghĩa trong cấu hình limits của tenant), và tự động kích hoạt tín hiệu cảnh báo (Cost Alert) khi sử dụng đạt 80% hạn mức
- [x] AC 5.5: THE AI_Core SHALL expose metrics cho Prometheus

### Task 6: 6: Prompt Management
> *User Story: Là admin, tôi muốn quản lý và version prompt templates.*

**Acceptance Criteria Implementation:**
- [x] AC 6.1: THE AI_Core SHALL lưu trữ prompt templates per-tenant
- [x] AC 6.2: THE AI_Core SHALL hỗ trợ prompt versioning
- [x] AC 6.3: THE AI_Core SHALL hỗ trợ A/B testing prompts

### Task 7: 7: ReAct Agent Orchestration (MỚI)
> *User Story: Là hệ thống, tôi cần AI tự quyết định gọi tools nào để hoàn thành tác vụ.*

**Acceptance Criteria Implementation:**
- [x] AC 7.1: THE AI_Core SHALL implement ReAct agent loop (Reason → Act → Observe → Repeat)
- [x] AC 7.2: THE AI_Core SHALL hỗ trợ tối đa 5 iterations per request (safety limit)
- [x] AC 7.3: THE AI_Core SHALL tự quyết định tool nào cần gọi dựa trên context
- [x] AC 7.4: THE AI_Core SHALL handle tool execution timeout (10s per tool) và tích hợp cơ chế Circuit Breaker (pybreaker) để báo lỗi nhanh (1ms) khi tool endpoint sập liên tục.
- [x] AC 7.5: IF agent loop vượt max iterations, THEN trả về best-effort response

### Task 8: 8: MCP Tool Registry (MỚI)
> *User Story: Là developer, tôi muốn đăng ký tools từ service của mình cho AI sử dụng.*

**Acceptance Criteria Implementation:**
- [x] AC 8.1: THE AI_Core SHALL maintain registry của tất cả available tools
- [x] AC 8.2: THE AI_Core SHALL phân loại tools: retrieval, action, content, processing
- [x] AC 8.3: THE AI_Core SHALL restrict tools per use case (Use Case mapping matrix)
- [x] AC 8.3b: THE AI_Core SHALL thực thi phân quyền người dùng động theo mã quyền hạn dạng `module:action` so khớp với cache Redis Keycloak `{tenant_id}:permissions:{user_role}` (độ trễ < 50ms)
- [x] AC 8.4: THE AI_Core SHALL rate limit tool calls (per tool, per tenant)
- [x] AC 8.5: THE AI_Core SHALL log tất cả tool calls cho audit

### Task 9: 9: Web Search Integration (MỚI)
> *User Story: Là content creator, tôi muốn AI tìm thông tin mới nhất trên internet.*

**Acceptance Criteria Implementation:**
- [x] AC 9.1: THE AI_Core SHALL hỗ trợ web search tool (Tavily/SerpAPI)
- [x] AC 9.2: THE AI_Core SHALL hỗ trợ URL fetch tool (đọc nội dung trang web) tích hợp Jina Reader API (`https://r.jina.ai/`) để chuyển đổi nội dung thành Markdown tối ưu hóa tokens
- [x] AC 9.3: THE AI_Core SHALL hỗ trợ social trends tool (trending topics per platform)
- [x] AC 9.4: Web search SHALL rate limited: max 3 per request, 50 per hour per tenant
- [x] AC 9.5: THE AI_Core SHALL hiển thị sources cho user review

### Task 10: 10: Agent Safety & Guardrails (MỚI)
> *User Story: Là admin, tôi muốn AI agent không thực hiện hành động nguy hiểm.*

**Acceptance Criteria Implementation:**
- [x] AC 10.1: THE AI_Core SHALL require human confirmation cho destructive actions (publish, delete)
- [x] AC 10.2: THE AI_Core SHALL prevent infinite loops (max iterations + anti-loop rules: cấm gọi liên tiếp quá 2 lần web_search hoặc 3 lần knowledge_base_search)
- [x] AC 10.3: THE AI_Core SHALL enforce tenant isolation (agent chỉ access data của tenant mình)
- [x] AC 10.4: THE AI_Core SHALL cap total tokens per session (10000 tokens max)
- [x] AC 10.5: THE AI_Core SHALL log tất cả agent decisions cho audit trail
- [x] AC 10.6: THE AI_Core SHALL hỗ trợ chặn chủ đề (Topic Guardrails) qua System Prompt và so khớp RAG confidence
- [x] AC 10.7: THE AI_Core SHALL tích hợp Custom Regex Middleware PII Masking đầu vào/đầu ra với độ trễ < 10ms
- [x] AC 10.8: THE AI_Core SHALL tận dụng Safety Filters ở tầng API của nhà cung cấp mô hình
- [x] AC 10.9: THE AI_Core SHALL tích hợp bộ đánh giá kiểm chứng nguồn tin (NLI Grounding Validator) ở đầu ra bằng mô hình NLI
- [x] AC 10.10: THE AI_Core SHALL tích hợp bộ kiểm duyệt nội dung đầu ra (Output Content Moderation - Profanity, Toxicity, Prompt Leakage prevention) tại tầng ContentGuardrail

### Task 11: Implement Business Logic Rules
**Business Validations:**
- [x] Tổng quan vai trò (CẬP NHẬT): **LLM Gateway**: Model routing, token optimization, provider failover (giữ nguyên)
- [x] Tổng quan vai trò (CẬP NHẬT): **Agent Orchestrator**: LangGraph ReAct loop — reason → act → observe → repeat
- [x] Tổng quan vai trò (CẬP NHẬT): **MCP Tool Registry**: Đăng ký và quản lý tools từ các services khác
- [x] Tổng quan vai trò (CẬP NHẬT): **Tool Executor**: Thực thi tool calls, handle timeout/retry
- [x] ReAct Agent Loop (LangGraph): Thought: "I need to find product info to answer this question"
- [x] ReAct Agent Loop (LangGraph): Action: knowledge_base_search(query="sản phẩm A giá")
- [x] ReAct Agent Loop (LangGraph): Observation: "Sản phẩm A giá 500k, có 3 size..."
- [x] ReAct Agent Loop (LangGraph): Thought: "I have enough info to answer"
- [x] ReAct Agent Loop (LangGraph): Final Answer: "Sản phẩm A có giá 500.000đ ạ."
- [x] Ảnh hưởng đến các service khác: Nhận message từ Messaging (gRPC)
- [x] Ảnh hưởng đến các service khác: Forward cho AI Core agent (use_case="chatbot")
- [x] Ảnh hưởng đến các service khác: Nhận response → return cho Messaging
- [x] Ảnh hưởng đến các service khác: Vẫn giữ checkpoint management (conversation state)
- [x] LLM Gateway (giữ nguyên từ trước): Model routing (GPT-4o-mini cho chatbot, Claude cho content)
- [x] LLM Gateway (giữ nguyên từ trước): Token optimization (prompt caching, history compression)
- [x] LLM Gateway (giữ nguyên từ trước): Provider failover (circuit breaker)
- [x] LLM Gateway (giữ nguyên từ trước): Cost tracking
- [x] Luồng đồng bộ cấu hình (MỚI): Triển khai background listener thread/task lắng nghe kênh Redis Pub/Sub `config.updates`
- [x] Luồng đồng bộ cấu hình (MỚI): Thực hiện gọi gRPC/REST sang Tenant Config Service lấy thông tin config mới khi nhận event
- [x] Luồng đồng bộ cấu hình (MỚI): Ghi đè thông tin mới vào database `ai_core_db` (`api_key_configs` và `llm_route_configs`)
- [x] Luồng đồng bộ cấu hình (MỚI): Giải mã API Keys bằng thuật toán đối xứng AES-256 trước khi gọi các LLM APIs ngoại vi
- [x] Luồng đồng bộ cấu hình (MỚI): Thực hiện invalidate cache Redis của AI Core ngay sau khi reload config thành công
- [x] Phân giải khóa API: Bắt buộc sử dụng BYOK (khoá riêng của Tenant), nếu thiếu khóa phải lập tức chặn cuộc gọi và báo lỗi HTTP 400 (không sử dụng System Config DB fallback hay biến môi trường)
- [x] Kiểm tra phân hạng gói cước động từ Redis (`tenant:{tenant_id}:tier`) để áp dụng hạn mức Rate Limiting cho các tool
- [x] API Endpoints (MỚI): Triển khai GET /api/v1/configs/routes trả về cấu hình định tuyến động của tenant
- [x] API Endpoints (MỚI): Triển khai POST /api/v1/configs/routes cập nhật/tạo mới cấu hình định tuyến động
- [x] API Endpoints (MỚI): Triển khai GET /api/v1/configs/keys trả về cấu hình khóa API hoạt động
- [x] API Endpoints (MỚI): Triển khai POST /api/v1/configs/keys cập nhật/tạo khóa API mới (mã hóa AES-256)

### Task 12: Implement Structured Logging & Auditing
**Logging Requirements:**
- [x] Sensitive Data Rules: NEVER log full prompt content ở level INFO (chỉ DEBUG)
- [x] Sensitive Data Rules: NEVER log API keys
- [x] Sensitive Data Rules: Log tenant_id nhưng KHÔNG log user PII
- [x] Sensitive Data Rules: Truncate long content (max 200 chars in logs)
- [x] Guardrails Logging: Ghi nhận danh sách PII placeholders (`pii_masked_keys`), điểm số NLI validation (`nli_grounding_score`), trạng thái kiểm chứng NLI (`nli_status`), và số vòng lặp Agent (`agent_iterations`) trong JSON context logs.
- [x] Guardrails Tracing: Định nghĩa và propagate trace context cho các Middleware và Agent Loop spans (de-id, nli, re-id).
- [x] Guardrails Metrics: Triển khai các Prometheus metrics custom (`ai_core_pii_tokens_total`, `ai_core_nli_grounding_score`, `ai_core_nli_violations_total`, `ai_core_rag_similarity_score`, `ai_core_rate_limit_violations_total`) và tích hợp vào `/metrics` endpoint.

## Verification & Testing

### Automated Tests
- [x] Write unit tests verifying core logic of each Requirement (including unified API, routing, token optimization, and failover).
- [x] Write integration tests for all API endpoints (configs, analytics, prompt templates).
- [x] Verify tenant isolation by querying data and sending API requests across different tenant IDs (Property 1).
- [x] Verify circuit breaker triggers when LLM providers timeout/fail (Property 4).
- [x] Verify local database consistency and compensation logic (Property 5).

### Manual Verification
- [x] Deploy service to local Docker / Kubernetes cluster.
- [x] Perform end-to-end tests using the Gateway (Kong) routing.
- [x] Test the real-time configuration hot-reload via Redis Pub/Sub events and measure propagation latency (< 5 seconds).
- [x] Test LLM cost simulation reporting with 30 days of mock token logs.

## Done When

- [x] All Acceptance Criteria for Requirements are implemented and verified.
- [x] Unit test coverage is >80%.
- [x] Logs are formatted as structured JSON and trace context is propagated.
- [x] Tenant isolation (RLS / metadata filtering) is strictly enforced.

### Task: Security Integration & Dynamic RBAC (MỚI)
- [x] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `ai-core`.
- [x] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`.
- [x] Triển khai HMAC Signature Verification Guard/Interceptor sử dụng `GATEWAY_SIGNING_SECRET` để xác thực request từ Gateway.
- [x] Triển khai cơ chế so khớp quyền hạn Dynamic RBAC in-memory O(1) hỗ trợ wildcard (`*`, `ai-core:*`, `ai-core:{resource}:*`).
- [x] Thực hiện tích hợp Endpoint `/api/v1/permissions/manifest` trả về danh sách tài nguyên và quyền hạn của service.
- [x] Bổ sung các test cases kiểm tra Signature Verification và Access Control Denied.

---

## Future Phase 2 Task Checklist

### Task 13: Semantic Caching Implementation
- [x] AC 11.1: Tích hợp Redis Stack và cài đặt module RediSearch vector index trong code
- [x] AC 11.2: Triển khai kiểm tra tương đồng ngữ nghĩa câu hỏi trước khi gọi LLM/KB Search

### Task 14: Structured Outputs Integration
- [x] AC 12.1: Định nghĩa JSON schema và tích hợp `response_format` trong LiteLLM completion calls

### Task 15: Agent Tracing & Monitoring
- [x] AC 13.1: Cấu hình OpenTelemetry exporter kết nối tới LangSmith/Arize Collector

### Task 16: 12 LLM Providers Custom Optimization (MỚI)
> *User Story: Là business owner và system admin, tôi muốn AI-core được cấu hình tối ưu chi phí, độ trễ và tính năng đặc thù cho 12 LLM providers (Tương ứng với Requirement 14).*

**Acceptance Criteria Implementation:**
- [x] AC 16.1: Tích hợp cấu trúc Prompt Caching (OpenAI & Anthropic cache control breakpoints - AC 14.1)
  - OpenAI: `apply_openai_caching()` — system prompt reorder + `X-Cache-Hint` header (auto-cache ≥ 1024 tokens)
  - Anthropic: `apply_anthropic_caching()` — `cache_control: {type: ephemeral}` tại System Prompt & RAG Context
- [x] AC 16.2: Triển khai Google Safety Settings và Context Caching lớn cho Gemini (AC 14.2)
  - Safety Settings: 4 harm categories BLOCK_MEDIUM_AND_ABOVE
  - Context Caching: `build_gemini_context_cache_params()` inject `cachedContent.ttl=300s` cho contexts > 32k tokens
- [x] AC 16.3: Xử lý DeepSeek-R1 suy nghĩ (thinking block parsing) và fast failover circuit breaker (5s timeout - AC 14.3)
  - `timeout=5.0` cho DeepSeek provider
  - `<think>...</think>` block extraction → `reasoning_content` field
- [x] AC 16.4: Đồng bộ hóa local vLLM/Ollama endpoints qua database configurations (AC 14.4)
  - `api_base` từ `api_key_configs` được inject vào LiteLLM call (provider `local`)
  - Circuit breaker `PROVIDER_BREAKERS["local"]` đã được đăng ký
- [x] AC 16.5: Parse và cấu trúc citations metadata từ Cohere và Perplexity APIs (AC 14.5)
  - Perplexity: `response.citations` direct extraction
  - Cohere: `response.citations` + `response.meta.citations` fallback với chuẩn hoá `{start, end, text, source}`
- [x] AC 16.6: Tự động dọn dẹp format parameters null cho Mistral và cấu hình EU nodes routing (AC 14.6)
  - Null cleanup: `sanitize_mistral_tools()` recursive deep copy remove None values
  - EU routing: `apply_mistral_eu_routing()` detect `eu.`/`europe` trong `api_base` hoặc default Mistral La Plateforme endpoint


### Task 17: Dynamic Default Model Resolution & Deprecation Defense (MỚI)
> *User Story: Là system admin, tôi muốn các mô hình mặc định tự động thích ứng với khóa API hoạt động của Tenant và tự động đổi sang mô hình rẻ nhất còn sống khi mô hình hiện tại bị khai tử ở upstream (Tương ứng với Requirement 2 AC 8 & 9).*

**Acceptance Criteria Implementation:**
- [x] AC 17.1: Thiết lập cơ sở dữ liệu bảng `system_default_route_configs` trong DB AI-CORE
- [x] AC 17.2: Triển khai background job `sync_dynamic_cost_registry` kéo bảng giá mới nhất từ GitHub LiteLLM, lưu local cache và nạp vào LiteLLM registry
- [x] AC 17.3: Triển khai đồng bộ bảng default `sync_system_default_configs`: tính toán cheapest model của từng Provider cho tất cả các usecase và lưu/cập nhật (UPSERT) vào DB
- [x] AC 17.4: Cấu hình startup sync trong `main.py` tự động chạy đồng bộ bảng default khi server khởi động
- [x] AC 17.5: Định tuyến Gateway thông minh: Khi Tenant chưa có Route Config cụ thể, tự động chọn đúng default model của active Provider từ `system_default_route_configs` DB
- [x] AC 17.6: Triển khai hàm `resolve_active_default_model` để tự động phát hiện model bị khai tử và tự động chuyển hướng sang cheapest model còn sống của Provider đó
- [x] AC 17.7: Viết unit tests bổ sung và đảm bảo toàn bộ tests PASS thành công


### Task 18: Auto-Configuration on First Key & Dynamic Models Endpoint (MỚI)
> *User Story: Là system admin, tôi muốn hệ thống tự động thiết lập các định tuyến LLM ban đầu khi Tenant cấu hình API Key đầu tiên, và cung cấp một danh mục mô hình khả dụng động thay vì fix cứng.*

**Acceptance Criteria Implementation:**
- [x] AC 18.1: Triển khai hàm helper `auto_create_tenant_routes_from_defaults` nhân bản cấu hình định tuyến mặc định của Provider tương ứng khi thêm khóa API đầu tiên
- [x] AC 18.2: Tích hợp logic tự động tạo định tuyến vào REST API `create_or_update_key`
- [x] AC 18.3: Tích hợp logic tự động tạo định tuyến vào sync listener `fetch_and_sync_config`
- [x] AC 18.4: Nâng cấp REST API `/models` động dựa trên LiteLLM model_cost registry
- [x] AC 18.5: Cập nhật cơ chế xác thực tệp registry LiteLLM sang kiểm tra schema động thay vì kiểm tra model cứng gpt-4o-mini
- [x] AC 18.6: Bổ sung unit tests kiểm thử toàn diện logic mới và chạy pass 100% test suite

### Task 19: Secure Multi-tenant MCP Host Gateway (MỚI)
- [x] Triển khai lớp `MCPClientManager` (`gateway/mcp/manager.py`) hỗ trợ Singleton connection pool SSE.
- [x] Triển khai whitelisting động qua bảng `tenant_mcp_servers` để ngăn chặn SSRF.
- [x] Bắt buộc tự động tiêm/ghi đè tham số `tenant_id` từ JWT token xác thực vào tham số (arguments) của tool trước khi gửi sang MCP Server.
- [x] Cập nhật `ToolExecutor.execute` định tuyến các remote tools (có tiền tố `{server_name}__`) qua `MCPClientManager.execute_mcp_tool`.
- [x] Viết unit tests kiểm thử cơ chế whitelisting và tiêm `tenant_id` tại AI Core.

