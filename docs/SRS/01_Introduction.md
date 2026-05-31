# 1. GIỚI THIỆU (INTRODUCTION)

> Phần này tuân thủ cấu trúc IEEE 830-1998 Section 1 và ISO/IEC/IEEE 29148:2018.

---

## 1.1. Mục đích tài liệu (Purpose)

Tài liệu Đặc tả Yêu cầu Phần mềm (SRS) này mô tả đầy đủ và chi tiết các yêu cầu chức năng, yêu cầu phi chức năng, giao diện hệ thống, mô hình dữ liệu và các ràng buộc kỹ thuật của **Nền tảng Marketing Đa kênh Tích hợp AI (AI-Powered Multi-Channel Marketing Platform)**.

### Đối tượng đọc và mục đích sử dụng

| Đối tượng | Mục đích sử dụng |
|-----------|-----------------|
| **Product Owner / Stakeholders** | Xác nhận tính đầy đủ và chính xác của yêu cầu nghiệp vụ trước khi phát triển |
| **Software Architects** | Thiết kế kiến trúc hệ thống, xác định service boundaries và communication patterns |
| **Backend/Frontend Developers** | Hiểu rõ logic nghiệp vụ, API contracts, data models để triển khai đúng yêu cầu |
| **QA Engineers** | Xây dựng Test Cases dựa trên Acceptance Criteria và Traceability Matrix |
| **DevOps Engineers** | Nắm bắt yêu cầu về infrastructure, deployment, monitoring và resilience |
| **Project Managers** | Ước lượng effort, phân chia Sprint, theo dõi tiến độ dựa trên User Stories |
| **UI/UX Designers** | Hiểu các màn hình chức năng, luồng người dùng và yêu cầu giao diện |

---

## 1.2. Phạm vi sản phẩm (Product Scope)

### 1.2.1. Tên sản phẩm
**AI-Powered Multi-Channel Marketing Platform** (tên nội bộ: MKT Platform)

### 1.2.2. Mô tả tổng quan
Nền tảng Marketing đa kênh tích hợp AI tự động hóa là một giải pháp **SaaS (Software-as-a-Service)** xây dựng trên kiến trúc **Microservices**, hỗ trợ các doanh nghiệp (Tenants) thực hiện:

1. **Quản lý hộp thư tập trung (Unified Inbox):** Gom toàn bộ tin nhắn từ Facebook Messenger, Zalo OA, TikTok vào một giao diện duy nhất.
2. **Tự động hóa tương tác bằng AI Chatbot:** Sử dụng RAG (Retrieval-Augmented Generation) + LangGraph để chatbot tự động trả lời khách hàng dựa trên cơ sở tri thức riêng của từng Tenant.
3. **Tạo nội dung Marketing bằng AI:** Sinh bài viết marketing cá nhân hóa theo brand voice, tự động tối ưu cho từng nền tảng xã hội.
4. **Lập lịch đăng bài đa kênh:** Đặt lịch đăng bài tự động trên Facebook, TikTok; chuyển đổi thành Broadcast Message cho Zalo OA.
5. **Quản lý quan hệ khách hàng (CRM):** Quản lý danh bạ khách hàng đa kênh, gộp hồ sơ tự động, chấm điểm Lead scoring.
6. **Chiến dịch gửi tin nhắn hàng loạt:** Broadcast message đến các Segment khách hàng với A/B testing.
7. **Phân tích hiệu quả (Analytics):** Báo cáo hiệu suất Agent, Chatbot, chiến dịch marketing và ROI.
8. **Quản lý tài liệu và tệp tin tập trung (DMS):** Quản lý cấu trúc thư mục ảo, lưu trữ, phân quyền và kiểm soát phiên bản tệp tin (ảnh, video, catalog PDF) cho các phân hệ khác.

### 1.2.3. Giai đoạn phát triển

