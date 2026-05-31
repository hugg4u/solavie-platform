# 4. USER STORIES & ACCEPTANCE CRITERIA

> User Stories được viết theo format Agile chuẩn. Acceptance Criteria sử dụng format Given-When-Then (Gherkin). Mỗi User Story liên kết ngược tới Use Case (UC) và Functional Requirement (FR) tương ứng.

---

## 4.1. Epic 1: Identity & Access Management

### US-001: Đăng nhập Dashboard
**As a** Agent/Manager/Admin,
**I want to** đăng nhập bằng email và mật khẩu,
**So that** tôi có thể truy cập Dashboard với đúng quyền hạn của mình.

**Acceptance Criteria:**
- **Given** tài khoản Agent đã được Admin tạo, **When** Agent nhập đúng email + password, **Then** hệ thống redirect tới Unified Inbox với menu tương ứng Role.
- **Given** Agent nhập sai password 5 lần, **When** Agent thử lần thứ 6, **Then** tài khoản bị khóa 15 phút.
- **Given** JWT token hết hạn nhưng Refresh Token còn hợp lệ, **When** Agent thực hiện thao tác, **Then** hệ thống tự động refresh token ngầm.

**Priority:** 🔴 Must Have | **Story Points:** 5
**Liên kết:** UC-01, FR-AUTH-001, FR-AUTH-002

---

### US-002: Tự động đăng xuất khi rảnh
**As a** Tenant Admin,
**I want to** hệ thống tự động đăng xuất nhân viên sau thời gian không hoạt động,
**So that** tránh truy cập trái phép khi nhân viên rời máy tính.

**Acceptance Criteria:**
- **Given** config `session_timeout_minutes = 30`, **When** Agent không có tương tác trong 30 phút, **Then** hệ thống đăng xuất và redirect về trang login.
- **Given** Agent đang trong phiên chat active, **When** 30 phút trôi qua, **Then** session timeout KHÔNG kích hoạt (activity = chat).

**Priority:** 🟡 Should Have | **Story Points:** 3
**Liên kết:** UC-01, FR-AUTH-003

---

### US-003: Tạo vai trò mới
**As a** Tenant Admin,
**I want to** tạo vai trò tùy chỉnh và gán quyền hạn cụ thể,
**So that** tôi có thể phân quyền linh hoạt theo cơ cấu tổ chức doanh nghiệp.

**Acceptance Criteria:**
- **Given** Admin ở trang Quản lý phân quyền, **When** tạo Role "Trưởng nhóm KD" với quyền `inbox:read`, `inbox:chat`, `contacts:view`, **Then** Role được lưu và hiển thị trong danh sách.
- **Given** tên Role đã tồn tại, **When** Admin tạo Role trùng tên, **Then** hiển thị lỗi "Tên vai trò đã tồn tại".

**Priority:** 🔴 Must Have | **Story Points:** 8
**Liên kết:** UC-02, FR-AUTH-004, FR-AUTH-005

---

### US-004: Thay đổi quyền có hiệu lực ngay
**As a** Tenant Admin,
**I want to** khi tôi thay đổi permissions của một Role, tất cả user thuộc Role đó nhận quyền mới ngay lập tức,
**So that** tôi không cần yêu cầu nhân viên đăng nhập lại.

**Acceptance Criteria:**
- **Given** Admin thay đổi quyền Role "Agent", **When** lưu thay đổi, **Then** Redis cache được invalidate, Agent đang online thấy menu cập nhật trong < 1 phút.

**Priority:** 🔴 Must Have | **Story Points:** 5
**Liên kết:** UC-02, FR-AUTH-006

---

### US-005: Onboard Tenant mới
**As a** Super Admin,
**I want to** tạo Tenant mới với 1 click,
**So that** Tenant có thể bắt đầu sử dụng hệ thống ngay sau khi nhận email chào mừng.

**Acceptance Criteria:**
- **Given** Super Admin nhập tên công ty + email admin + gói dịch vụ, **When** nhấn "Tạo", **Then** hệ thống tạo Realm Keycloak, Admin account, default config, và gửi email activation.
- **Given** email admin đã tồn tại, **When** tạo Tenant, **Then** hiển thị lỗi "Email đã được sử dụng".

**Priority:** 🔴 Must Have | **Story Points:** 13
**Liên kết:** UC-03, FR-AUTH-007, FR-AUTH-008

---

## 4.2. Epic 2: Channel Management

### US-006: Kết nối Facebook Page
**As a** Tenant Admin,
**I want to** kết nối Facebook Page vào hệ thống qua OAuth,
**So that** hệ thống có thể nhận và gửi tin nhắn trên Facebook Messenger.

**Acceptance Criteria:**
- **Given** Admin ở trang Quản lý kênh, **When** nhấn "Kết nối Facebook" và hoàn tất OAuth, **Then** Page hiển thị trạng thái `Active` với webhook đã đăng ký.
- **Given** Admin hủy OAuth dialog, **When** redirect về hệ thống, **Then** hiển thị thông báo "Đã hủy kết nối".
- **Given** Page đã kết nối, **When** Admin nhấn "Ngắt kết nối", **Then** token bị revoke, webhook bị hủy, trạng thái → `Disconnected`.

**Priority:** 🔴 Must Have | **Story Points:** 8
**Liên kết:** UC-04, FR-CH-001, FR-CH-002

---

### US-007: Kết nối Zalo OA
**As a** Tenant Admin,
**I want to** kết nối Zalo Official Account vào hệ thống,
**So that** hệ thống có thể nhận tin nhắn Zalo và gửi Broadcast.

**Acceptance Criteria:**
- **Given** Admin có quyền quản trị Zalo OA, **When** hoàn tất OAuth Zalo, **Then** OA hiển thị trạng thái `Active`.
- **Given** OA đã kết nối, **When** Admin kiểm tra, **Then** hiển thị thông tin OA: tên, số follower, trạng thái webhook.

**Priority:** 🔴 Must Have | **Story Points:** 8
**Liên kết:** UC-04, FR-CH-003

---

### US-008: Token tự động refresh
**As a** Tenant Admin,
**I want to** hệ thống tự động làm mới token kênh MXH trước khi hết hạn,
**So that** tôi không phải kết nối lại thủ công mỗi khi token hết hạn.

**Acceptance Criteria:**
- **Given** token sẽ hết hạn trong 24h, **When** background job chạy, **Then** token được refresh tự động, mã hóa AES-256 và lưu DB.
- **Given** refresh token bị revoke (user đổi mật khẩu Facebook), **When** job chạy, **Then** trạng thái kênh → `Token Expired`, gửi notification khẩn cấp cho Admin.

**Priority:** 🔴 Must Have | **Story Points:** 5
**Liên kết:** UC-05, FR-CH-004, FR-CH-005

---

## 4.3. Epic 3: Messaging & Inbox

### US-009: Xem tất cả conversations trên 1 màn hình
**As a** Agent,
**I want to** xem tất cả cuộc hội thoại từ mọi kênh (Facebook, Zalo, TikTok) trên một màn hình duy nhất,
**So that** tôi không cần chuyển đổi giữa nhiều ứng dụng.

**Acceptance Criteria:**
- **Given** Agent mở Unified Inbox, **When** trang load, **Then** hiển thị danh sách conversations từ tất cả kênh, sắp xếp theo tin nhắn mới nhất.
- **Given** có conversations từ 3 kênh, **When** hiển thị, **Then** mỗi conversation có icon/tag kênh nguồn [Facebook]/[Zalo]/[TikTok].

**Priority:** 🔴 Must Have | **Story Points:** 8
**Liên kết:** UC-06, FR-MSG-001

---

### US-010: Lọc conversations theo kênh
**As a** Agent,
**I want to** lọc danh sách conversations theo kênh (Facebook only, Zalo only),
**So that** tôi có thể tập trung xử lý tin nhắn từ kênh cụ thể.

**Acceptance Criteria:**
- **Given** Agent ở Inbox, **When** chọn filter "Facebook", **Then** chỉ hiển thị conversations từ Facebook Messenger.
- **Given** Agent ở Inbox, **When** chọn filter "Chưa gán", **Then** chỉ hiển thị conversations trong hàng đợi chưa có Agent.

