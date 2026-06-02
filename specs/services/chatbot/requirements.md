# Requirements Document

## Introduction

Dịch vụ chatbot AI "nhân sự số" 24/7 của Solavie — sử dụng LangGraph để quản lý state đồ thị hội thoại, phân loại intent, RAG retrieval, response generation, confidence scoring, auto-handoff, AI Vision OCR, Input/Output Guardrails, Lead Capture Flow, Human-in-the-loop Breakpoints và Prompt Caching.

## Glossary

- **Chatbot_Service**: Dịch vụ chatbot AI (Python 3.12, FastAPI + LangGraph + gRPC)
- **LangGraph**: Framework quản lý state đồ thị hội thoại
- **Intent**: Ý định của khách hàng: faq, sales_inquiry, site_survey_booking, complaint, chitchat, out_of_scope
- **RAG**: Retrieval-Augmented Generation — truy xuất tri thức nội bộ
- **Confidence_Score**: Điểm tin cậy tổng hợp (0.0-1.0) từ intent confidence + RAG relevance + NLI grounding
- **Handoff**: Chuyển hội thoại từ bot sang nhân viên khi confidence < threshold hoặc sentiment tiêu cực
- **Semantic_Router**: Bộ định tuyến ngữ nghĩa — lọc câu hỏi không phù hợp (đối thủ, jailbreak, chính trị)
- **NLI**: Natural Language Inference — kiểm tra tính xác thực câu trả lời AI (Entailment/Contradiction/Neutral)
- **Grounding_Score**: Điểm xác thực câu trả lời qua NLI, >= 0.80 mới được gửi cho khách
- **Breakpoint**: Điểm tạm dừng LangGraph để chờ phê duyệt từ Agent trước khi thực thi hành động nhạy cảm
- **Lead_Capture**: Kịch bản thu thập thông tin khách hàng tiềm năng ngoài giờ làm việc
- **Sliding_Window**: Cơ chế duy trì tối đa 10 tin nhắn gần nhất + summary tin nhắn cũ

## Requirements

### Requirement 1: Intent Classification

**User Story:** Là hệ thống, tôi cần phân loại ý định khách hàng chính xác và nhanh để route xử lý phù hợp.

#### Acceptance Criteria
1. WHEN message nhận được qua gRPC, THE Chatbot_Service SHALL phân loại intent thành một trong các nhóm: faq, sales_inquiry, site_survey_booking, complaint, chitchat, out_of_scope
2. THE Chatbot_Service SHALL detect ngôn ngữ của tin nhắn (tối thiểu: Tiếng Việt, English)
3. THE Chatbot_Service SHALL chạy intent classification song song với embedding query để tối ưu latency
4. Intent classification SHALL hoàn thành trong < 200ms
5. THE Chatbot_Service SHALL trả về intent label kèm confidence score (0.0-1.0) cho mỗi phân loại

### Requirement 2: RAG Retrieval

**User Story:** Là chatbot, tôi cần tìm thông tin chính xác từ knowledge base nội bộ của Solavie để trả lời, không tự bịa.

#### Acceptance Criteria
1. THE Chatbot_Service SHALL gọi Knowledge_Base Service để thực hiện hybrid search (dense + sparse)
2. THE Chatbot_Service SHALL nhận top-5 relevant document chunks sau reranking từ Knowledge Base
3. IF RAG relevance score của tất cả chunks < ngưỡng rag_relevance_threshold cấu hình (mặc định 0.5), THEN THE Chatbot_Service SHALL kích hoạt handoff ngay lập tức thay vì trả lời
4. THE Chatbot_Service SHALL truncate và nén context documents để tối ưu token budget trước khi gửi lên LLM
5. THE Chatbot_Service SHALL gửi kèm top-5 chunks làm context cho AI Core khi generate response

### Requirement 3: Response Generation