| Giai đoạn | Mô tả | Tenant mục tiêu |
|-----------|-------|-----------------|
| **Phase 1 (MVP)** | Phục vụ nghiệp vụ năng lượng mặt trời | Solavie (Internal Tenant) |
| **Phase 2 (SaaS)** | Mở rộng thành nền tảng SaaS đa ngành | Bán lẻ, F&B, Bất động sản, Giáo dục... |

### 1.2.4. Ranh giới hệ thống (System Boundary)

**Trong phạm vi (In Scope):**
- Tích hợp 3 kênh: Facebook Page (Messenger + Comments + Feed), Zalo Official Account (Chat + Broadcast), TikTok (Comments + Feed)
- Chatbot AI với RAG, Vision (đọc ảnh hóa đơn), MCP tools
- Content AI generation & approval workflow
- Scheduler đa múi giờ
- CRM với merge contact, lead scoring, segmentation
- Campaign broadcast & A/B testing
- Real-time Analytics & Dashboard
- Dynamic RBAC (phân quyền động)
- Multi-tenant isolation (RLS + Kafka tenant routing)
- Tenant Config Service (cấu hình tập trung hot-reload)
- Phân hệ DMS quản lý thư mục, upload file lên MinIO/S3, phân quyền và lưu lịch sử phiên bản tệp
- Phân hệ Link Shortener tự động rút gọn và tracking lượt click chuột (CTR) của chiến dịch gửi tin
- Phân hệ Media Processing tự động nén ảnh, tạo thumbnail và transcode video chuẩn API mạng xã hội
- Tiến trình Data Retention dọn dẹp dữ liệu hoạt động cũ, đóng gói và sao lưu sang cold storage định kỳ

**Ngoài phạm vi (Out of Scope):**
- Tích hợp Zalo cá nhân / Zalo Business (không có API chính thức)
- Đăng bài tự động lên Zalo OA Newsfeed (API không hỗ trợ)
- Thanh toán / Billing Service (sẽ phát triển ở Phase 2)
- Mobile native app (chỉ Web Dashboard responsive)
- Tích hợp Instagram, YouTube, LinkedIn (sẽ mở rộng sau)
- E-commerce / Order Management System
- Warehouse / Inventory Management

---

## 1.3. Thuật ngữ, Viết tắt & Định nghĩa (Definitions, Acronyms, and Abbreviations)

### 1.3.1. Thuật ngữ nghiệp vụ

