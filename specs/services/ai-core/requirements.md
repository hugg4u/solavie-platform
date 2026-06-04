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
4. THE AI_Core SHALL quản lý và bảo mật API Keys cùng Custom Endpoint URL (như vLLM/Ollama local) trong bảng `api_key_configs` sử dụng mã hóa đối xứng (AES-256). Thuật toán mã hóa sử dụng `cryptography.fernet` với Fernet Key được sinh bằng cách băm SHA-256 chuỗi cấu hình `ENCRYPTION_SECRET_KEY` nhằm đảm bảo tính chịu lỗi cao.
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
4. THE AI_Core SHALL handle tool execution timeout và thực thi cơ chế Circuit Breaker (sử dụng pybreaker) cho từng endpoint của tool. Cấu hình timeout được phân cấp động: tối đa 2.0s đối với các công cụ tương tác trực tiếp/hot-path (như `knowledge_base_search`, `contact_lookup`, `analyze_sentiment`) và tối đa 10s đối với các công cụ nền chậm (như `web_search`, `generate_content`). Nếu tool lỗi liên tiếp 5 lần trong 30 giây, Circuit Breaker chuyển sang trạng thái Open để tự động báo lỗi tức thì (1ms) nhằm tránh treo Agent.
5. IF agent loop vượt max iterations, THEN trả về best-effort response

### Requirement 8: MCP Tool Registry (MỚI)

**User Story:** Là developer, tôi muốn đăng ký tools từ service của mình cho AI sử dụng.

#### Acceptance Criteria
1. THE AI_Core SHALL maintain registry của tất cả available tools.
2. THE AI_Core SHALL phân loại tools thành các nhóm: retrieval, action, content, và processing.
3. THE AI_Core SHALL restrict tools per use case (permission matrix) và thực hiện phân quyền người dùng thông qua mã quyền hạn dạng `module:action` (ví dụ: `crm:read`, `kb:search`, `messaging:chat`). Bộ thực thi công cụ bắt buộc phải đối chiếu mã này với danh sách quyền hạn của người dùng được tải từ cache Redis Keycloak `{tenant_id}:permissions:{user_role}` với độ trễ tối đa cho phép là dưới 50ms trước khi chạy.
4. THE AI_Core SHALL rate limit tool calls (per tool, per tenant) sử dụng cơ chế Redis Token Bucket.
5. THE AI_Core SHALL log tất cả tool calls cho audit.

### Requirement 9: Web Search Integration (MỚI)

**User Story:** Là content creator, tôi muốn AI tìm thông tin mới nhất trên internet.

#### Acceptance Criteria
1. THE AI_Core SHALL hỗ trợ web search tool (Tavily/SerpAPI).
2. THE AI_Core SHALL hỗ trợ URL fetch tool (đọc nội dung trang web) tích hợp Jina Reader API (`https://r.jina.ai/`) để chuyển đổi nội dung trang web thành Markdown, giúp tối ưu hóa số lượng token truyền vào context.
3. THE AI_Core SHALL hỗ trợ social trends tool (trending topics per platform).
4. Web search SHALL rate limited: max 3 per request, 50 per hour per tenant.
5. THE AI_Core SHALL hiển thị sources cho user review.

### Requirement 10: Agent Safety & Guardrails (MỚI)

**User Story:** Là admin, tôi muốn AI agent không thực hiện hành động nguy hiểm.

