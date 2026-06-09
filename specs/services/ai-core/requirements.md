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
7. THE AI_Core SHALL NOT sử dụng bất kỳ khóa API dùng chung nào (như khóa của hệ thống hoặc biến môi trường fallback) khi Tenant gọi dịch vụ AI. Nếu không tìm thấy khóa API riêng của Tenant trong cơ sở dữ liệu (BYOK model), hệ thống PHẢI lập tức trả về lỗi rõ ràng yêu cầu Tenant cấu hình bổ sung API Key của họ để sử dụng.
8. THE AI_Core SHALL duy trì bảng cấu hình mặc định hệ thống `system_default_route_configs` trong DB để lưu trữ model mặc định cho từng cặp (provider, use_case) thay vì fix cứng trong mã nguồn. Hệ thống sẽ tự động đồng bộ (sync) bảng này khi khởi động dịch vụ (startup) và định kỳ chạy job kéo bảng giá LLM mới nhất từ GitHub LiteLLM. Quá trình kiểm tra tính hợp lệ của tệp giá tải về PHẢI thực hiện xác thực cấu trúc schema động (structural validation - lấy mẫu kiểm tra ngẫu nhiên xem có chứa thông số giá token đầu vào/đầu ra hay không) thay vì kiểm tra sự tồn tại của một tên mô hình fix cứng cụ thể. Sau đó, hệ thống tự động tính toán ra mô hình chat rẻ nhất hiện tại của từng Provider để làm mặc định.
9. THE AI_Core SHALL thực hiện kiểm tra hoạt động (Active Verification) trước mỗi cuộc gọi LLM. Nếu mô hình được cấu hình (ví dụ: mô hình mặc định hoặc mô hình do Tenant cấu hình) không còn tồn tại trong LiteLLM Registry (dấu hiệu bị khai tử ở upstream), hệ thống phải tự động fallback sang mô hình rẻ nhất đang hoạt động của Provider đó và ghi log warning kèm Prometheus metrics để DevOps xử lý.
10. THE AI_Core SHALL tự động khởi tạo các bản ghi cấu hình định tuyến (`LLMRouteConfig`) cho cả 5 usecase cho Tenant dựa trên cấu hình model rẻ nhất của Provider hoạt động tương ứng từ bảng `system_default_route_configs` ngay khi Tenant thêm hoặc đồng bộ khóa API đầu tiên.
11. THE AI_Core SHALL cung cấp REST API `/api/v1/completions/models` trả về danh sách mô hình động bằng cách duyệt qua registry LiteLLM (`model_cost`), lọc toàn bộ mô hình chat (`mode == "chat"`) thuộc 12 nhà cung cấp hỗ trợ trong hệ thống và tự động bổ sung mô hình local mặc định, thay vì trả về danh sách tĩnh fix cứng mô hình.


### Requirement 3: Token Optimization

**User Story:** Là business owner, tôi muốn chi phí AI thấp nhất có thể.

#### Acceptance Criteria
1. THE AI_Core SHALL áp dụng prompt caching (giảm 50% cost cho system prompts)
2. THE AI_Core SHALL compress conversation history: sử dụng logic cắt chuỗi thô (Baseline), và hỗ trợ cơ chế nâng cao (Production-ready) thông qua LLM-based summarization chạy ngầm và lưu Redis cache (TTL 1 giờ). Quá trình nén chỉ kích hoạt khi thỏa mãn đồng thời: tổng số tin nhắn `len(messages) > keep_recent + 4` (mặc định > 9 tin nhắn) và tổng độ dài tin nhắn cũ > 1500 ký tự. Hệ thống phải xác định nhà cung cấp (provider) từ cấu hình định tuyến động (Route Configs) của Tenant cho use-case `summarization` hoặc `chatbot` làm fallback. Từ provider này, hệ thống tự động phân giải ra mô hình hỗ trợ chat rẻ nhất của nhà cung cấp đó từ kho dữ liệu định giá của LiteLLM, sử dụng bộ nhớ đệm trong RAM (`_cheapest_models_cache`) để tối ưu hóa hiệu năng truy xuất O(1), tránh việc fix cứng mô hình trong mã nguồn.
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
4. THE AI_Core SHALL alert khi cost vượt threshold cấu hình của tenant: theo dõi chi phí tích lũy trong 30 ngày qua của tenant, so sánh với hạn mức chi phí (`cost_limit_usd` được định nghĩa trong cấu hình limits của tenant), và tự động kích hoạt tín hiệu cảnh báo (Cost Alert) khi sử dụng đạt 80% hạn mức.
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

### Requirement 8: MCP Tool Registry (Custom & Whitelisted)

**User Story:** Là developer, tôi muốn đăng ký các Custom MCP Server nội bộ (solar_calc, crm, om_ticket) cho AI sử dụng một cách động và bảo mật.

#### Acceptance Criteria
1. THE AI_Core SHALL maintain a whitelisted registry của các Custom MCP Servers (`tenant_mcp_servers` table) theo từng tenant.
2. THE AI_Core SHALL dynamically query and establish SSE (Server-Sent Events) connections tới các whitelisted MCP servers này thông qua `MCPClientManager` để lấy danh sách tools động.
3. THE AI_Core SHALL restrict tools per use case (permission matrix) và thực hiện phân quyền người dùng dựa trên Global Permission Spec (`{service}:{resource}:{action}`). Lớp Guard và Executor bắt buộc phải xác thực chữ ký HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET`, sau đó đối chiếu mã quyền hạn in-memory O(1) với độ trễ dưới 2ms trước khi chạy. AI Core SHALL expose API manifest `GET /api/v1/permissions/manifest` trả về danh sách tài nguyên và hành động mà service hỗ trợ.
4. THE AI_Core SHALL automatically inject/overwrite the `tenant_id` parameter from authenticated JWT into every tool execution argument payload to guarantee strict tenant data isolation.
5. THE AI_Core SHALL block all connections to external public/community MCP servers (like raw postgres, sqlite, or filesystem servers) to eliminate SSRF and prompt injection data exfiltration risks.
6. THE AI_Core SHALL rate limit tool calls (per tool, per tenant) sử dụng cơ chế Redis Token Bucket, và log tất cả tool calls cho audit.

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

### Requirement 15: Self-Registration and Lifecycle Management (MỚI)

**User Story:** Là một developer, tôi muốn service của mình tự động đăng ký và duy trì heartbeat trên Redis Registry khi khởi động để Gateway có thể định tuyến động chính xác mà không phụ thuộc vào hạ tầng.

#### Acceptance Criteria
1. THE AI_Core Service SHALL tự động phát hiện IP nội bộ của container khi khởi chạy.
2. THE AI_Core Service SHALL đăng ký IP:Port của mình vào Redis Set `registry:service:ai-core` khi startup.
3. THE AI_Core Service SHALL gửi tin nhắn sống (heartbeat) định kỳ mỗi 5 giây lên Redis key `registry:service:ai-core:node:{ip}:{port}` với TTL là 15 giây.
4. THE AI_Core Service SHALL tích hợp cơ chế tự hủy đăng ký (deregister) khi nhận tín hiệu kết thúc từ hệ điều hành (`SIGTERM` hoặc `SIGINT`), tự động xóa IP của mình ra khỏi Redis Set để Gateway ngưng chuyển tiếp traffic.