**Priority:** 🔴 Must Have | **Story Points:** 3
**Liên kết:** UC-06, FR-MSG-002

---

### US-011: Nhận tin nhắn realtime
**As a** Agent,
**I want to** nhận tin nhắn mới ngay lập tức khi khách hàng gửi,
**So that** tôi có thể phản hồi nhanh nhất có thể.

**Acceptance Criteria:**
- **Given** Agent đang mở Inbox, **When** khách gửi tin nhắn mới, **Then** tin nhắn hiện ngay (< 1 giây) qua WebSocket + badge count cập nhật + âm thanh thông báo (nếu config bật).

**Priority:** 🔴 Must Have | **Story Points:** 5
**Liên kết:** UC-06, FR-MSG-003

---

### US-012: Gửi tin nhắn reply
**As a** Agent,
**I want to** gõ và gửi tin nhắn phản hồi khách hàng ngay trên Dashboard,
**So that** khách hàng nhận được trả lời trên đúng kênh MXH họ đang dùng.

**Acceptance Criteria:**
- **Given** conversation từ Facebook đang ở Manual mode, **When** Agent gõ tin và nhấn Enter, **Then** tin nhắn được gửi qua Facebook Messenger API, hiển thị checkmark delivered.
- **Given** tin nhắn gửi thất bại (API lỗi), **When** retry 3 lần vẫn lỗi, **Then** đánh dấu `Failed` + hiện nút "Gửi lại".

**Priority:** 🔴 Must Have | **Story Points:** 5
**Liên kết:** UC-07, FR-MSG-004, FR-MSG-005

---

### US-013: Cảnh báo ngoài khung 24h Facebook
**As a** Agent,
**I want to** được cảnh báo khi conversation Facebook ngoài khung 24h,
**So that** tôi biết cần dùng Message Tags hoặc tin nhắn có phí.

**Acceptance Criteria:**
- **Given** conversation Facebook, tin nhắn cuối của khách > 24h trước, **When** Agent mở conversation, **Then** ô nhập tin bị khóa, hiển thị cảnh báo + dropdown chọn Message Tag.

**Priority:** 🟡 Should Have | **Story Points:** 5
**Liên kết:** UC-07, FR-MSG-006

---

### US-014: Chatbot tự động handoff khi không chắc chắn
**As a** Customer,
**I want to** được chuyển cho nhân viên thật khi chatbot không trả lời được,
**So that** tôi không bị stuck với bot vô ích.

**Acceptance Criteria:**
- **Given** Chatbot confidence < 0.70, **When** chatbot xử lý tin nhắn, **Then** chuyển conversation sang Manual mode + gửi tin "Vui lòng chờ, nhân viên sẽ hỗ trợ bạn" + notify Agent.

**Priority:** 🔴 Must Have | **Story Points:** 8
**Liên kết:** UC-08, FR-MSG-007, FR-CB-004

---

### US-015: Handoff khi khách giận dữ
**As a** Tenant Admin,
**I want to** chatbot tự động chuyển nhân viên khi phát hiện khách hàng đang tức giận,
**So that** tránh chatbot làm tình hình tệ hơn.

**Acceptance Criteria:**
- **Given** config `auto_handoff_on_negative = true`, **When** sentiment analysis = angry (score ≥ 0.60), **Then** kích hoạt handoff ngay lập tức bất kể confidence score.

**Priority:** 🔴 Must Have | **Story Points:** 5
**Liên kết:** UC-08, FR-MSG-008

---

### US-016: Phân phối Agent theo Hybrid Routing
**As a** Manager,
**I want to** hệ thống tự động phân phối cuộc chat cho Agent phù hợp nhất,
**So that** khách hàng được hỗ trợ nhanh và có trải nghiệm liền mạch.

**Acceptance Criteria:**
- **Given** khách hàng cũ gửi tin, Agent cũ online & có tải < 5 conversations, **When** handoff xảy ra, **Then** gán cho Agent cũ.
- **Given** Agent cũ offline, **When** handoff xảy ra, **Then** đưa vào Queue & Claim 3 phút, nếu không ai nhận → gán Least Busy.

**Priority:** 🟡 Should Have | **Story Points:** 8
**Liên kết:** UC-08, FR-MSG-009

---

### US-017: Chuyển ngược về Bot sau khi Agent hoàn tất
**As a** Agent,
**I want to** nhấn "Đóng hội thoại" để trả conversation lại cho Bot,
**So that** chatbot tiếp tục tự động chăm sóc nếu khách nhắn lại.

**Acceptance Criteria:**
- **Given** conversation đang Manual, **When** Agent nhấn "Đóng", **Then** trạng thái → Auto, Bot tiếp quản.
- **Given** config `manual_to_auto_trigger = timeout`, timeout = 2h, **When** 2h không có tin nhắn, **Then** tự động chuyển về Auto.

**Priority:** 🟡 Should Have | **Story Points:** 5
**Liên kết:** UC-09, FR-MSG-010, FR-MSG-011

---

## 4.4. Epic 4: AI Chatbot

### US-018: Chatbot trả lời dựa trên tri thức
**As a** Customer,
**I want to** chatbot trả lời chính xác dựa trên thông tin sản phẩm/dịch vụ của công ty,
**So that** tôi nhận được câu trả lời hữu ích thay vì câu trả lời chung chung.

**Acceptance Criteria:**
- **Given** Knowledge Base có tài liệu sản phẩm, **When** khách hỏi "Giá điện mặt trời 5kWp?", **Then** chatbot tìm RAG → sinh câu trả lời dựa trên tài liệu thực tế trong < 3 giây.

**Priority:** 🔴 Must Have | **Story Points:** 13
**Liên kết:** UC-10, FR-CB-001, FR-CB-002

---

### US-019: Chatbot duy trì ngữ cảnh chat
**As a** Customer,
**I want to** chatbot nhớ những gì tôi đã nói trước đó trong cuộc hội thoại,
**So that** tôi không phải lặp lại thông tin.

**Acceptance Criteria:**
- **Given** khách đã nói "Tôi muốn lắp cho hộ gia đình ở Quận 7", **When** khách hỏi tiếp "Chi phí bao nhiêu?", **Then** chatbot trả lời kèm ngữ cảnh "hộ gia đình, Quận 7" mà không hỏi lại.

**Priority:** 🔴 Must Have | **Story Points:** 8
**Liên kết:** UC-10, FR-CB-003

---

### US-020: Đọc hóa đơn bằng AI Vision
**As a** Customer (Solavie),
**I want to** gửi ảnh hóa đơn tiền điện và chatbot tự động đọc được số liệu,
**So that** tôi không cần gõ lại thông tin thủ công.

**Acceptance Criteria:**
- **Given** config `ai_vision_invoice_reading = true`, **When** khách gửi ảnh hóa đơn, **Then** chatbot trích xuất kWh + số tiền, hỏi xác nhận, cập nhật CRM.
- **Given** ảnh mờ/không phải hóa đơn, **When** AI không đọc được, **Then** chatbot hỏi chụp lại hoặc handoff.

**Priority:** 🟡 Should Have | **Story Points:** 8
**Liên kết:** UC-11, FR-CB-005, FR-CB-006

---

### US-021: Tắt AI Vision cho ngành không cần
**As a** Tenant Admin (ngành Bán lẻ),
**I want to** tắt tính năng đọc hóa đơn điện,
**So that** chatbot không cố phân tích ảnh sản phẩm khách gửi nhầm.

**Acceptance Criteria:**
- **Given** config `ai_vision_invoice_reading = false`, **When** khách gửi ảnh, **Then** chatbot bỏ qua phân tích → kích hoạt Handoff.

**Priority:** 🟡 Should Have | **Story Points:** 2
**Liên kết:** UC-11, FR-CB-006

---

### US-022: Lead Capture ngoài giờ
**As a** Tenant Admin,
**I want to** chatbot thu thập thông tin khách hàng khi ngoài giờ làm việc,
**So that** không bỏ sót lead tiềm năng.

