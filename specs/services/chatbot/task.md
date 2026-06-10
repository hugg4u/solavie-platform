# Task Checklist — CHATBOT Service

## Overview
This document tracks the implementation checklist for **CHATBOT Service** based on the system specifications.

### Technical Stack & Configuration
- **Platform/Tech:** Python 3.12, FastAPI + LangGraph + gRPC

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/chatbot/requirements.md)
- [Design](file:///specs/solavie-system/services/chatbot/design.md)
- [Logging](file:///specs/solavie-system/services/chatbot/logging.md)
- [Business Logic](file:///specs/solavie-system/services/chatbot/business-logic.md)

---

## Tasks Checklist

### Task 1: 1: Intent Classification
> *User Story: Là hệ thống, tôi cần phân loại ý định khách hàng chính xác và nhanh để route xử lý phù hợp.*

**Acceptance Criteria Implementation:**
- [ ] AC 1.1: WHEN message nhận được qua gRPC, THE Chatbot_Service SHALL phân loại intent thành một trong các nhóm: faq, sales_inquiry, site_survey_booking, complaint, chitchat, out_of_scope
- [ ] AC 1.2: THE Chatbot_Service SHALL detect ngôn ngữ của tin nhắn (tối thiểu: Tiếng Việt, English)
- [ ] AC 1.3: THE Chatbot_Service SHALL chạy intent classification song song với embedding query để tối ưu latency
- [ ] AC 1.4: Intent classification SHALL hoàn thành trong < 200ms
- [ ] AC 1.5: THE Chatbot_Service SHALL trả về intent label kèm confidence score (0.0-1.0) cho mỗi phân loại

### Task 2: 2: RAG Retrieval
> *User Story: Là chatbot, tôi cần tìm thông tin chính xác từ knowledge base nội bộ của Solavie để trả lời, không tự bịa.*

**Acceptance Criteria Implementation:**
- [ ] AC 2.1: THE Chatbot_Service SHALL gọi Knowledge_Base Service để thực hiện hybrid search (dense + sparse)
- [ ] AC 2.2: THE Chatbot_Service SHALL nhận top-5 relevant document chunks sau reranking từ Knowledge Base
- [ ] AC 2.3: IF RAG relevance score của tất cả chunks < ngưỡng rag_relevance_threshold cấu hình (mặc định 0.5), THEN THE Chatbot_Service SHALL kích hoạt handoff ngay lập tức thay vì trả lời
- [ ] AC 2.4: THE Chatbot_Service SHALL truncate và nén context documents để tối ưu token budget trước khi gửi lên LLM
- [ ] AC 2.5: THE Chatbot_Service SHALL gửi kèm top-5 chunks làm context cho AI Core khi generate response

### Task 3: 3: Response Generation
> *User Story: Là khách hàng, tôi muốn nhận câu trả lời chính xác, tự nhiên và nhất quán với ngữ cảnh cuộc trò chuyện.*

**Acceptance Criteria Implementation:**
- [ ] AC 3.1: THE Chatbot_Service SHALL gọi AI_Core qua gRPC để generate response với context RAG và conversation history
- [ ] AC 3.2: THE Chatbot_Service SHALL include compressed conversation history trong context để duy trì ngữ cảnh
- [ ] AC 3.3: THE Chatbot_Service SHALL generate response bằng đúng ngôn ngữ khách hàng đang sử dụng
- [ ] AC 3.4: Response generation SHALL hoàn thành trong < 1.5 giây (không tính streaming)
- [ ] AC 3.5: THE Chatbot_Service SHALL hỗ trợ streaming response qua gRPC stream cho trải nghiệm realtime

### Task 4: 4: Confidence Scoring & Handoff
> *User Story: Là chủ doanh nghiệp, tôi muốn bot chỉ trả lời khi chắc chắn đúng, và chuyển ngay cho nhân viên khi không chắc.*

**Acceptance Criteria Implementation:**
- [ ] AC 4.1: THE Chatbot_Service SHALL tính confidence score (0.0-1.0) tổng hợp từ: intent confidence, RAG relevance score, NLI grounding score
- [ ] AC 4.2: WHEN confidence >= ngưỡng confidence_threshold cấu hình (mặc định 0.70), THE Chatbot_Service SHALL gửi response cho khách hàng
- [ ] AC 4.3: WHEN confidence < confidence_threshold, THE Chatbot_Service SHALL kích hoạt handoff ngay lập tức và KHÔNG gửi response tự động
- [ ] AC 4.4: WHEN sentiment score của tin nhắn khách hàng >= 0.60 (angry/negative), THE Chatbot_Service SHALL kích hoạt handoff khẩn cấp bỏ qua mọi bước xử lý tiếp theo
- [ ] AC 4.5: IF AI_Core timeout > 5 giây, THEN THE Chatbot_Service SHALL kích hoạt handoff ngay lập tức
- [ ] AC 4.6: WHEN handoff được kích hoạt, THE Chatbot_Service SHALL gửi tin nhắn thông báo chờ cho khách (ví dụ: "Yêu cầu của bạn đang được chuyển đến nhân viên tư vấn...") trước khi chuyển giao

### Task 5: 5: Multi-language Support
> *User Story: Là khách hàng, tôi muốn chat bằng ngôn ngữ của mình và nhận câu trả lời bằng ngôn ngữ đó.*

**Acceptance Criteria Implementation:**
- [ ] AC 5.1: THE Chatbot_Service SHALL detect ngôn ngữ từ nội dung tin nhắn đầu vào
- [ ] AC 5.2: THE Chatbot_Service SHALL trả lời bằng đúng ngôn ngữ khách hàng đang sử dụng trong phiên chat
- [ ] AC 5.3: THE Chatbot_Service SHALL hỗ trợ tối thiểu: Tiếng Việt và English
- [ ] AC 5.4: THE Chatbot_Service SHALL duy trì ngôn ngữ nhất quán trong suốt phiên chat trừ khi khách chủ động chuyển ngôn ngữ

### Task 6: 6: Conversation State Management
> *User Story: Là hệ thống, tôi cần duy trì context qua nhiều lượt chat để chatbot hiểu ngữ cảnh mà không hỏi lại.*

**Acceptance Criteria Implementation:**
- [ ] AC 6.1: THE Chatbot_Service SHALL lưu LangGraph state checkpoints vào PostgreSQL (chatbot_db) sau mỗi lượt chat
- [ ] AC 6.2: THE Chatbot_Service SHALL resume conversation state từ checkpoint khi khách hàng reply tiếp theo
- [ ] AC 6.3: THE Chatbot_Service SHALL duy trì tối đa 10 tin nhắn gần nhất trong MessagesState
- [ ] AC 6.4: WHEN số tin nhắn > 10 hoặc tổng tokens > 4000, THE Chatbot_Service SHALL tự động trigger Summarization Node (xem Requirement 10)
- [ ] AC 6.5: THE Chatbot_Service SHALL đảm bảo state consistency khi xử lý đa luồng (concurrent requests cùng conversation)

### Task 7: 7: AI Vision — Đọc hóa đơn tiền điện
> *User Story: Là khách hàng, tôi muốn chụp ảnh hóa đơn tiền điện gửi lên thay vì phải nhập số thủ công.*

**Acceptance Criteria Implementation:**
- [ ] AC 7.1: WHEN nhận tin nhắn dạng ảnh và cấu hình ai_vision_invoice_reading = true, THE Chatbot_Service SHALL gọi AI Core sử dụng Vision LLM để OCR trích xuất: số tiền điện (VND), sản lượng tiêu thụ (kWh), mã khách hàng EVN, họ tên chủ hộ
- [ ] AC 7.2: THE Chatbot_Service SHALL cập nhật thông tin trích xuất vào CRM Contact của khách hàng
- [ ] AC 7.3: WHEN cấu hình ai_vision_invoice_reading = false, THE Chatbot_Service SHALL bỏ qua phân tích ảnh và kích hoạt Handoff cho Agent xử lý thủ công
- [ ] AC 7.4: IF Vision LLM không thể trích xuất thông tin rõ ràng từ ảnh, THEN THE Chatbot_Service SHALL yêu cầu khách chụp lại ảnh rõ hơn hoặc nhập thủ công

### Task 8: 8: Input Guardrail — Semantic Router
> *User Story: Là chủ doanh nghiệp, tôi muốn chatbot không trả lời các câu hỏi về đối thủ, chính trị, tôn giáo hoặc bị tấn công jailbreak.*

**Acceptance Criteria Implementation:**
- [ ] AC 8.1: THE Chatbot_Service SHALL kiểm tra mọi tin nhắn đầu vào qua Semantic Router trước khi chuyển tới LLM
- [ ] AC 8.2: IF Semantic Router phát hiện tin nhắn thuộc danh mục cấm (đối thủ cạnh tranh điện mặt trời, chính trị, tôn giáo, xã hội nhạy cảm), THEN THE Chatbot_Service SHALL chặn ngay và trả về câu từ chối định nghĩa sẵn
- [ ] AC 8.3: IF Semantic Router phát hiện dấu hiệu Jailbreak hoặc Prompt Injection, THEN THE Chatbot_Service SHALL chặn ngay và trả về câu từ chối, KHÔNG chuyển tiếp tới LLM
- [ ] AC 8.4: THE Chatbot_Service SHALL điều hướng khéo léo khách hàng quay lại chủ đề điện mặt trời sau khi từ chối
- [ ] AC 8.5: THE Chatbot_Service SHALL log tất cả tin nhắn bị chặn vào audit log với lý do

### Task 9: 9: Output Guardrail — NLI Grounding Validator
> *User Story: Là chủ doanh nghiệp, tôi muốn chatbot không bao giờ đưa ra thông tin sai lệch hoặc không có cơ sở trong tài liệu nội bộ.*

**Acceptance Criteria Implementation:**
- [ ] AC 9.1: THE Chatbot_Service SHALL kiểm tra tính xác thực (Grounding) của mọi câu trả lời RAG qua mô hình NLI trước khi gửi cho khách
- [ ] AC 9.2: IF NLI phân loại câu trả lời là Contradiction (mâu thuẫn với context RAG), THEN THE Chatbot_Service SHALL chặn câu trả lời và tự động sinh lại (regenerate) tối đa 1 lần
- [ ] AC 9.3: IF NLI phân loại câu trả lời là Neutral (không thể chứng thực bằng context RAG), THEN THE Chatbot_Service SHALL chặn câu trả lời và kích hoạt Handoff
- [ ] AC 9.4: WHEN Grounding Score >= 0.80 (Entailment), THE Chatbot_Service SHALL cho phép gửi câu trả lời cho khách hàng
- [ ] AC 9.5: IF regenerate vẫn không đạt Grounding Score >= 0.80, THEN THE Chatbot_Service SHALL kích hoạt Handoff thay vì gửi câu trả lời không chắc chắn

### Task 10: 10: Sliding Window Memory & Auto-Summarization
> *User Story: Là hệ thống, tôi cần tối ưu chi phí token bằng cách tóm tắt lịch sử chat dài mà không mất ngữ cảnh quan trọng.*

**Acceptance Criteria Implementation:**
- [ ] AC 10.1: WHEN số tin nhắn trong MessagesState > 10 hoặc tổng tokens > 4000, THE Chatbot_Service SHALL tự động gọi LLM để tóm tắt các tin nhắn cũ
- [ ] AC 10.2: THE Chatbot_Service SHALL lưu nội dung tóm tắt vào trường summary của LangGraph state
- [ ] AC 10.3: THE Chatbot_Service SHALL trim (cắt bỏ) các tin nhắn cũ đã được tóm tắt, chỉ giữ lại summary + N tin nhắn gần nhất
- [ ] AC 10.4: THE Chatbot_Service SHALL đảm bảo summary được include trong context khi generate response tiếp theo
- [ ] AC 10.5: Summarization SHALL không làm gián đoạn luồng hội thoại với khách hàng

### Task 11: 11: Lead Capture Flow — Ngoài giờ làm việc
> *User Story: Là chủ doanh nghiệp, tôi muốn chatbot thu thập thông tin khách hàng tiềm năng ngay cả khi ngoài giờ làm việc.*

**Acceptance Criteria Implementation:**
- [ ] AC 11.1: WHEN ngoài khung giờ làm việc cấu hình (working_hours) và offline_mode_behavior = lead_capture, THE Chatbot_Service SHALL kích hoạt kịch bản thu thập thông tin tự động
- [ ] AC 11.2: THE Chatbot_Service SHALL thu thập tuần tự: Họ tên, Số điện thoại, Địa chỉ lắp đặt
- [ ] AC 11.3: THE Chatbot_Service SHALL validate SĐT: đúng 10 chữ số, bắt đầu bằng 03/05/07/08/09; nếu sai SHALL yêu cầu nhập lại lịch sự
- [ ] AC 11.4: WHEN thu thập đủ thông tin, THE Chatbot_Service SHALL lưu Contact vào CRM và tạo Deal ở giai đoạn lead
- [ ] AC 11.5: WHEN Lead Capture hoàn tất, THE Chatbot_Service SHALL khóa chatbot (không tự do trò chuyện) cho đến khi nhân viên vào làm việc hôm sau

### Task 12: 12: Human-in-the-loop Breakpoints
> *User Story: Là chủ doanh nghiệp, tôi muốn kiểm soát các hành động nhạy cảm của AI trước khi thực thi.*

**Acceptance Criteria Implementation:**
- [ ] AC 12.1: WHEN Chatbot chuẩn bị gọi công cụ nằm trong danh sách required_approvals cấu hình của Tenant, THE Chatbot_Service SHALL tự động tạm dừng LangGraph graph tại breakpoint
- [ ] AC 12.2: THE Chatbot_Service SHALL tạo sự kiện ActionApproval ở trạng thái Pending và đẩy lên Dashboard của Agent phụ trách
- [ ] AC 12.3: THE Chatbot_Service SHALL gửi tin nhắn thông báo chờ duyệt cho khách hàng
- [ ] AC 12.4: WHEN nhận tín hiệu Approve từ Agent, THE Chatbot_Service SHALL tiếp tục thực thi graph từ breakpoint
- [ ] AC 12.5: WHEN nhận tín hiệu Reject từ Agent, THE Chatbot_Service SHALL thực hiện compensating action (rollback) và thông báo cho khách
- [ ] AC 12.6: THE Chatbot_Service SHALL timeout breakpoint sau 30 phút nếu không có phản hồi từ Agent và kích hoạt Handoff

### Task 13: 13: Prompt Caching & Token Optimization
> *User Story: Là chủ doanh nghiệp, tôi muốn chi phí vận hành AI thấp nhất có thể mà không giảm chất lượng.*

**Acceptance Criteria Implementation:**
- [ ] AC 13.1: THE Chatbot_Service SHALL cấu hình AI Core để cache system prompt, schemas công cụ MCP và tài liệu tĩnh ở đầu prompt
- [ ] AC 13.2: THE Chatbot_Service SHALL tái sử dụng prompt cache cho các tin nhắn tiếp theo trong cùng phiên, giảm tối thiểu 50% chi phí input token
- [ ] AC 13.3: THE Chatbot_Service SHALL nén conversation history (qua Summarization) trước khi gửi lên LLM để giảm token
- [ ] AC 13.4: THE Chatbot_Service SHALL đạt token cost trung bình < $0.005 per message
- [ ] AC 13.5: THE Chatbot_Service SHALL log token usage (input/output/cached) cho mỗi LLM call để Analytics theo dõi chi phí

### Task 14: Implement Business Logic Rules
**Business Validations:**
- [ ] Tổng quan vai trò (CẬP NHẬT): Nhận message từ Messaging (gRPC)
- [ ] Tổng quan vai trò (CẬP NHẬT): Load conversation state (checkpoint)
- [ ] Tổng quan vai trò (CẬP NHẬT): Gọi AI Core agent (use_case="chatbot") — AI Core tự handle: intent, RAG, response, confidence
- [ ] Tổng quan vai trò (CẬP NHẬT): Nhận kết quả → return cho Messaging
- [ ] Tổng quan vai trò (CẬP NHẬT): Lưu checkpoint
- [ ] Tổng quan vai trò (CẬP NHẬT): Intent classification (via reasoning)
- [ ] Tổng quan vai trò (CẬP NHẬT): RAG retrieval (via knowledge_base_search tool)
- [ ] Tổng quan vai trò (CẬP NHẬT): Response generation (via LLM)
- [ ] Tổng quan vai trò (CẬP NHẬT): Confidence evaluation (built into agent loop)
- [ ] Tổng quan vai trò (CẬP NHẬT): Handoff decision (via handoff_to_agent tool)
- [ ] Tổng quan vai trò (CẬP NHẬT): Sentiment analysis (via analyze_sentiment tool)
- [ ] Tổng quan vai trò (CẬP NHẬT): gRPC server interface (Messaging gọi vào)
- [ ] Tổng quan vai trò (CẬP NHẬT): Conversation state management (LangGraph checkpoints)
- [ ] Tổng quan vai trò (CẬP NHẬT): Timeout handling (5s max → auto handoff)
- [ ] Tổng quan vai trò (CẬP NHẬT): Per-tenant chatbot config (confidence threshold, enabled languages)
- [ ] Tổng quan vai trò (CẬP NHẬT): Metrics collection (intent distribution, handoff rate)
- [ ] Node 1: Classify Intent (parallel): faq: Hỏi thông tin (giờ mở cửa, chính sách, etc.)
- [ ] Node 1: Classify Intent (parallel): sales: Quan tâm mua hàng (hỏi giá, so sánh, etc.)
- [ ] Node 1: Classify Intent (parallel): support: Cần hỗ trợ kỹ thuật (lỗi, không hoạt động, etc.)
- [ ] Node 1: Classify Intent (parallel): complaint: Phàn nàn, tức giận → HANDOFF NGAY
- [ ] Node 1: Classify Intent (parallel): chitchat: Chào hỏi, nói chuyện phiếm
- [ ] Node 1: Classify Intent (parallel): If customer is angry, frustrated, or complaining → intent=complaint
- [ ] Node 1: Classify Intent (parallel): If asking about price, buying, ordering → intent=sales
- [ ] Node 1: Classify Intent (parallel): If greeting, small talk → intent=chitchat
- [ ] Node 1: Classify Intent (parallel): If reporting a problem, error → intent=support
- [ ] Node 1: Classify Intent (parallel): Otherwise → intent=faq"""
- [ ] Node 3: Route by Intent: complaint hoặc angry → HANDOFF NGAY, không cần RAG
- [ ] Node 3: Route by Intent: chitchat → generate simple reply, không cần RAG
- [ ] Node 3: Route by Intent: faq/sales/support → cần RAG để trả lời chính xác
- [ ] Node 4: Retrieve Knowledge: Call KB hybrid search API
- [ ] Node 4: Retrieve Knowledge: KB thực hiện: vector search + BM25 + rerank
- [ ] Node 4: Retrieve Knowledge: Trả về top-5 documents
- [ ] Node 4: Retrieve Knowledge: Kiểm tra quality: nếu top score < 0.5 → không có info → handoff
- [ ] Node 5: Generate Response: Chỉ trả lời dựa trên context (không hallucinate)
- [ ] Node 5: Generate Response: Yêu cầu LLM trả về confidence score
- [ ] Node 5: Generate Response: Nếu context không đủ → LLM phải nói "không biết" → confidence thấp
- [ ] Node 5: Generate Response: Answer ONLY based on the provided Context
- [ ] Node 5: Generate Response: If the Context does not contain the answer, respond with:
- [ ] Node 5: Generate Response: NEVER make up information
- [ ] Node 5: Generate Response: Be concise (2-3 sentences max)
- [ ] Node 5: Generate Response: Match the customer's language
- [ ] Node 5: Generate Response: confidence 0.9-1.0: Answer is directly in context
- [ ] Node 5: Generate Response: confidence 0.7-0.8: Answer is implied by context
- [ ] Node 5: Generate Response: confidence 0.0-0.6: Not sure / not in context"""
- [ ] Conversation State (LangGraph Checkpoint): Mỗi conversation có 1 checkpoint trong PostgreSQL
- [ ] Conversation State (LangGraph Checkpoint): Khi khách reply tiếp → load checkpoint → resume graph
- [ ] Conversation State (LangGraph Checkpoint): Cho phép multi-turn conversation với context

## Verification & Testing

### Automated Tests
- [ ] Write unit tests verifying core logic of each Requirement.
- [ ] Write integration tests for API endpoints.
- [ ] Verify tenant isolation by querying data across different tenant IDs.

### Manual Verification
- [ ] Deploy service to local Docker / Kubernetes cluster.
- [ ] Perform end-to-end tests using the Gateway (Kong) routing.

## Done When

- [ ] All Acceptance Criteria for Requirements are implemented and verified.
- [ ] Unit test coverage is >80%.
- [ ] Logs are formatted as structured JSON and trace context is propagated.
- [ ] Tenant isolation (RLS / metadata filtering) is strictly enforced.

### Task: Security Integration & Dynamic RBAC (MỚI)
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `chatbot`.
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`.
- [ ] Triển khai HMAC Signature Verification Guard/Interceptor sử dụng `GATEWAY_SIGNING_SECRET` để xác thực request từ Gateway.
- [ ] Triển khai cơ chế so khớp quyền hạn Dynamic RBAC in-memory O(1) hỗ trợ wildcard (`*`, `chatbot:*`, `chatbot:{resource}:*`).
- [ ] Thực hiện tích hợp Endpoint `/api/v1/permissions/manifest` trả về danh sách tài nguyên và quyền hạn của service.
- [ ] Bổ sung các test cases kiểm tra Signature Verification và Access Control Denied.

---

## Service Discovery Client Integration (MỚI)

### Task 21: Service Discovery Client Integration
- [ ] AC 21.1: Triển khai lớp `ServiceRegistryClient` tự động lấy IP nội bộ qua kết nối UDP socket ảo.
- [ ] AC 21.2: Tích hợp `ServiceRegistryClient` vào lifecycle hook khởi động và tắt của ứng dụng (FastAPI).
- [ ] AC 21.3: Triển khai cấu trúc JSON logs cho các sự kiện đăng ký và lỗi heartbeat lên Redis.