**User Story:** Là khách hàng, tôi muốn nhận câu trả lời chính xác, tự nhiên và nhất quán với ngữ cảnh cuộc trò chuyện.

#### Acceptance Criteria
1. THE Chatbot_Service SHALL gọi AI_Core qua gRPC để generate response với context RAG và conversation history
2. THE Chatbot_Service SHALL include compressed conversation history trong context để duy trì ngữ cảnh
3. THE Chatbot_Service SHALL generate response bằng đúng ngôn ngữ khách hàng đang sử dụng
4. Response generation SHALL hoàn thành trong < 1.5 giây (không tính streaming)
5. THE Chatbot_Service SHALL hỗ trợ streaming response qua gRPC stream cho trải nghiệm realtime

### Requirement 4: Confidence Scoring & Handoff

**User Story:** Là chủ doanh nghiệp, tôi muốn bot chỉ trả lời khi chắc chắn đúng, và chuyển ngay cho nhân viên khi không chắc.

#### Acceptance Criteria
1. THE Chatbot_Service SHALL tính confidence score (0.0-1.0) tổng hợp từ: intent confidence, RAG relevance score, NLI grounding score
2. WHEN confidence >= ngưỡng confidence_threshold cấu hình (mặc định 0.70), THE Chatbot_Service SHALL gửi response cho khách hàng
3. WHEN confidence < confidence_threshold, THE Chatbot_Service SHALL kích hoạt handoff ngay lập tức và KHÔNG gửi response tự động
4. WHEN sentiment score của tin nhắn khách hàng >= 0.60 (angry/negative), THE Chatbot_Service SHALL kích hoạt handoff khẩn cấp bỏ qua mọi bước xử lý tiếp theo
5. IF AI_Core timeout > 5 giây, THEN THE Chatbot_Service SHALL kích hoạt handoff ngay lập tức
6. WHEN handoff được kích hoạt, THE Chatbot_Service SHALL gửi tin nhắn thông báo chờ cho khách (ví dụ: "Yêu cầu của bạn đang được chuyển đến nhân viên tư vấn...") trước khi chuyển giao

### Requirement 5: Multi-language Support

**User Story:** Là khách hàng, tôi muốn chat bằng ngôn ngữ của mình và nhận câu trả lời bằng ngôn ngữ đó.

#### Acceptance Criteria
1. THE Chatbot_Service SHALL detect ngôn ngữ từ nội dung tin nhắn đầu vào
2. THE Chatbot_Service SHALL trả lời bằng đúng ngôn ngữ khách hàng đang sử dụng trong phiên chat
3. THE Chatbot_Service SHALL hỗ trợ tối thiểu: Tiếng Việt và English
4. THE Chatbot_Service SHALL duy trì ngôn ngữ nhất quán trong suốt phiên chat trừ khi khách chủ động chuyển ngôn ngữ

### Requirement 6: Conversation State Management

**User Story:** Là hệ thống, tôi cần duy trì context qua nhiều lượt chat để chatbot hiểu ngữ cảnh mà không hỏi lại.

#### Acceptance Criteria
1. THE Chatbot_Service SHALL lưu LangGraph state checkpoints vào PostgreSQL (chatbot_db) sau mỗi lượt chat
2. THE Chatbot_Service SHALL resume conversation state từ checkpoint khi khách hàng reply tiếp theo
3. THE Chatbot_Service SHALL duy trì tối đa 10 tin nhắn gần nhất trong MessagesState
4. WHEN số tin nhắn > 10 hoặc tổng tokens > 4000, THE Chatbot_Service SHALL tự động trigger Summarization Node (xem Requirement 10)
5. THE Chatbot_Service SHALL đảm bảo state consistency khi xử lý đa luồng (concurrent requests cùng conversation)

### Requirement 7: AI Vision — Đọc hóa đơn tiền điện

**User Story:** Là khách hàng, tôi muốn chụp ảnh hóa đơn tiền điện gửi lên thay vì phải nhập số thủ công.