**Acceptance Criteria:**
- **Given** ngoài working_hours + config = lead_capture, **When** khách nhắn tin, **Then** chatbot chạy script: Chào → Hỏi SĐT → Hỏi địa chỉ → Hỏi nhu cầu → Lưu CRM + tag "Ngoài giờ" → Khóa chat.
- **Given** khách nhập SĐT sai format, **When** chatbot validate, **Then** hỏi lại cụ thể.

**Priority:** 🟡 Should Have | **Story Points:** 8
**Liên kết:** UC-12, FR-CB-007, FR-CB-008

---

## 4.5. Epic 5: Knowledge Base

### US-023: Upload tài liệu PDF
**As a** Admin/Content Creator,
**I want to** upload file PDF/DOCX vào Knowledge Base,
**So that** chatbot có dữ liệu để trả lời khách hàng chính xác.

**Acceptance Criteria:**
- **Given** file PDF hợp lệ < 50MB, **When** upload, **Then** file được chunked, embedded, trạng thái `Ready` trong < 5 phút.
- **Given** file không đúng format, **When** upload, **Then** hiển thị lỗi "Chỉ hỗ trợ PDF, DOCX, TXT, MD".

**Priority:** 🔴 Must Have | **Story Points:** 8
**Liên kết:** UC-13, FR-KB-001, FR-KB-002, FR-KB-003

---

### US-024: Tìm kiếm Hybrid (Dense + Sparse)
**As a** Chatbot Service,
**I want to** tìm kiếm tài liệu bằng kết hợp Dense Search + BM25 + Reranking,
**So that** kết quả tìm kiếm chính xác nhất có thể.

**Acceptance Criteria:**
- **Given** câu hỏi từ khách, **When** search, **Then** trả về top-5 chunks với Relevance Score, latency < 500ms.

**Priority:** 🔴 Must Have | **Story Points:** 13
**Liên kết:** UC-14, FR-KB-004, FR-KB-005

---

## 4.6. Epic 6: Content & Scheduler

### US-025: Tạo bài viết bằng AI
**As a** Content Creator,
**I want to** nhập chủ đề và AI tự động sinh bài viết cho nhiều nền tảng,
**So that** tôi tiết kiệm thời gian viết content.

**Acceptance Criteria:**
- **Given** Creator nhập chủ đề + chọn 3 kênh, **When** nhấn "Tạo bằng AI", **Then** AI sinh 3 phiên bản bài viết (Facebook: dài/emoji, TikTok: ngắn/trend, Zalo: trang trọng) trong < 15 giây.

**Priority:** 🔴 Must Have | **Story Points:** 13
**Liên kết:** UC-15, FR-CNT-001, FR-CNT-002

---

### US-026: Quality Check nội dung
**As a** Content Creator,
**I want to** hệ thống tự động kiểm tra chất lượng bài viết AI,
**So that** tôi không đăng bài có lỗi chính tả hoặc từ cấm.

**Acceptance Criteria:**
- **Given** AI sinh bài viết, **When** Quality Check chạy, **Then** hiển thị Quality Score + danh sách issues (nếu có).
- **Given** Quality Score < 0.70, **When** hiển thị, **Then** cảnh báo "Cần chỉnh sửa" + highlight vấn đề.

**Priority:** 🟡 Should Have | **Story Points:** 5
**Liên kết:** UC-15, FR-CNT-003, FR-CNT-004

---

### US-027: Phê duyệt bài viết
**As a** Manager,
**I want to** xem preview và phê duyệt bài viết trước khi đăng,
**So that** đảm bảo chất lượng nội dung đại diện cho thương hiệu.

**Acceptance Criteria:**
- **Given** config `require_content_approval = true`, **When** Creator gửi duyệt, **Then** Manager thấy bài trong "Chờ duyệt" + nhấn Approve/Reject.
- **Given** Manager reject, **When** nhập lý do, **Then** Creator nhận notification + trạng thái `Rejected`.

**Priority:** 🟡 Should Have | **Story Points:** 5
**Liên kết:** UC-16, FR-CNT-005, FR-CNT-006

---

### US-028: Auto-approve bài chất lượng cao
**As a** Tenant Admin,
**I want to** tự động duyệt bài viết có Quality Score cao,
**So that** giảm bớt công việc duyệt thủ công cho Manager.

**Acceptance Criteria:**
- **Given** config `require_content_approval = false` + `auto_approve_quality_threshold = 0.85`, **When** bài viết có score ≥ 0.85, **Then** tự động `Approved`, bỏ qua Manager.

**Priority:** 🟢 Could Have | **Story Points:** 3
**Liên kết:** UC-16, FR-CNT-006

---

### US-029: Đặt lịch đăng bài
**As a** Content Creator,
**I want to** đặt lịch đăng bài viết vào thời điểm tối ưu,
**So that** bài viết tiếp cận nhiều khách hàng nhất.

**Acceptance Criteria:**
- **Given** bài viết `Approved` + chọn ngày/giờ/múi giờ, **When** nhấn "Lên lịch", **Then** Quartz Job được tạo, bài hiển thị trên Calendar.
- **Given** đến giờ đăng, kênh Facebook, **When** Quartz trigger, **Then** bài được đăng lên Facebook Feed.
- **Given** đến giờ đăng, kênh Zalo OA, **When** Quartz trigger, **Then** bài chuyển thành Broadcast Message gửi đến followers.

**Priority:** 🔴 Must Have | **Story Points:** 8
**Liên kết:** UC-17, FR-SCH-001, FR-SCH-002, FR-SCH-003

---

### US-030: Retry đăng bài khi lỗi
**As a** Content Creator,
**I want to** hệ thống tự động thử đăng lại bài khi API lỗi,
**So that** tôi không cần theo dõi từng bài viết.

**Acceptance Criteria:**
- **Given** API đăng bài lỗi, **When** retry 3 lần vẫn thất bại, **Then** trạng thái → `Draft_Failed`, notification cho Creator.

**Priority:** 🔴 Must Have | **Story Points:** 3
**Liên kết:** UC-17, FR-SCH-004

---

### US-031: Kéo thả bài viết trên Calendar
**As a** Content Creator,
**I want to** kéo thả bài viết trên Calendar View để đổi thời gian đăng,
**So that** tôi dễ dàng điều chỉnh lịch đăng bằng thao tác trực quan.

**Acceptance Criteria:**
- **Given** bài viết `Scheduled` trên Calendar, **When** Creator kéo thả sang slot khác, **Then** Quartz Job được cập nhật thời gian mới.

**Priority:** 🟡 Should Have | **Story Points:** 5
**Liên kết:** UC-18, FR-SCH-005, FR-SCH-006

---

## 4.7. Epic 7: CRM & Contact Management

### US-032: Xem hồ sơ khách hàng 360°
**As a** Agent,
**I want to** xem toàn bộ thông tin khách hàng (tên, SĐT, kênh, lịch sử chat) trên 1 màn hình,
**So that** tôi hiểu rõ khách hàng trước khi trả lời.

**Acceptance Criteria:**
- **Given** Agent mở contact, **When** trang load, **Then** hiển thị: thông tin cá nhân, danh sách kênh liên kết, unified timeline (tất cả tin nhắn từ mọi kênh với tag [Facebook]/[Zalo]), Lead Score, Segment tags.

**Priority:** 🔴 Must Have | **Story Points:** 8
**Liên kết:** UC-19, FR-CRM-001, FR-CRM-002

---

### US-033: Data Masking cho Agent
**As a** Tenant Admin,
**I want to** ẩn SĐT/Email khách hàng đối với nhân viên Agent không có quyền,
**So that** bảo vệ dữ liệu cá nhân khách hàng.

**Acceptance Criteria:**
- **Given** config `data_masking_enabled = true` + Agent không có quyền `contacts:mask_data`, **When** Agent xem contact, **Then** SĐT hiện `091****678`, Email hiện `n***@gmail.com`.

**Priority:** 🟡 Should Have | **Story Points:** 3
**Liên kết:** UC-19, FR-CRM-003

---

### US-034: Tự động gộp contact trùng SĐT + tên
**As a** CRM Service,
**I want to** tự động gộp contacts khi trùng SĐT + tên giống nhau,
**So that** Agent có cái nhìn đầy đủ về 1 khách hàng thay vì nhiều hồ sơ rời rạc.