| Thuật ngữ | Định nghĩa |
|-----------|-----------|
| **Tenant** | Một doanh nghiệp hoặc tổ chức đăng ký sử dụng dịch vụ của nền tảng. Mỗi Tenant có không gian dữ liệu cô lập hoàn toàn. |
| **Human Agent** | Nhân viên tư vấn / chăm sóc khách hàng thuộc Tenant, được gán quyền trả lời tin nhắn trên Dashboard. |
| **Contact** | Hồ sơ khách hàng trong CRM, có thể liên kết với nhiều kênh liên lạc (Facebook, Zalo, TikTok). |
| **Conversation** | Một phiên hội thoại giữa khách hàng và hệ thống (Bot hoặc Agent), thuộc một kênh cụ thể. |
| **Handoff** | Quy trình chuyển giao quyền kiểm soát cuộc hội thoại tự động từ Chatbot AI sang Human Agent khi bot không đủ độ tin cậy hoặc khách hàng tức giận. |
| **Escalation** | Đẩy một tác vụ, bình luận tiêu cực hoặc sự kiện cần xử lý từ hệ thống tự động lên hàng đợi duyệt của con người. |
| **Lead** | Khách hàng tiềm năng đã cung cấp thông tin liên hệ (SĐT, email) nhưng chưa chuyển đổi thành khách hàng chính thức. |
| **Lead Score** | Điểm số đánh giá mức độ tiềm năng chuyển đổi của một Contact, tính dựa trên hành vi tương tác. |
| **Segment** | Tập hợp các Contact thỏa mãn bộ lọc động (ví dụ: khách từ Facebook, tương tác trong 7 ngày). |
| **Campaign** | Chiến dịch gửi tin nhắn hàng loạt (Broadcast) đến một Segment khách hàng theo lịch trình. |
| **Brand Voice** | Phong cách ngôn ngữ đặc trưng của Tenant, được AI học từ tài liệu tri thức để sinh nội dung nhất quán. |
| **Content Versioning** | Quản lý phiên bản bài viết, cho phép so sánh và rollback về phiên bản trước. |
| **Broadcast Message** | Tin nhắn gửi hàng loạt đến nhiều người dùng Zalo OA cùng lúc (thay thế cho việc đăng bài Feed). |
| **Working Hours** | Khung giờ làm việc của Tenant, quyết định hành vi chatbot trong/ngoài giờ. |
| **Merge Contact** | Gộp nhiều hồ sơ Contact trùng lặp thành một hồ sơ duy nhất, kèm theo toàn bộ lịch sử tương tác. |
| **Deal / Sales Pipeline** | Phễu cơ hội bán hàng — các giai đoạn dẫn dắt khách hàng từ lúc tiếp cận, khảo sát đến khi ký được hợp đồng. |
| **Site Survey** | Khảo sát thực địa mái — việc kỹ thuật viên đo đạc diện tích, độ dốc mái, hướng nắng và chụp ảnh kết cấu xà gồ, tủ điện. |
| **Solar ROI & Proposal** | Đề xuất đầu tư và tính hoàn vốn — bản chào giá chứa phương án công suất lắp đặt, sản lượng điện dự kiến và dòng tiền hoàn vốn. |
| **O&M Ticket** | Vé hỗ trợ bảo trì — phiếu ghi nhận lỗi thiết bị sau bán hàng (Inverter cảnh báo lỗi, pin sụt giảm công suất) để điều phối kỹ thuật khắc phục. |

### 1.3.2. Thuật ngữ kỹ thuật