#### Acceptance Criteria
1. THE AI_Core SHALL require human confirmation cho destructive actions (publish, delete).
2. THE AI_Core SHALL prevent infinite loops (max iterations + anti-loop rules: cấm gọi liên tiếp quá 2 lần web_search hoặc 3 lần knowledge_base_search).
3. THE AI_Core SHALL enforce tenant isolation (agent chỉ access data của tenant mình).
4. THE AI_Core SHALL cap total tokens per session (10000 tokens max).
5. THE AI_Core SHALL log tất cả agent decisions cho audit trail.
6. THE AI_Core SHALL hỗ trợ chặn chủ đề (Topic Guardrails) thông qua chỉ thị cấu hình trong System Prompt templates và cơ chế so khớp độ tự tin của tài liệu RAG để từ chối trả lời các chủ đề ngoài phạm vi doanh nghiệp (như chính trị, tôn giáo, đối thủ cạnh tranh...) bằng một câu phản hồi từ chối lịch sự mặc định.
7. THE AI_Core SHALL tích hợp bộ lọc Regex cục bộ (Custom Guardrail Middleware) hiệu năng cao ngay tại tầng Gateway để thực hiện cơ chế De-identification (thay thế dữ liệu PII bằng token động có chỉ mục dạng `[PHONE_1]`, `[EMAIL_1]`, `[CARD_1]`), lưu trữ quan hệ ánh xạ trong cục bộ server (`AgentState["pii_map"]`), khôi phục (Re-identification) tại `ToolExecutor` trước khi gọi API CRM hoặc các phân hệ nội bộ để xử lý và cập nhật, đồng thời khôi phục lại ở đầu ra trước khi hiển thị cho khách hàng. Độ trễ xử lý (processing overhead) của bộ lọc này PHẢI nhỏ hơn 10ms.
8. THE AI_Core SHALL tận dụng các bộ lọc an toàn sẵn có của LLM Providers (như Google Safety Settings cho Gemini) để ngăn chặn các nội dung bạo lực, thù hận, quấy rối và tình dục ở mức độ API của nhà cung cấp.
9. THE AI_Core SHALL tích hợp bộ đánh giá kiểm chứng nguồn tin (NLI Grounding Validator) ở đầu ra bằng mô hình suy luận tự nhiên (NLI) để so khớp câu trả lời với tài liệu RAG gốc. Nếu phát hiện mâu thuẫn (Contradiction) hoặc không có căn cứ (Neutral) với điểm số tin cậy (Grounding Score) < 0.80, hệ thống SHALL chặn phản hồi và tiến hành thử lại (tối đa 2 lần) trước khi tự động chuyển giao cuộc chat cho nhân viên.
10. THE AI_Core SHALL tích hợp bộ kiểm duyệt nội dung đầu ra độc lập (Output Content Moderation) tại tầng ContentGuardrail để phát hiện và ngăn chặn các nội dung thô tục (Profanity), độc hại (Toxicity), và nguy cơ rò rỉ chỉ dẫn hệ thống (Prompt Leakage prevention) trước khi khôi phục dữ liệu PII. Nếu phát hiện vi phạm, hệ thống SHALL chặn phản hồi và trả về câu từ chối mặc định an toàn: "Xin lỗi, tôi không thể hiển thị nội dung này do vi phạm chính sách an toàn thông tin."

## Security & Access Control
- **Authentication & Authorization:** APIs của AI Core Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `ai-core`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến AI Core Service.
- **Tenant Isolation:** Dữ liệu AI Core **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.

---

## Future Roadmap (Phase 2)

### Requirement 11: Semantic Caching
- **AC 11.1:** Dịch vụ SHALL tích hợp Redis Vector Search để lưu trữ các câu trả lời của LLM.
- **AC 11.2:** Khi có câu hỏi mới có độ tương đồng ngữ nghĩa > 90% (Cosine Similarity) với câu hỏi cũ đã lưu, hệ thống SHALL trả về ngay lập tức từ cache, bỏ qua cuộc gọi LLM và KB Search để tối ưu chi phí và tăng tốc phản hồi (< 10ms).

### Requirement 12: Structured Outputs Enforcement
- **AC 12.1:** Dịch vụ SHALL sử dụng JSON Schema (qua tính năng `response_format` của LLM APIs) để bắt buộc Agent phản hồi theo đúng cấu hình định dạng, giúp chatbot và CRM parse kết quả an toàn.

### Requirement 13: Agent Tracing & Observability
- **AC 13.1:** Dịch vụ SHALL tích hợp OpenTelemetry với LangSmith hoặc Arize Phoenix để ghi nhận và hiển thị trực quan sơ đồ suy luận (Thought -> Action -> Observation) của Agent.

### Requirement 14: 12 LLM Providers Custom Optimization
- **AC 14.1:** OpenAI & Anthropic Caching - Dịch vụ SHALL chèn nhãn cache control (`cache_control: {"type": "ephemeral"}` cho Anthropic) tại các điểm breakpoint tĩnh (System Prompt, Tools) và ít biến động (RAG Context, Summary) để kích hoạt prompt caching.
- **AC 14.2:** Google Gemini Settings - Dịch vụ SHALL hỗ trợ thiết lập Google Safety Settings (ngăn chặn bạo lực, thù hận, quấy rối, tình dục) và kích hoạt Context Caching cho các ngữ cảnh lớn (>32k tokens) kèm TTL cụ thể.
- **AC 14.3:** DeepSeek-R1 Optimization - Dịch vụ SHALL trích xuất và lưu trữ khối lập luận (`reasoning_content` hoặc khối `<think>`) đồng thời áp dụng timeout ngắn (5s) và fallback nhanh sang mô hình khác để tránh nghẽn mạng.
- **AC 14.4:** Local LLM Integration - Dịch vụ SHALL cho phép cấu hình custom `api_base` và lưu trữ mã hóa API key cho Ollama/vLLM để gọi các mô hình local.
- **AC 14.5:** Citation Metadata Parsing - Dịch vụ SHALL tự động bóc tách và chuẩn hóa dữ liệu trích dẫn nguồn (`citations`) từ Cohere và Perplexity APIs để hiển thị trên UI.
- **AC 14.6:** Mistral Tool Payload - Dịch vụ SHALL dọn sạch (filter out) các tham số `None` trong schema định nghĩa tools trước khi gọi Mistral API để tránh lỗi Bad Request (400).