**Acceptance Criteria:**
- **Given** Contact A (Facebook, SĐT 0912345678, tên "Nam Nguyen") + Contact B (Zalo, SĐT 0912345678, tên "Nam Nguyễn"), **When** SĐT cập nhật, **Then** auto-merge → 1 contact duy nhất + toàn bộ lịch sử chat gộp lại với tag kênh nguồn.

**Priority:** 🔴 Must Have | **Story Points:** 13
**Liên kết:** UC-20, FR-CRM-004, FR-CRM-005

---

### US-035: Gợi ý merge cho trường hợp không chắc chắn
**As a** Agent,
**I want to** nhận gợi ý merge khi hệ thống tìm thấy contacts khả nghi trùng lặp,
**So that** tôi có thể xác nhận thủ công tránh gộp nhầm.

**Acceptance Criteria:**
- **Given** Contact A SĐT trùng Contact B nhưng tên khác biệt hoàn toàn, **When** CRM phát hiện, **Then** tạo MergeSuggestion hiển thị trên Dashboard Agent với bảng so sánh 2 contacts → Agent nhấn "Merge" hoặc "Bỏ qua".

**Priority:** 🔴 Must Have | **Story Points:** 8
**Liên kết:** UC-20, FR-CRM-006, FR-CRM-007

---

## 4.8. Epic 8: Campaign

### US-036: Tạo chiến dịch broadcast
**As a** Manager,
**I want to** tạo chiến dịch gửi tin nhắn hàng loạt đến nhóm khách hàng,
**So that** tiếp cận khách hàng với thông tin ưu đãi/khuyến mãi.

**Acceptance Criteria:**
- **Given** Manager chọn Segment + soạn nội dung + lịch gửi, **When** nhấn "Khởi chạy", **Then** tin nhắn được gửi với tốc độ `campaign_sending_rate` msg/phút.
- **Given** API rate limit bị hit, **When** gửi đang chạy, **Then** tự động pause, chờ `Retry-After`, resume.

**Priority:** 🟡 Should Have | **Story Points:** 13
**Liên kết:** UC-21, FR-CAM-001, FR-CAM-002, FR-CAM-003

---

### US-037: Xử lý Facebook ngoài 24h trong Campaign
**As a** Manager,
**I want to** cấu hình hành vi khi gửi Campaign cho contacts Facebook ngoài 24h,
**So that** chiến dịch không bị lỗi hàng loạt.

**Acceptance Criteria:**
- **Given** config `campaign_fb_outside_24h_action = skip`, **When** contact ngoài 24h, **Then** bỏ qua contact đó, ghi log.
- **Given** config `campaign_fb_outside_24h_action = use_tag`, **When** contact ngoài 24h, **Then** gửi qua Message Tag cho phép.

**Priority:** 🟡 Should Have | **Story Points:** 5
**Liên kết:** UC-21, FR-CAM-003

---

### US-038: A/B Testing
**As a** Manager,
**I want to** thử nghiệm 2 phiên bản nội dung trước khi gửi hàng loạt,
**So that** chọn được nội dung hiệu quả nhất.

**Acceptance Criteria:**
- **Given** Campaign với A/B Testing bật, 10% mẫu, **When** chạy, **Then** 10% nhận A, 10% nhận B, sau X giờ hiển thị report so sánh → Manager chọn winner → gửi cho 80% còn lại.

**Priority:** 🟢 Could Have | **Story Points:** 13
**Liên kết:** UC-22, FR-CAM-004, FR-CAM-005

---

## 4.9. Epic 9: Analytics

### US-039: Dashboard tổng quan
**As a** Manager,
**I want to** xem dashboard tổng quan hiệu suất,
**So that** tôi nắm được tình hình hoạt động marketing và CSKH.

**Acceptance Criteria:**
- **Given** Manager mở Analytics, **When** trang load, **Then** hiển thị: Tổng conversations (theo kênh), Tỷ lệ bot/agent, Thời gian phản hồi TB, Lead conversion rate.
- **Given** chọn range "30 ngày", **When** filter, **Then** dữ liệu cập nhật theo khoảng thời gian.

**Priority:** 🟡 Should Have | **Story Points:** 13
**Liên kết:** UC-23, FR-ANL-001, FR-ANL-002

---

### US-040: Xuất báo cáo
**As a** Manager,
**I want to** xuất báo cáo dạng CSV/PDF,
**So that** tôi chia sẻ số liệu cho ban lãnh đạo.

**Acceptance Criteria:**
- **Given** Manager ở trang Analytics, **When** nhấn "Xuất CSV", **Then** download file CSV chứa dữ liệu theo filter đã chọn.

**Priority:** 🟢 Could Have | **Story Points:** 5
**Liên kết:** UC-23, FR-ANL-003

---

## 4.10. Epic 10: Tenant Configuration

### US-041: Cấu hình Chatbot
**As a** Tenant Admin,
**I want to** cấu hình các thông số chatbot (confidence threshold, system prompt, AI model...),
**So that** chatbot hoạt động phù hợp với nghiệp vụ doanh nghiệp tôi.

**Acceptance Criteria:**
- **Given** Admin mở Cấu hình → tab "AI & Tri thức", **When** thay đổi `confidence_threshold` từ 0.70 → 0.80, **Then** lưu thành công, chatbot áp dụng ngưỡng mới ngay lập tức (hot reload < 5 giây).

**Priority:** 🔴 Must Have | **Story Points:** 8
**Liên kết:** UC-24, FR-CFG-001, FR-CFG-002

---

### US-042: Config validation
**As a** Tenant Admin,
**I want to** hệ thống kiểm tra giá trị cấu hình trước khi lưu,
**So that** tôi không nhập sai gây lỗi hệ thống.

**Acceptance Criteria:**
- **Given** Admin nhập confidence_threshold = 2.0 (ngoài range 0-1), **When** nhấn Lưu, **Then** hiển thị lỗi "Giá trị phải từ 0.60 đến 0.95".

**Priority:** 🔴 Must Have | **Story Points:** 3
**Liên kết:** UC-24, FR-CFG-003, FR-CFG-004

---

## 4.11. Epic 11: Comment Management

### US-043: Tự động ẩn spam
**As a** Tenant Admin,
**I want to** hệ thống tự động ẩn bình luận spam trên bài viết,
**So that** fanpage/page luôn sạch sẽ chuyên nghiệp.

**Acceptance Criteria:**
- **Given** bình luận mới trên Facebook, **When** AI phân tích Spam Score ≥ 0.85, **Then** tự động ẩn bình luận + ghi audit log.

**Priority:** 🟡 Should Have | **Story Points:** 5
**Liên kết:** UC-25, FR-CMT-001, FR-CMT-002

---

### US-044: Escalate bình luận tiêu cực
**As a** Agent,
**I want to** nhận thông báo khi có bình luận tiêu cực trên bài viết,
**So that** tôi xử lý kịp thời tránh khủng hoảng truyền thông.

**Acceptance Criteria:**
- **Given** bình luận có Negative Sentiment ≥ 0.60, **When** AI phân tích, **Then** gửi notification cho Agent + đẩy lên hàng đợi "Bình luận cần xử lý".

**Priority:** 🟡 Should Have | **Story Points:** 5
**Liên kết:** UC-25, FR-CMT-003, FR-CMT-004

---

## 4.12. Epic 12: Document Management System (DMS)

### US-045: Tải tệp lên DMS
**As a** Content Creator/Agent,
**I want to** tải các tệp tin (hình ảnh, video, tài liệu PDF, DOCX) lên hệ thống,
**So that** tôi có thể lưu trữ tập trung và sử dụng làm tài nguyên cho bài viết tiếp thị hoặc tệp đính kèm trong chat.

**Acceptance Criteria:**
- **Given** người dùng ở trang DMS, **When** chọn tệp tin hợp lệ và nhấn "Tải lên", **Then** tệp được upload lên MinIO, ghi nhận metadata vào `dms_db` và hiển thị trên UI.
- **Given** người dùng chọn tệp nguy hiểm (.exe, .bat, .sh), **When** nhấn tải lên, **Then** hệ thống chặn và hiển thị lỗi "Định dạng tệp không được hỗ trợ".
- **Given** tệp tải lên thành công, **When** hoàn tất, **Then** Kafka publish sự kiện `dms.file.created` chứa thông tin tệp.