| Thuật ngữ | Định nghĩa |
|-----------|-----------|
| **Confidence Score** | Thang điểm 0.0 – 1.0 đo lường độ tin cậy của câu trả lời do AI sinh ra hoặc các quyết định phân loại. |
| **RAG** | Retrieval-Augmented Generation — kỹ thuật truy xuất thông tin từ cơ sở tri thức cục bộ để cung cấp ngữ nghĩa bổ sung cho LLM sinh câu trả lời chính xác. |
| **LangGraph** | Framework xây dựng AI Agent dạng đồ thị trạng thái (State Graph), cho phép quản lý luồng xử lý phức tạp của Chatbot. |
| **MCP** | Model Context Protocol — giao thức chuẩn hóa để LLM gọi các API/tools bên ngoài một cách có cấu trúc. |
| **ReAct** | Reasoning + Acting — mô hình AI thực hiện vòng lặp: Suy luận → Hành động → Quan sát → Lặp lại cho đến khi có kết quả. |
| **Semantic Router** | Bộ định tuyến ngữ nghĩa — mô hình phân loại văn bản siêu nhẹ dùng làm rào chắn đầu vào để lọc câu hỏi lạc đề, đối thủ hoặc jailbreak với độ trễ tối thiểu. |
| **NLI (Natural Language Inference)** | Suy luận ngôn ngữ tự nhiên — mô hình so khớp tiền đề (RAG context) và giả thuyết (câu trả lời LLM) để phân loại mức độ chứng thực (grounding), dùng làm rào chắn chống ảo giác. |
| **Prompt Caching** | Bộ đệm câu lệnh — kỹ thuật lưu trữ KV-caching của LLM cho phép bỏ qua việc tính toán lại các token tĩnh (system prompt, schemas, docs) nằm ở đầu prompt. |
| **Sliding Window Memory** | Bộ nhớ cửa sổ trượt — kỹ thuật quản lý lịch sử chat bằng cách duy trì một số lượng tin nhắn gần nhất cố định kết hợp với tóm tắt tự động của các tin nhắn cũ. |
| **RLS** | Row-Level Security — cơ chế bảo mật ở tầng database PostgreSQL, tự động lọc dữ liệu theo `tenant_id`. |
| **Saga Pattern** | Mô hình quản lý giao dịch phân tán trong kiến trúc microservices bằng chuỗi sự kiện bù trừ (compensating events). |
| **Circuit Breaker** | Mô hình ngắt mạch, tự động dừng gọi service lỗi liên tục để tránh hiệu ứng domino (cascading failure). |
| **Hot Reload** | Cập nhật cấu hình hệ thống mà không cần khởi động lại dịch vụ, thông qua Redis Pub/Sub. |
| **Webhook** | Cơ chế callback HTTP do bên thứ ba (Facebook, Zalo, TikTok) gửi khi có sự kiện mới (tin nhắn, bình luận). |
| **Idempotency** | Tính bất biến khi thực hiện cùng một thao tác nhiều lần — đảm bảo không tạo dữ liệu trùng lặp. |
| **Vector Embedding** | Biểu diễn văn bản dưới dạng vector số trong không gian nhiều chiều, phục vụ tìm kiếm ngữ nghĩa (semantic search). |
| **Semantic Chunking** | Chia nhỏ tài liệu dựa trên ngữ nghĩa câu (không cắt ngang câu) để tạo các đoạn văn bản phù hợp cho RAG. |
| **Reranking** | Sắp xếp lại kết quả tìm kiếm bằng mô hình AI chuyên dụng để chọn ra các kết quả chính xác nhất. |
| **Token Bucket** | Thuật toán giới hạn tần suất (rate limiting) dựa trên "thùng chứa token" với tốc độ nạp cố định. |
| **Canary Deployment** | Chiến lược triển khai phiên bản mới cho một tỷ lệ nhỏ traffic trước khi mở rộng toàn bộ. |
| **Presigned URL** | URL tạm thời có chữ ký xác thực, cho phép truy cập trực tiếp file trên MinIO/S3 trong thời gian giới hạn. |
| **CTR (Click-Through Rate)** | Tỷ lệ nhấp chuột — Tỷ lệ phần trăm số lượt nhấp chuột trên tổng số lượt hiển thị/gửi của một liên kết. |
| **Transcoding** | Quá trình chuyển mã — Giải nén, xử lý (thay đổi độ phân giải/bitrate) và nén lại tệp tin media để đạt định dạng tối ưu. |
| **Cold Storage** | Lưu trữ lạnh — Lưu trữ dữ liệu lịch sử ít khi truy cập (như logs nén dạng Parquet) trên đối tượng lưu trữ S3 nhằm tối ưu hóa chi phí. |

### 1.3.3. Viết tắt (Acronyms)

| Viết tắt | Đầy đủ |
|----------|--------|
| API | Application Programming Interface |
| BRD | Business Requirements Document |
| CRUD | Create, Read, Update, Delete |
| CRM | Customer Relationship Management |
| CTR | Click-Through Rate |
| DMS | Document Management System |
| DFD | Data Flow Diagram |
| ERD | Entity-Relationship Diagram |
| FFmpeg | Fast Forward MPEG (Thư viện xử lý multimedia đa nền tảng) |
| FR | Functional Requirement |
| gRPC | Google Remote Procedure Call |
| JWT | JSON Web Token |
| LLM | Large Language Model |
| NFR | Non-Functional Requirement |
| OA | Official Account (Zalo) |
| OCR | Optical Character Recognition |
| OIDC | OpenID Connect |
| RBAC | Role-Based Access Control |
| REST | Representational State Transfer |
| RLS | Row-Level Security |
| RTM | Requirements Traceability Matrix |
| SaaS | Software as a Service |
| SRS | Software Requirements Specification |
| SSL/TLS | Secure Sockets Layer / Transport Layer Security |
| TTL | Time To Live |
| UC | Use Case |
| US | User Story |
| WSS | WebSocket Secure |