#### Acceptance Criteria
1. WHEN nhận tin nhắn dạng ảnh và cấu hình ai_vision_invoice_reading = true, THE Chatbot_Service SHALL gọi AI Core sử dụng Vision LLM để OCR trích xuất: số tiền điện (VND), sản lượng tiêu thụ (kWh), mã khách hàng EVN, họ tên chủ hộ
2. THE Chatbot_Service SHALL cập nhật thông tin trích xuất vào CRM Contact của khách hàng
3. WHEN cấu hình ai_vision_invoice_reading = false, THE Chatbot_Service SHALL bỏ qua phân tích ảnh và kích hoạt Handoff cho Agent xử lý thủ công
4. IF Vision LLM không thể trích xuất thông tin rõ ràng từ ảnh, THEN THE Chatbot_Service SHALL yêu cầu khách chụp lại ảnh rõ hơn hoặc nhập thủ công

### Requirement 8: Input Guardrail — Semantic Router

**User Story:** Là chủ doanh nghiệp, tôi muốn chatbot không trả lời các câu hỏi về đối thủ, chính trị, tôn giáo hoặc bị tấn công jailbreak.

#### Acceptance Criteria
1. THE Chatbot_Service SHALL kiểm tra mọi tin nhắn đầu vào qua Semantic Router trước khi chuyển tới LLM
2. IF Semantic Router phát hiện tin nhắn thuộc danh mục cấm (đối thủ cạnh tranh điện mặt trời, chính trị, tôn giáo, xã hội nhạy cảm), THEN THE Chatbot_Service SHALL chặn ngay và trả về câu từ chối định nghĩa sẵn
3. IF Semantic Router phát hiện dấu hiệu Jailbreak hoặc Prompt Injection, THEN THE Chatbot_Service SHALL chặn ngay và trả về câu từ chối, KHÔNG chuyển tiếp tới LLM
4. THE Chatbot_Service SHALL điều hướng khéo léo khách hàng quay lại chủ đề điện mặt trời sau khi từ chối
5. THE Chatbot_Service SHALL log tất cả tin nhắn bị chặn vào audit log với lý do

### Requirement 9: Output Guardrail — NLI Grounding Validator

**User Story:** Là chủ doanh nghiệp, tôi muốn chatbot không bao giờ đưa ra thông tin sai lệch hoặc không có cơ sở trong tài liệu nội bộ.

#### Acceptance Criteria
1. THE Chatbot_Service SHALL kiểm tra tính xác thực (Grounding) của mọi câu trả lời RAG qua mô hình NLI trước khi gửi cho khách
2. IF NLI phân loại câu trả lời là Contradiction (mâu thuẫn với context RAG), THEN THE Chatbot_Service SHALL chặn câu trả lời và tự động sinh lại (regenerate) tối đa 1 lần
3. IF NLI phân loại câu trả lời là Neutral (không thể chứng thực bằng context RAG), THEN THE Chatbot_Service SHALL chặn câu trả lời và kích hoạt Handoff
4. WHEN Grounding Score >= 0.80 (Entailment), THE Chatbot_Service SHALL cho phép gửi câu trả lời cho khách hàng
5. IF regenerate vẫn không đạt Grounding Score >= 0.80, THEN THE Chatbot_Service SHALL kích hoạt Handoff thay vì gửi câu trả lời không chắc chắn

### Requirement 10: Sliding Window Memory & Auto-Summarization

**User Story:** Là hệ thống, tôi cần tối ưu chi phí token bằng cách tóm tắt lịch sử chat dài mà không mất ngữ cảnh quan trọng.