**Priority:** 🔴 Must Have | **Story Points:** 5
**Liên kết:** UC-26, FR-DMS-001, FR-DMS-002

---

### US-046: Quản lý cấu trúc thư mục ảo
**As a** Content Creator/Admin,
**I want to** tạo, sửa, xóa và kéo thả các thư mục ảo,
**So that** tôi có thể tổ chức, sắp xếp tệp tin khoa học theo từng chiến dịch hoặc chủ đề.

**Acceptance Criteria:**
- **Given** Admin ở trang DMS, **When** nhấn "Tạo thư mục" và nhập tên hợp lệ, **Then** thư mục được lưu và hiển thị trên cây thư mục.
- **Given** Admin kéo thả một tệp từ thư mục A sang thư mục B, **When** thả tệp, **Then** hệ thống cập nhật `parent_folder_id` của tệp đó trong database và reload danh sách.

**Priority:** 🟡 Should Have | **Story Points:** 5
**Liên kết:** UC-27, FR-DMS-003, FR-DMS-004

---

### US-047: Thiết lập quyền truy cập Hybrid cho thư mục
**As a** Tenant Admin,
**I want to** cấu hình chế độ truy cập (Public hoặc Private) cho từng thư mục,
**So that** ảnh bài đăng marketing có thể truy cập nhanh (Public) và tài liệu nội bộ/RAG được bảo mật tuyệt đối (Private).

**Acceptance Criteria:**
- **Given** thư mục được đặt chế độ `Public`, **When** người dùng ngoài truy cập, **Then** tệp tin hiển thị trực tiếp qua link CDN/MinIO mà không cần xác thực token.
- **Given** thư mục được đặt chế độ `Private`, **When** có yêu cầu truy cập, **Then** hệ thống bắt buộc kiểm tra JWT Token và yêu cầu sinh Presigned URL ngắn hạn để tải tệp.

**Priority:** 🔴 Must Have | **Story Points:** 5
**Liên kết:** UC-28, FR-DMS-005, FR-DMS-006

---

### US-048: Tự động kiểm soát hạn mức lưu trữ (Storage Quota)
**As a** Tenant Admin,
**I want to** hệ thống tự động ngăn chặn tải tệp lên khi tổng dung lượng lưu trữ của Tenant vượt quá giới hạn gói cước,
**So that** doanh nghiệp không bị phát sinh chi phí lưu trữ vượt ngân sách.

**Acceptance Criteria:**
- **Given** Tenant đang sử dụng gói Standard (hạn mức 10GB) và tổng dung lượng hiện tại là 9.95GB, **When** người dùng cố gắng tải lên tệp 100MB, **Then** hệ thống hiển thị thông báo lỗi "Vượt quá dung lượng lưu trữ cho phép của gói dịch vụ" và chặn upload.

**Priority:** 🔴 Must Have | **Story Points:** 5
**Liên kết:** UC-26, FR-DMS-002

---

### US-049: Quản lý phiên bản tệp tin với giới hạn cấu hình
**As a** Content Creator,
**I want to** hệ thống tự động tạo phiên bản mới khi upload trùng tên tệp tin và chỉ giữ tối đa N phiên bản gần nhất,
**So that** tôi có thể xem lại lịch sử thay đổi và không làm cạn kiệt dung lượng đĩa của hệ thống.

**Acceptance Criteria:**
- **Given** tệp `solavie_intro.pdf` đã tồn tại, **When** người dùng upload tệp mới trùng tên, **Then** hệ thống lưu tệp mới làm phiên bản hiện tại, đẩy bản cũ vào bảng lịch sử phiên bản (`v1`).
- **Given** cấu hình giới hạn N = 5 phiên bản, **When** người dùng upload phiên bản thứ 6, **Then** hệ thống tự động xóa file vật lý của phiên bản đầu tiên (`v1`) trên MinIO để giải phóng dung lượng.

**Priority:** 🟡 Should Have | **Story Points:** 8
**Liên kết:** UC-29, FR-DMS-007, FR-DMS-008

---

### US-050: Sinh link chia sẻ tệp Private có thời hạn (Presigned URL)
**As a** Agent,
**I want to** sinh link tải tạm thời có thời hạn hết hạn là 15 phút đối với các tệp Private,
**So that** khách hàng hoặc nhân viên khác chỉ có thể xem/tải tệp trong thời gian an toàn.

**Acceptance Criteria:**
- **Given** tệp tin Private trong DMS, **When** Agent nhấn "Lấy link chia sẻ", **Then** hệ thống sinh Presigned URL chứa chữ ký bảo mật có thời gian hiệu lực (TTL) là 15 phút.
- **Given** link chia sẻ đã quá 15 phút kể từ lúc sinh, **When** người dùng click vào link, **Then** MinIO/S3 trả về lỗi `Access Denied` hoặc `ExpiredToken`.

**Priority:** 🟡 Should Have | **Story Points:** 3
**Liên kết:** UC-28, FR-DMS-006

---

### US-051: Tự động rút gọn liên kết chiến dịch
**As a** Manager,
**I want to** hệ thống tự động rút gọn mọi liên kết đích trong nội dung tin nhắn chiến dịch Marketing,
**So that** tin nhắn gọn nhẹ và sẵn sàng để theo dõi hành vi nhấp chuột của từng khách hàng.

**Acceptance Criteria:**
- **Given** chiến dịch Broadcast chứa link `https://solavie.vn/sale`, **When** hệ thống bắt đầu gửi tin, **Then** link được thay thế thành `https://mkt.co/t/{tracking_id}` duy nhất cho mỗi Contact.
- **Given** link rút gọn được sinh ra, **When** kiểm tra `shortener_db`, **Then** tồn tại bản ghi mapping chính xác link rút gọn với link gốc, Contact ID, Campaign ID.

**Priority:** 🔴 Must Have | **Story Points:** 3
**Liên kết:** UC-30, FR-SHR-001, FR-SHR-002

---

### US-052: Theo dõi click và chuyển hướng link
**As a** Customer,
**I want to** chuyển hướng ngay lập tức về trang web đích của doanh nghiệp khi click vào link rút gọn,
**So that** trải nghiệm duyệt tin không bị gián đoạn và hệ thống ghi nhận được sự kiện click của tôi.

**Acceptance Criteria:**
- **Given** khách hàng click vào link `https://mkt.co/t/{tracking_id}`, **When** request gửi lên, **Then** Link Shortener Service publish event `campaign.link.clicked` chứa metadata sang Kafka trong vòng < 20ms và trả về HTTP Redirect `302 Found` trỏ tới link gốc.
- **Given** mã `tracking_id` bị sai hoặc hết hạn, **When** click vào link, **Then** hệ thống chuyển hướng về trang lỗi 404 thân thiện hoặc trang chủ của Tenant.

**Priority:** 🔴 Must Have | **Story Points:** 3
**Liên kết:** UC-30, FR-SHR-002, FR-SHR-003

---

### US-053: Nén dung lượng hình ảnh tải lên
**As a** System,
**I want to** tự động nén dung lượng của các hình ảnh (JPEG, PNG) tải lên hệ thống qua DMS,
**So that** tiết kiệm dung lượng lưu trữ MinIO và tăng tốc độ tải trang Dashboard của Agent.

**Acceptance Criteria:**
- **Given** người dùng tải lên ảnh JPEG dung lượng 5MB, **When** DMS upload thành công, **Then** Media Processor tiêu thụ event, nén dung lượng ảnh xuống < 1MB nhưng giữ nguyên độ phân giải và chất lượng chấp nhận được, lưu ghi đè lên MinIO.
- **Given** ảnh đã được nén, **When** hiển thị trên Dashboard, **Then** thời gian tải ảnh giảm xuống dưới 200ms.

**Priority:** 🟡 Should Have | **Story Points:** 5
**Liên kết:** UC-31, FR-MED-001

---