---

## 1.4. Tài liệu tham chiếu (References)

### 1.4.1. Tài liệu dự án nội bộ

| # | Tài liệu | Phiên bản | Mô tả |
|---|----------|-----------|-------|
| REF-01 | [Business Requirements Document (BRD)](../BRD.md) | 1.0 | Yêu cầu nghiệp vụ, quy trình kinh doanh, Config-Driven Architecture |
| REF-02 | [BA Interview Notes](../BA_Interview_Questions.md) | 1.0 | Ghi chép phỏng vấn nghiệp vụ với stakeholders |
| REF-03 | [SRS Legacy v0.5](../SRS.md) | 0.5 | Phiên bản SRS sơ bộ (kiến trúc tổng quan) |

### 1.4.2. Chuẩn quốc tế & Tham khảo kỹ thuật

| # | Tài liệu | Nguồn |
|---|----------|-------|
| REF-04 | IEEE Std 830-1998: Recommended Practice for Software Requirements Specifications | IEEE |
| REF-05 | ISO/IEC/IEEE 29148:2018: Systems and software engineering — Life cycle processes — Requirements engineering | ISO/IEC/IEEE |
| REF-06 | ISO/IEC 25010:2011: Systems and software quality models (SQuaRE) | ISO/IEC |
| REF-07 | RFC 2119: Key words for use in RFCs to Indicate Requirement Levels | IETF |
| REF-08 | OWASP Top 10 - 2021: Web Application Security Risks | OWASP Foundation |
| REF-09 | Facebook Graph API v18.0 Documentation | Meta for Developers |
| REF-10 | Zalo OA API v3 Documentation | Zalo Developers |
| REF-11 | TikTok API for Business Documentation | TikTok for Developers |
| REF-12 | OpenAI API Reference | OpenAI |
| REF-13 | Anthropic Claude API Reference | Anthropic |

---

## 1.5. Tổng quan tài liệu (Overview)

Tài liệu SRS này được tổ chức thành **12 phần** theo chuẩn IEEE 830 kết hợp ISO/IEC/IEEE 29148, mỗi phần được lưu trữ trong một file riêng biệt để dễ dàng quản lý và bảo trì:

| Phần | Nội dung | Đối tượng chính |
|------|---------|-----------------|
| **01 - Introduction** (file này) | Mục tiêu, phạm vi, thuật ngữ, tham chiếu | Tất cả |
| **02 - Overall Description** | Bối cảnh, người dùng, ràng buộc, giả định | PM, Architect, BA |
| **03 - Use Cases** | 29 Use Cases chi tiết với Flow đầy đủ | BA, Dev, QA |
| **04 - User Stories** | 60+ User Stories + Acceptance Criteria | Dev, QA, PM |
| **05 - Functional Requirements** | 130+ yêu cầu chức năng có mã FR-xxx | Dev, Architect |
| **06 - Non-Functional Requirements** | Performance, Security, Reliability, Scalability | Architect, DevOps, QA |
| **07 - External Interfaces** | UI, API contracts, Communication protocols | Dev, UI/UX, QA |
| **08 - Data Models** | ERD, Schema, Data Dictionary | Dev, DBA |
| **09 - System Architecture** | Microservices, Deployment, Communication | Architect, DevOps |
| **10 - Standards & Resilience** | AI Confidence Scale, Saga, Error handling, Risks | Architect, Dev, PM |
| **11 - Traceability Matrix** | Ma trận truy vết FR → UC → US → Test Case | QA, PM, BA |
| **12 - Appendices** | Glossary mở rộng, Sign-off, Change Request | Tất cả |

---

*← [Về Mục lục](./00_SRS_Index.md) | [Tiếp: Overall Description →](./02_Overall_Description.md)*