#### Acceptance Criteria
1. WHEN số tin nhắn trong MessagesState > 10 hoặc tổng tokens > 4000, THE Chatbot_Service SHALL tự động gọi LLM để tóm tắt các tin nhắn cũ
2. THE Chatbot_Service SHALL lưu nội dung tóm tắt vào trường summary của LangGraph state
3. THE Chatbot_Service SHALL trim (cắt bỏ) các tin nhắn cũ đã được tóm tắt, chỉ giữ lại summary + N tin nhắn gần nhất
4. THE Chatbot_Service SHALL đảm bảo summary được include trong context khi generate response tiếp theo
5. Summarization SHALL không làm gián đoạn luồng hội thoại với khách hàng

### Requirement 11: Lead Capture Flow — Ngoài giờ làm việc

**User Story:** Là chủ doanh nghiệp, tôi muốn chatbot thu thập thông tin khách hàng tiềm năng ngay cả khi ngoài giờ làm việc.

#### Acceptance Criteria
1. WHEN ngoài khung giờ làm việc cấu hình (working_hours) và offline_mode_behavior = lead_capture, THE Chatbot_Service SHALL kích hoạt kịch bản thu thập thông tin tự động
2. THE Chatbot_Service SHALL thu thập tuần tự: Họ tên, Số điện thoại, Địa chỉ lắp đặt
3. THE Chatbot_Service SHALL validate SĐT: đúng 10 chữ số, bắt đầu bằng 03/05/07/08/09; nếu sai SHALL yêu cầu nhập lại lịch sự
4. WHEN thu thập đủ thông tin, THE Chatbot_Service SHALL lưu Contact vào CRM và tạo Deal ở giai đoạn lead
5. WHEN Lead Capture hoàn tất, THE Chatbot_Service SHALL khóa chatbot (không tự do trò chuyện) cho đến khi nhân viên vào làm việc hôm sau

### Requirement 12: Human-in-the-loop Breakpoints

**User Story:** Là chủ doanh nghiệp, tôi muốn kiểm soát các hành động nhạy cảm của AI trước khi thực thi.

#### Acceptance Criteria
1. WHEN Chatbot chuẩn bị gọi công cụ nằm trong danh sách required_approvals cấu hình của Tenant, THE Chatbot_Service SHALL tự động tạm dừng LangGraph graph tại breakpoint
2. THE Chatbot_Service SHALL tạo sự kiện ActionApproval ở trạng thái Pending và đẩy lên Dashboard của Agent phụ trách
3. THE Chatbot_Service SHALL gửi tin nhắn thông báo chờ duyệt cho khách hàng
4. WHEN nhận tín hiệu Approve từ Agent, THE Chatbot_Service SHALL tiếp tục thực thi graph từ breakpoint
5. WHEN nhận tín hiệu Reject từ Agent, THE Chatbot_Service SHALL thực hiện compensating action (rollback) và thông báo cho khách
6. THE Chatbot_Service SHALL timeout breakpoint sau 30 phút nếu không có phản hồi từ Agent và kích hoạt Handoff

### Requirement 13: Prompt Caching & Token Optimization

**User Story:** Là chủ doanh nghiệp, tôi muốn chi phí vận hành AI thấp nhất có thể mà không giảm chất lượng.

#### Acceptance Criteria
1. THE Chatbot_Service SHALL cấu hình AI Core để cache system prompt, schemas công cụ MCP và tài liệu tĩnh ở đầu prompt
2. THE Chatbot_Service SHALL tái sử dụng prompt cache cho các tin nhắn tiếp theo trong cùng phiên, giảm tối thiểu 50% chi phí input token
3. THE Chatbot_Service SHALL nén conversation history (qua Summarization) trước khi gửi lên LLM để giảm token
4. THE Chatbot_Service SHALL đạt token cost trung bình < $0.005 per message
5. THE Chatbot_Service SHALL log token usage (input/output/cached) cho mỗi LLM call để Analytics theo dõi chi phí

## Security & Access Control
- **Authentication & Authorization:** APIs của Chatbot Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `chatbot`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Chatbot Service.
- **Tenant Isolation:** Dữ liệu Chatbot **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.