### US-054: Sinh ảnh thu nhỏ (Thumbnail) tự động
**As a** Agent,
**I want to** xem nhanh ảnh thu nhỏ (Thumbnail) của tài liệu PDF, hình ảnh hoặc video trên màn hình quản lý thư mục,
**So that** tôi có thể nhận diện và tìm kiếm tài liệu trực quan mà không cần tải toàn bộ file về máy.

**Acceptance Criteria:**
- **Given** tệp tin (ảnh/video/PDF) được tải lên, **When** Media Processor nhận event, **Then** tự động sinh ảnh thumbnail kích thước `200x200` pixel dạng `.png` và lưu vào thư mục `thumbnails/` trên MinIO.
- **Given** file đã có thumbnail, **When** gọi API lấy metadata tệp, **Then** trường `thumbnail_url` trả về URL dẫn trực tiếp tới ảnh thumbnail đó.

**Priority:** 🟡 Should Have | **Story Points:** 3
**Liên kết:** UC-31, FR-MED-002

---

### US-055: Chuyển mã (Transcode) video cho mạng xã hội
**As a** Content Creator,
**I want to** hệ thống tự động chuyển mã (transcode) mọi video tôi tải lên sang định dạng tiêu chuẩn phù hợp với API Facebook/TikTok,
**So that** các video quảng cáo luôn đăng tải thành công mà không bị API mạng xã hội từ chối do sai format.

**Acceptance Criteria:**
- **Given** video định dạng `.mov` hoặc `.avi` tải lên DMS, **When** Media Processor xử lý, **Then** chạy FFmpeg để transcode về định dạng `.mp4` chuẩn codec video H.264 và codec audio AAC.
- **Given** video dọc được tải lên để đăng TikTok, **When** transcode, **Then** hệ thống giữ nguyên tỷ lệ khung hình `9:16` và kiểm tra bitrate thích hợp để đăng qua API TikTok thành công.

**Priority:** 🟡 Should Have | **Story Points:** 8
**Liên kết:** UC-31, FR-MED-003

---

### US-056: Chuyển dữ liệu lịch sử cũ sang lưu trữ lạnh (Cold Storage)
**As a** System Admin,
**I want to** hệ thống tự động nén và đóng gói dữ liệu logs, tin nhắn cũ hơn 90 ngày lên S3 Cold Storage,
**So that** dung lượng đĩa của các DB hoạt động không bị quá tải và dữ liệu vẫn được bảo toàn phục vụ kiểm toán.

**Acceptance Criteria:**
- **Given** cấu hình dọn dẹp dữ liệu bật, **When** thời gian đạt 02:00 AM, **Then** Scheduler kích hoạt Quartz job quét các bản ghi logs/chat > 90 ngày trong `messaging_db` và `analytics_db` để xuất thành tệp Parquet.
- **Given** tệp Parquet được tạo, **When** upload lên MinIO, **Then** lưu tại bucket `archive/` phân cấp theo `tenant_id` và thời gian.

**Priority:** 🟡 Should Have | **Story Points:** 5
**Liên kết:** UC-32, FR-RET-001, FR-RET-002

---

### US-057: Xóa sạch dữ liệu cũ trong DB hoạt động
**As a** Database Administrator,
**I want to** hệ thống tự động xóa bỏ hoàn toàn các bản ghi dữ liệu đã được sao lưu lạnh thành công khỏi database hoạt động,
**So that** giải phóng dung lượng ổ cứng vật lý và phục hồi hiệu suất truy vấn.

**Acceptance Criteria:**
- **Given** tệp sao lưu Parquet đã được upload lên MinIO thành công, **When** job tiếp tục chạy, **Then** thực thi lệnh `DELETE` xóa các bản ghi cũ tương ứng trong DB hoạt động.
- **Given** lệnh xóa hoàn thành, **When** chạy `VACUUM` DB, **Then** dung lượng đĩa được giải phóng thực tế tăng lên và thời gian thực thi các API chat của Agent giảm xuống.

**Priority:** 🟡 Should Have | **Story Points:** 3
**Liên kết:** UC-32, FR-RET-002

---

### US-058: Ghi nhật ký kiểm toán hành động dọn dẹp
**As a** Security Officer,
**I want to** ghi nhận chi tiết hành động dọn dẹp dữ liệu tự động vào nhật ký kiểm toán (Audit Log),
**So that** tôi có thể kiểm tra xem dữ liệu nào đã bị xóa và đảm bảo tính tuân thủ bảo mật.

**Acceptance Criteria:**
- **Given** job dọn dẹp hoàn thành, **When** ghi nhận kết quả, **Then** publish một event audit vào Kafka topic `audit.events` với nội dung: ID Tenant, số lượng bản ghi đã xóa, dung lượng giải phóng, thời gian chạy và hash của tệp backup lạnh.

**Priority:** 🟡 Should Have | **Story Points:** 3
**Liên kết:** UC-32, FR-RET-003

---

### US-059: Quản lý Deal Pipeline trong CRM
**As a** Sales Agent,
**I want to** quản lý các giai đoạn của Deal bán hàng mặt trời theo dạng phễu kéo thả,
**So that** tôi có thể theo dõi và thúc đẩy tiến độ chốt hợp đồng với từng khách hàng hiệu quả.

**Acceptance Criteria:**
- **Given** Deal đang ở trạng thái `Consult`, **When** Agent xác nhận khách hàng đồng ý cho khảo sát thực tế, **Then** Agent có thể kéo thả Deal sang trạng thái `Survey` trên Kanban board, hệ thống lưu trạng thái mới và ghi log audit.

**Priority:** 🔴 Must Have | **Story Points:** 5
**Liên kết:** UC-33, FR-CRM-008

---

### US-060: Ghi nhận biên bản khảo sát mái nhà thực địa
**As a** Kỹ thuật viên khảo sát,
**I want to** nhập các thông số kỹ thuật mái nhà và upload ảnh chụp hiện trường tại công trình của khách hàng,
**So that** kỹ sư thiết kế có đủ dữ liệu thực tế để vẽ bản vẽ kỹ thuật tấm pin.

**Acceptance Criteria:**
- **Given** Deal ở trạng thái `Survey`, **When** Kỹ thuật viên nhập các thông số (Diện tích mái = 120m2, loại mái = Ngói, hướng = Nam) và upload 3 tấm ảnh kết cấu mái nhà, **Then** hệ thống ghi nhận bản ghi vào `crm_surveys`, lưu ảnh chụp lên MinIO qua DMS và tự động đổi trạng thái Deal thành `Proposal`.

**Priority:** 🔴 Must Have | **Story Points:** 5
**Liên kết:** UC-33, FR-CRM-009

---

### US-061: Tính toán sản lượng điện và ROI hoàn vốn
**As a** Sales Agent,
**I want to** hệ thống tự động tính toán công suất lắp đặt tối ưu, sản lượng điện sản sinh hàng năm và thời gian hoàn vốn đầu tư,
**So that** tôi có thể tư vấn phương án tài chính thuyết phục nhất cho khách hàng.

**Acceptance Criteria:**
- **Given** thông số khảo sát mái 120m2 và tiền điện trung bình 3 triệu VNĐ/tháng, **When** Agent bấm nút "Tính toán giải pháp", **Then** hệ thống tính toán đề xuất công suất tối ưu là 8 kWp, sản lượng điện dự kiến 960 kWh/tháng, tỷ lệ tiết kiệm 70% và thời gian hoàn vốn là 4.5 năm.

**Priority:** 🔴 Must Have | **Story Points:** 8
**Liên kết:** UC-34, FR-CRM-010

---

### US-062: Tự động xuất đề xuất Solar Proposal PDF
**As a** Sales Agent,
**I want to** tự động sinh bản đề xuất đầu tư (Solar Proposal) dạng file PDF hoàn chỉnh chứa ảnh khảo sát thực tế,
**So that** tôi có thể tải xuống và gửi bản chào giá chuyên nghiệp cho khách hàng ngay lập tức qua Zalo/Facebook.

**Acceptance Criteria:**
- **Given** kết quả tính toán giải pháp Solar hoàn thành, **When** Agent chọn "Xuất Proposal PDF", **Then** hệ thống tự động chèn dữ liệu vào template, xuất ra tệp PDF, lưu vào DMS ở chế độ Private và trả về link tải bảo mật (Presigned URL 15p) cho Agent.

**Priority:** 🔴 Must Have | **Story Points:** 5
**Liên kết:** UC-34, FR-CRM-011

---

### US-063: Khởi tạo Ticket O&M bảo hành khi khách báo lỗi
**As a** Agent trực chat,
**I want to** nhanh chóng tạo Ticket sửa chữa khi nhận được thông báo sự cố hệ thống từ khách hàng qua chat,
**So that** phòng bảo trì O&M tiếp nhận xử lý kịp thời và không bỏ sót yêu cầu bảo hành.

**Acceptance Criteria:**
- **Given** cuộc hội thoại chat trên Unified Inbox khách hàng báo lỗi "Inverter báo lỗi đèn đỏ chớp", **When** Agent chọn "Tạo Ticket sự cố", **Then** hệ thống tự động lấy thông tin Contact, tạo Ticket mới trong `crm_tickets` trạng thái `Open` và gán độ ưu tiên `High`.

**Priority:** 🟡 Should Have | **Story Points:** 3
**Liên kết:** UC-35, FR-CRM-012

---

### US-064: Phân công và theo dõi tiến độ sửa chữa hiện trường
**As a** Điều phối viên bảo trì,
**I want to** phân công kỹ thuật viên đi khắc phục sự cố và theo dõi tiến trình xử lý Ticket bảo trì cho đến khi hoàn thành,
**So that** tôi kiểm soát được chất lượng dịch vụ cam kết (SLA) với khách hàng.

**Acceptance Criteria:**
- **Given** Ticket O&M ở trạng thái `Open`, **When** Điều phối viên gán ID Kỹ thuật viên A, **Then** hệ thống chuyển trạng thái Ticket sang `Assigned` và gửi Notification cảnh báo về điện thoại Kỹ thuật viên A.
- **Given** Kỹ thuật viên A hoàn thành sửa chữa tại hiện trường, **When** chọn đóng ticket và upload ảnh nghiệm thu, **Then** Ticket chuyển sang `Closed` và gửi tin nhắn tự động cảm ơn cho khách hàng qua Zalo.

**Priority:** 🟡 Should Have | **Story Points:** 3
**Liên kết:** UC-35, FR-CRM-012

---

## 4.13. Epic 13: Gap Remediation — Tuân thủ Pháp luật & Nghiệp vụ bổ sung

### US-065: Deal tự động chuyển giai đoạn sau khảo sát
**As a** Sales Agent,
**I want to** khi Kỹ thuật viên lưu xong biên bản khảo sát mái, hệ thống tự động chuyển Deal sang giai đoạn `Báo giá & ROI`,
**So that** tôi không cần thao tác thủ công và quá trình bán hàng được liền mạch.

**Acceptance Criteria:**
- **Given** Deal ở trạng thái `Survey` và Kỹ thuật viên vừa lưu biên bản khảo sát thành công, **When** hệ thống ghi nhận bản ghi `crm_surveys` mới, **Then** tự động chuyển trạng thái Deal sang `Proposal` và gửi notification cho Sales Agent phụ trách.

**Priority:** 🔴 Must Have | **Story Points:** 3
**Liên kết:** UC-33, FR-CRM-008

---

### US-066: Lấy sơ đồ bố trí tấm pin 3D từ HelioScope/OpenSolar
**As a** Sales Agent,
**I want to** hệ thống tự động lấy sơ đồ thiết kế 3D bố trí tấm pin và sản lượng bức xạ từ HelioScope hoặc OpenSolar,
**So that** bản đề xuất Solar Proposal có thiết kế chuyên nghiệp và sản lượng chính xác theo vị trí thực tế.

**Acceptance Criteria:**
- **Given** thông tin khảo sát mái có tọa độ GPS, **When** Sales bấm "Lấy thiết kế 3D", **Then** hệ thống gọi API bên thứ ba và hiển thị sơ đồ bố trí tấm pin 3D kèm dữ liệu bức xạ.
- **Given** API bên thứ ba không phản hồi, **When** timeout sau 30 giây, **Then** hiển thị thông báo lỗi và cho phép Sales nhập sản lượng thủ công.

**Priority:** 🟡 Should Have | **Story Points:** 5
**Liên kết:** UC-34, FR-CRM-013

---

### US-067: Gửi tin cảm ơn và link CSAT sau đóng O&M Ticket
**As a** Quản lý dịch vụ hậu mãi,
**I want to** hệ thống tự động gửi tin nhắn cảm ơn và link khảo sát đánh giá dịch vụ khi đóng Ticket O&M,
**So that** tôi thu thập được phản hồi chất lượng dịch vụ từ khách hàng để cải thiện SLA.

**Acceptance Criteria:**
- **Given** Ticket O&M chuyển sang `Closed`, **When** hệ thống xử lý sự kiện đóng ticket, **Then** gửi tự động tin nhắn cảm ơn qua kênh MXH gốc kèm link khảo sát CSAT có thời hạn 72 giờ.
- **Given** khách hàng hoàn thành khảo sát CSAT, **When** submit form, **Then** điểm đánh giá được lưu vào `crm_tickets.csat_score`.

**Priority:** 🟡 Should Have | **Story Points:** 5
**Liên kết:** UC-35, FR-CRM-014

---

### US-068: Khóa chatbot sau khi thu thập Lead ngoài giờ
**As a** Sales Manager,
**I want to** chatbot tự động khóa (không trả lời tự do) sau khi hoàn thành thu thập thông tin Lead ngoài giờ,
**So that** khách hàng không nhận được thông tin sai lệch khi không có nhân viên trực giám sát.

**Acceptance Criteria:**
- **Given** kịch bản Lead Capture hoàn thành và khách hàng đã cung cấp SĐT, **When** hệ thống lưu Lead, **Then** chatbot bị khóa đối với cuộc hội thoại này, trạng thái chuyển thành `waiting_agent`.
- **Given** cuộc hội thoại đang ở `waiting_agent`, **When** Agent online bấm claim, **Then** chatbot được mở khóa và cuộc hội thoại chuyển sang Manual mode.

**Priority:** 🟡 Should Have | **Story Points:** 3
**Liên kết:** UC-12, FR-CB-012

---

### US-069: Giảm chi phí AI bằng Prompt Caching
**As a** System Architect,
**I want to** hệ thống tự động tổ chức cấu trúc prompt tối ưu cho Anthropic Prompt Caching,
**So that** giảm chi phí token đầu vào lặp lại tới 90% và tăng tốc độ phản hồi chatbot tới 80%.

**Acceptance Criteria:**
- **Given** một cuộc hội thoại có System Prompt + Tools Schema + RAG Context không đổi, **When** khách hàng gửi tin nhắn mới, **Then** AI Core sử dụng prompt structure có cache control breakpoints, API trả về `cache_read_input_tokens > 0` xác nhận cache hit.
- **Given** cache TTL mặc định 5 phút, **When** cuộc hội thoại không hoạt động > 5 phút, **Then** cache tự động hết hạn và lần gọi tiếp theo là cold start.

**Priority:** 🔴 Must Have | **Story Points:** 5
**Liên kết:** UC-10, FR-AI-004

---

### US-070: Kết nối TikTok Business vào hệ thống
**As a** Tenant Admin,
**I want to** kết nối tài khoản TikTok Business/Shop vào hệ thống qua OAuth,
**So that** hệ thống có thể nhận tin nhắn và bình luận TikTok, đăng nội dung lên TikTok.

**Acceptance Criteria:**
- **Given** Admin ở trang Quản lý kênh, **When** nhấn "Kết nối TikTok" và hoàn tất OAuth, **Then** kênh TikTok hiển thị trạng thái `Active` và webhook đã đăng ký.
- **Given** kênh TikTok đã kết nối, **When** Admin nhấn "Ngắt kết nối", **Then** token bị revoke, webhook bị hủy, trạng thái → `Disconnected`.

**Priority:** 🟡 Should Have | **Story Points:** 8
**Liên kết:** UC-04, FR-CH-006, FR-CH-007

---

### US-071: Tự động gia hạn Token TikTok
**As a** Hệ thống (Background),
**I want to** tự động gia hạn token TikTok trước khi hết hạn,
**So that** kênh TikTok không bị gián đoạn dịch vụ.

**Acceptance Criteria:**
- **Given** token TikTok sắp hết hạn trong 24 giờ, **When** background job quét tokens, **Then** tự động gọi TikTok API refresh và lưu token mới mã hóa AES-256.

**Priority:** 🟡 Should Have | **Story Points:** 3
**Liên kết:** UC-05, FR-CH-008

---

### US-072: Agent từ chối nhận cuộc chat Handoff
**As a** Agent,
**I want to** có thể từ chối cuộc chat được gán cho tôi từ Handoff nếu tôi đang bận,
**So that** khách hàng được chuyển sang Agent khác rảnh hơn thay vì phải chờ tôi.

**Acceptance Criteria:**
- **Given** Agent được gán cuộc chat từ Handoff, **When** Agent nhấn "Từ chối", **Then** cuộc chat quay lại hàng đợi chung và hệ thống chạy lại Hybrid Routing (loại trừ Agent vừa từ chối).

**Priority:** 🟢 Could Have | **Story Points:** 3
**Liên kết:** UC-08, FR-MSG-013

---

### US-073: Tự động chấm điểm Lead Score cho khách hàng
**As a** Sales Manager,
**I want to** hệ thống tự động chấm điểm tiềm năng cho mỗi khách hàng dựa trên hành vi tương tác,
**So that** đội Sales biết được khách hàng nào đang có nhu cầu cao nhất để ưu tiên liên hệ.

**Acceptance Criteria:**
- **Given** khách hàng cung cấp SĐT qua chat, **When** hệ thống nhận diện sự kiện, **Then** `lead_score` của Contact được cộng thêm điểm theo cấu hình (mặc định +20 điểm).
- **Given** khách hàng hỏi giá hệ thống điện mặt trời, **When** Chatbot phân loại intent = pricing_inquiry, **Then** `lead_score` được cộng thêm +15 điểm.
- **Given** khách hàng thể hiện thái độ tiêu cực, **When** sentiment score ≥ 0.60, **Then** `lead_score` bị trừ -10 điểm.

**Priority:** 🔴 Must Have | **Story Points:** 8
**Liên kết:** UC-36, FR-CRM-015

---

### US-074: Nhận cảnh báo Hot Lead khi khách hàng đạt ngưỡng VIP
**As a** Sales Agent,
**I want to** nhận thông báo khẩn cấp khi một khách hàng đạt ngưỡng Hot Lead,
**So that** tôi có thể gọi điện tư vấn trực tiếp ngay lập tức và tăng tỷ lệ chốt hợp đồng.

**Acceptance Criteria:**
- **Given** `lead_score` của Contact A vượt ngưỡng `hot_lead_threshold` (mặc định 60 điểm), **When** hệ thống phát hiện vượt ngưỡng, **Then** gắn tag `Hot Lead` cho Contact A, gửi Push Notification + âm thanh cảnh báo đến tất cả Sales online, hiển thị biểu tượng ⭐ trên Unified Inbox.

**Priority:** 🔴 Must Have | **Story Points:** 5
**Liên kết:** UC-36, FR-CRM-016

---

### US-075: Cấu hình trọng số Lead Scoring
**As a** Tenant Admin,
**I want to** tùy chỉnh trọng số điểm cho từng loại hành động khách hàng và ngưỡng Hot Lead,
**So that** hệ thống Lead Scoring phù hợp với đặc thù kinh doanh của doanh nghiệp tôi.

**Acceptance Criteria:**
- **Given** Admin vào trang Cấu hình > CRM & Campaign, **When** thay đổi trọng số "Cung cấp SĐT" từ +20 thành +25 và lưu, **Then** cấu hình có hiệu lực ngay lập tức (hot-reload), các Contact mới sẽ được chấm điểm theo trọng số mới.

**Priority:** 🔴 Must Have | **Story Points:** 3
**Liên kết:** UC-36, FR-CRM-017

---

### US-076: Hiển thị điều khoản xử lý dữ liệu cá nhân (NĐ 13/2023)
**As a** Tenant Admin,
**I want to** hệ thống tự động hiển thị thông báo điều khoản xử lý thông tin cá nhân khi khách hàng bắt đầu nhắn tin lần đầu,
**So that** doanh nghiệp tuân thủ Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân.

**Acceptance Criteria:**
- **Given** khách hàng gửi tin nhắn đầu tiên (chưa từng tương tác), **When** Chatbot nhận tin, **Then** gửi tin nhắn điều khoản trước khi phản hồi nội dung, kèm nút Quick Reply "Tôi đồng ý".
- **Given** khách hàng nhấn "Tôi đồng ý", **When** hệ thống nhận phản hồi, **Then** lưu `consent_given = true` vào CRM và Chatbot bắt đầu trả lời bình thường.
- **Given** khách hàng không đồng ý hoặc không phản hồi, **When** Chatbot chờ > 5 phút, **Then** gửi tin nhắn lịch sự "Cảm ơn bạn, nếu cần hỗ trợ hãy liên hệ lại nhé" và chỉ lưu thông tin ẩn danh.

**Priority:** 🔴 Must Have | **Story Points:** 5
**Liên kết:** UC-37, FR-SEC-001

---

### US-077: Xóa vĩnh viễn dữ liệu khách hàng theo yêu cầu
**As a** Manager có quyền `contacts:delete`,
**I want to** xóa hoàn toàn mọi dữ liệu cá nhân của một khách hàng khỏi hệ thống khi khách yêu cầu,
**So that** doanh nghiệp tuân thủ quyền rút lại dữ liệu theo NĐ 13/2023/NĐ-CP.

**Acceptance Criteria:**
- **Given** Manager mở hồ sơ Contact, **When** nhấn "Xóa vĩnh viễn dữ liệu", **Then** hệ thống hiển thị cảnh báo xác nhận 2 lần (double confirmation) trước khi thực hiện.
- **Given** Manager xác nhận xóa 2 lần, **When** hệ thống thực thi, **Then** xóa toàn bộ: lịch sử chat (messaging_db), thông tin CRM (crm_db), vector embedding (Qdrant), tệp đính kèm (MinIO), và ghi Audit Log hành động xóa (không ghi nội dung đã xóa).
- **Given** đã xóa xong, **When** Agent tìm kiếm SĐT/Email cũ, **Then** không tìm thấy bất kỳ kết quả nào.

**Priority:** 🔴 Must Have | **Story Points:** 8
**Liên kết:** UC-38, FR-SEC-002

---

## 4.14. Tổng hợp User Stories (Cập nhật v1.5.0)

| Epic | Số US | Must Have | Should Have | Could Have |
|------|-------|-----------|-------------|------------|
| Identity & Access | 5 | 4 | 1 | 0 |
| Channel Management | 5 | 3 | 2 | 0 |
| Messaging & Inbox | 10 | 6 | 3 | 1 |
| AI Chatbot | 6 | 3 | 3 | 0 |
| Knowledge Base | 2 | 2 | 0 | 0 |
| Content & Scheduler | 7 | 3 | 3 | 1 |
| CRM & Contact | 4 | 3 | 1 | 0 |
| Campaign | 3 | 0 | 2 | 1 |
| Analytics | 2 | 0 | 1 | 1 |
| Tenant Config | 2 | 2 | 0 | 0 |
| Comment Management | 2 | 0 | 2 | 0 |
| Document Management (DMS)| 6 | 3 | 3 | 0 |
| Link Shortener | 2 | 2 | 0 | 0 |
| Media Processing | 3 | 0 | 3 | 0 |
| Data Retention | 3 | 0 | 3 | 0 |
| Solar Business Logic | 9 | 5 | 4 | 0 |
| Lead Scoring & CRM+ | 3 | 3 | 0 | 0 |
| Security & Compliance | 2 | 2 | 0 | 0 |
| AI Cost Optimization | 1 | 1 | 0 | 0 |
| **Tổng** | **77** | **42** | **31** | **4** |

**Tổng Story Points ước lượng:** ~455 SP

---

*← [Trước: Use Cases](./03_Use_Cases.md) | [Về Mục lục](./00_SRS_Index.md) | [Tiếp: Functional Requirements →](./05_Functional_Requirements.md)*
