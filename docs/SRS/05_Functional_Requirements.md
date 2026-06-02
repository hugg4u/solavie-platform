# 5. YÊU CẦU CHỨC NĂNG (FUNCTIONAL REQUIREMENTS)

> Phần này tuân thủ cấu trúc IEEE 830-1998 Section 3 và ISO/IEC/IEEE 29148:2018. Tất cả các yêu cầu chức năng đều được chuẩn hóa dưới dạng mã định danh duy nhất `FR-[MODULE]-[XXX]` và sử dụng các từ khóa chuẩn hóa (PHẢI, NÊN, CÓ THỂ) theo chuẩn RFC 2119.

---

## 5.1. Phân hệ Identity & Access Management (AUTH)

### FR-AUTH-001: Xác thực người dùng qua Keycloak
- **Mô tả:** Hệ thống **PHẢI** xác thực danh tính người dùng thông qua giao thức OpenID Connect (OIDC) Authorization Code Flow kết nối tới Keycloak Identity Provider.
- **Đầu vào:** Email/Username, Password gửi từ trang Đăng nhập Dashboard.
- **Đầu ra:** JWT Access Token (chứa `tenant_id`, `user_id`, `roles`), Refresh Token và ID Token hợp lệ.
- **Ràng buộc:** Access Token **PHẢI** có thời hạn hiệu lực là 15 phút (có thể cấu hình), Refresh Token có thời hạn hiệu lực là 7 ngày.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-01, US-001

### FR-AUTH-002: Tự động làm mới Token (Silent Refresh)
- **Mô tả:** Dashboard **PHẢI** tự động gửi yêu cầu lấy Access Token mới thông qua Refresh Token khi Access Token hiện tại sắp hết hạn (trong vòng 30 giây cuối) mà không gây gián đoạn trải nghiệm người dùng.
- **Đầu vào:** Refresh Token lưu trữ an toàn trong HTTP-only Cookie hoặc memory.
- **Đầu ra:** Access Token mới.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-01, US-001

### FR-AUTH-003: Đăng xuất khi hết hạn phiên rảnh (Session Timeout)
- **Mô tả:** Hệ thống **PHẢI** tự động đăng xuất người dùng và hủy phiên làm việc trên Keycloak khi người dùng không có hành động tương tác nào (chuột, bàn phím, chat) quá thời gian quy định tại cấu hình `session_timeout_minutes`.
- **Đầu vào:** Thời gian không hoạt động của client.
- **Đầu ra:** Hủy JWT token trên Redis/Keycloak và điều hướng về trang Login.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-01, US-002

### FR-AUTH-004: Phân quyền dựa trên vai trò động (Dynamic RBAC)
- **Mô tả:** Hệ thống **PHẢI** kiểm tra quyền hạn của người dùng đối với từng API endpoint tại Kong API Gateway thông qua phân tích JWT Roles claim và đối chiếu với chính sách phân quyền lưu trữ trên DB.
- **Đầu vào:** JWT Access Token gửi kèm request.
- **Đầu ra:** Chấp nhận request hoặc trả về lỗi `403 Forbidden` nếu thiếu quyền.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-02, US-003

### FR-AUTH-009: Phân quyền mức Client (Client Scopes / Least Privilege)
- **Mô tả:** Hệ thống **PHẢI** định nghĩa và kiểm tra tính hợp lệ của các OAuth2 Client Scopes đối với từng Client (Dashboard, API Gateway) và từng API Route tại Gateway. Mỗi microservice nghiệp vụ (như Campaign, CRM) sẽ tương ứng với một scope cụ thể.
- **Đầu vào:** JWT Access Token gửi kèm request chứa claim `scope`.
- **Đầu ra:** Cho phép forward request tới microservice đích nếu token chứa scope hợp lệ, ngược lại trả về `403 Forbidden`.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-01, US-001


### FR-AUTH-010: Phân tách Danh tính và Hồ sơ Nghiệp vụ Người dùng (Hybrid User Profiles)
- **Mô tả:** Hệ thống **PHẢI** tách biệt dữ liệu xác thực cơ bản (do Keycloak quản lý) và hồ sơ nghiệp vụ người dùng nội bộ (do User Service phía Backend quản lý). Khi người dùng đăng ký hoặc được tạo mới, hệ thống **PHẢI** lưu thông tin nghiệp vụ mở rộng (số điện thoại, phòng ban, ảnh đại diện, trạng thái kích hoạt) vào database nghiệp vụ riêng biệt, liên kết 1:1 qua User UUID nhận được từ Keycloak.
- **Đầu vào:** User UUID từ Keycloak, thông tin nghiệp vụ gửi từ dashboard hoặc API mời nhân viên.
- **Đầu ra:** Bản ghi User nghiệp vụ được tạo thành công trong database `solavie_user_db`.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-01, US-001


### FR-AUTH-011: Thu hồi Session và Access Token tức thời
- **Mô tả:** Khi một người dùng bị khóa tài khoản hoặc buộc đăng xuất bởi Admin, hệ thống **PHẢI** lập tức gọi API hủy toàn bộ session trên Keycloak và gửi sự kiện thu hồi `token.revoked` (kèm theo `jti` của các token liên quan) để API Gateway từ chối quyền truy cập ngay lập tức (< 1ms).
- **Đầu vào:** Sự kiện khóa tài khoản / force logout.
- **Đầu ra:** Phiên làm việc bị vô hiệu hóa trên cả Keycloak và API Gateway.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-01, US-002

### FR-AUTH-012: Tự phục hồi đồng bộ User (Lazy Synchronization)
- **Mô tả:** Nhằm dự phòng sự cố mất Webhook kích hoạt từ Keycloak, khi người dùng đăng nhập lần đầu tiên thành công và gửi JWT Token hợp lệ, nếu trạng thái DB local của User Service vẫn là `PENDING` thì hệ thống **PHẢI** tự động kích hoạt tài khoản thành `ACTIVE`.
- **Đầu vào:** Request mang JWT Token hợp lệ lần đầu của User.
- **Đầu ra:** Trạng thái tài khoản được tự động chuyển sang `ACTIVE` trên DB.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-01, US-001

### FR-AUTH-013: Bảo mật Webhook Endpoint (Signature Verification)
- **Mô tả:** Mọi Webhook API tiếp nhận sự kiện cập nhật trạng thái User từ Keycloak sang Backend **PHẢI** được bảo mật bằng cơ chế xác thực chữ ký (Signature Verification) sử dụng thuật toán HMAC-SHA256 với Shared Secret.
- **Đầu vào:** Request Header chứa chữ ký số (Signature).
- **Đầu ra:** Chấp nhận xử lý sự kiện hoặc từ chối trả về lỗi `401 Unauthorized` nếu chữ ký không hợp lệ.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-02, US-003


### FR-AUTH-005: Quản lý Vai trò và Quyền hạn (Role Management)
- **Mô tả:** Hệ thống **PHẢI** cung cấp giao diện cho phép Tenant Admin thực hiện các tác vụ CRUD Vai trò (Role) mới và gán các quyền hạn (Permissions) hệ thống tương ứng.
- **Đầu vào:** Tên vai trò, danh sách permissions chọn từ danh mục.
- **Đầu ra:** Vai trò mới được ghi nhận trong cơ sở dữ liệu `keycloak_db` và `config_db`.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-02, US-003

### FR-AUTH-006: Đồng bộ hóa quyền hạn thời gian thực (Real-time Permission Sync)
- **Mô tả:** Khi Tenant Admin thay đổi danh sách permissions của một Role, hệ thống **PHẢI** thu hồi (invalidate) ngay lập tức các cached session liên quan đến Role đó trên Redis.
- **Đầu vào:** Sự kiện lưu thay đổi vai trò.
- **Đầu ra:** Phép thay đổi có hiệu lực ngay trong lượt gọi API tiếp theo của Agent mà không cần đăng nhập lại.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-02, US-004

### FR-AUTH-007: Khởi tạo Tenant tự động (Automated Provisioning)
- **Mô tả:** Khi Super Admin tạo Tenant mới, Auth Service **PHẢI** gọi API Keycloak để tự động khởi tạo một Realm mới, thiết lập các role mặc định (Admin, Manager, Agent, Viewer), và tạo tài khoản Admin đầu tiên của Tenant.
- **Đầu vào:** Tên công ty, Email admin, Gói dịch vụ.
- **Đầu ra:** Realm Keycloak mới, Tài khoản Admin Tenant và kích hoạt gửi email chào mừng.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-03, US-005

### FR-AUTH-008: Gửi Email kích hoạt tài khoản
- **Mô tả:** Hệ thống **PHẢI** gửi email tự động kèm liên kết kích hoạt (định dạng token dùng một lần và hết hạn sau 24 giờ) tới địa chỉ email của Admin Tenant mới được tạo.
- **Đầu vào:** Sự kiện tạo Tenant.
- **Đầu ra:** Email gửi thành công qua SMTP/SES server.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-03, US-005

---

## 5.2. Phân hệ Quản lý Kênh liên lạc (CH)

### FR-CH-001: Kết nối Kênh Facebook Page qua OAuth
- **Mô tả:** Hệ thống **PHẢI** hỗ trợ kết nối Facebook Page của Tenant thông qua luồng Facebook Login OAuth, trích xuất Page Access Token và lưu trữ vào cơ sở dữ liệu.
- **Đầu vào:** Facebook User authorization.
- **Đầu ra:** Bản ghi kênh mới với trạng thái `Active`, Page ID, Page Name, Page Access Token lưu mã hóa AES-256.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-04, US-006

### FR-CH-002: Đăng ký Webhook tự động cho Facebook
- **Mô tả:** Ngay khi kết nối Facebook Page thành công, Channel Connector Service **PHẢI** gọi Graph API để đăng ký nhận sự kiện tin nhắn (`messages`), bình luận (`ratings`, `feed`) của Page về Webhook URL của hệ thống.
- **Đầu vào:** Page Access Token.
- **Đầu ra:** Webhook được thiết lập thành công trên Facebook Developer App.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-04, US-006

### FR-CH-003: Kết nối Kênh Zalo OA
- **Mô tả:** Hệ thống **PHẢI** hỗ trợ kết nối Zalo Official Account thông qua Zalo OAuth SDK, trích xuất Access Token và Refresh Token để nhận webhook tin nhắn khách hàng gửi tới OA.
- **Đầu vào:** Xác thực tài khoản Admin Zalo OA.
- **Đầu ra:** Kênh Zalo OA hiển thị trạng thái `Active` kèm thông tin OA Name, OA ID.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-04, US-007

### FR-CH-004: Tự động gia hạn Token Kênh (Token Rotator)
- **Mô tả:** Background job **PHẢI** quét định kỳ mỗi 6 giờ để tìm các Refresh Token của Zalo OA hoặc Facebook sắp hết hạn (trong vòng 24 giờ tới) và tự động gọi API bên thứ ba để lấy Access Token mới.
- **Đầu vào:** Refresh Token cũ lưu trong DB.
- **Đầu ra:** Access Token & Refresh Token mới được mã hóa và ghi đè trong DB.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-05, US-008

### FR-CH-005: Xử lý và Cảnh báo Token hết hạn/Hủy ủy quyền
- **Mô tả:** Khi gọi API bên thứ ba trả về lỗi mất quyền truy cập (mã lỗi Token Expired hoặc Revoked), hệ thống **PHẢI** chuyển trạng thái kênh tương ứng thành `Token Expired` và gửi thông báo lỗi khẩn cấp tới Tenant Admin.
- **Đầu vào:** Mã lỗi API từ Facebook/Zalo.
- **Đầu ra:** Trạng thái kênh thay đổi, đẩy Notification cảnh báo.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-05, US-008

---

## 5.3. Phân hệ Tin nhắn và Hộp thư (MSG)

### FR-MSG-001: Hiển thị Hộp thư hợp nhất (Unified Inbox)
- **Mô tả:** Hệ thống **PHẢI** hiển thị toàn bộ hội thoại của Tenant từ Facebook, Zalo, TikTok trên cùng một màn hình Dashboard duy nhất, sắp xếp theo thời gian tin nhắn mới nhất giảm dần.
- **Đầu vào:** Yêu cầu tải trang Inbox của Agent.
- **Đầu ra:** Danh sách hội thoại phân trang, có phân biệt nguồn bằng icon/tag màu sắc khác nhau.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-06, US-009

### FR-MSG-002: Lọc và Tìm kiếm hội thoại nâng cao
- **Mô tả:** Hệ thống **PHẢI** cho phép Agent lọc hội thoại theo Kênh (Facebook, Zalo, TikTok), Trạng thái (Chờ xử lý, Đang xử lý, Đã đóng), Người phụ trách (Chưa gán, Tôi phụ trách, Agent khác), và tìm kiếm theo tên khách hàng.
- **Đầu vào:** Các bộ lọc/Từ khóa nhập từ giao diện Inbox.
- **Đầu ra:** Danh sách hội thoại thỏa mãn điều kiện lọc.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-06, US-010

### FR-MSG-003: Phân phối tin nhắn thời gian thực qua WebSocket
- **Mô tả:** Khi Channel Connector nhận được tin nhắn mới từ Webhook, hệ thống **PHẢI** normalize và truyền tải qua Kafka tới Messaging Service để đẩy trực tiếp tin nhắn xuống trình duyệt của Agent thông qua WebSocket với độ trễ < 1 giây.
- **Đầu vào:** Tin nhắn nhận từ Webhook ngoại vi.
- **Đầu ra:** Tin nhắn hiển thị trên Dashboard Agent mà không cần reload trang.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-06, US-011

### FR-MSG-004: Gửi tin nhắn phản hồi từ Dashboard
- **Mô tả:** Hệ thống **PHẢI** cho phép Agent nhập nội dung văn bản, đính kèm hình ảnh/tệp tin và gửi phản hồi cho khách hàng trực tiếp trên giao diện chat.
- **Đầu vào:** Nội dung chat do Agent nhập.
- **Đầu ra:** Gọi API ngoại vi tương ứng (Facebook Page API, Zalo OA API) để truyền tin đến điện thoại của khách hàng.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-07, US-012

### FR-MSG-005: Xử lý lỗi gửi tin và Retry tự động
- **Mô tả:** Nếu cuộc gọi gửi tin nhắn tới API của Facebook/Zalo bị lỗi mạng (5xx), hệ thống **PHẢI** tự động retry tối đa 3 lần bằng thuật toán Exponential Backoff. Nếu vẫn lỗi, tin nhắn **PHẢI** được đánh dấu trạng thái `Failed` trên UI kèm nút "Gửi lại".
- **Đầu vào:** Sự kiện gửi tin thất bại.
- **Đầu ra:** Trạng thái gửi tin cập nhật thành `Failed` và cảnh báo trực quan cho Agent.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-07, US-012

### FR-MSG-006: Kiểm soát Khung thời gian 24 giờ của Facebook
- **Mô tả:** Đối với kênh Facebook Messenger, hệ thống **PHẢI** kiểm tra khoảng cách thời gian kể từ tin nhắn cuối cùng của khách hàng. Nếu vượt quá 24 giờ, hệ thống **PHẢI** khóa ô nhập liệu thông thường và yêu cầu Agent chọn một Message Tag hợp lệ theo quy định của Meta trước khi gửi.
- **Đầu vào:** Thời gian tin nhắn cuối của khách hàng.
- **Đầu ra:** Khóa/Mở khóa ô chat và hiển thị giao diện chọn Message Tag.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-07, US-013

### FR-MSG-007: Thực hiện Handoff tự động từ Chatbot sang Agent
- **Mô tả:** Khi nhận được tín hiệu kích hoạt bàn giao từ Chatbot (do điểm tin cậy thấp hoặc khách hàng yêu cầu), Messaging Service **PHẢI** lập tức đổi chế độ hội thoại từ `Auto` sang `Manual`, gán cho Agent và kích hoạt gửi thông báo khẩn.
- **Đầu vào:** Yêu cầu Handoff từ Chatbot.
- **Đầu ra:** Trạng thái hội thoại chuyển thành `Manual`, gán Agent xử lý, push notify.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-08, US-014

### FR-MSG-008: Phát hiện cảm xúc tiêu cực để Handoff lập tức
- **Mô tả:** Hệ thống **PHẢI** liên tục phân tích cảm xúc tin nhắn của khách hàng. Nếu phát hiện cảm xúc tức giận (`angry`) với độ tin cậy >= 0.60, hệ thống **PHẢI** kích hoạt handoff khẩn cấp bỏ qua các bước xử lý tiếp theo của chatbot.
- **Đầu vào:** Sentiment score phân tích từ tin nhắn khách hàng.
- **Đầu ra:** Chuyển trạng thái hội thoại sang `Manual` ngay lập tức.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-08, US-015

### FR-MSG-009: Phân bổ cuộc gọi chat tự động (Routing Algorithm)
- **Mô tả:** Hệ thống **PHẢI** hỗ trợ thuật toán phân bổ Hybrid Routing: Ưu tiên gán cho Agent cũ đã từng chat; nếu offline/bận thì đưa vào hàng đợi Claim (3 phút); nếu quá 3 phút không ai nhận thì tự động gán cho Agent online có số lượng chat active ít nhất (Least Busy).
- **Đầu vào:** Sự kiện hội thoại chuyển sang Manual.
- **Đầu ra:** Hội thoại được gán cho Agent cụ thể.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-08, US-016

### FR-MSG-010: Chuyển ngược hội thoại Manual về Auto
- **Mô tả:** Hệ thống **PHẢI** cho phép Agent chủ động nhấn nút "Đóng hội thoại" (hoặc "Hoàn tất") để chuyển trạng thái hội thoại từ `Manual` về `Auto`, cho phép Chatbot tiếp quản trả lời các tin nhắn tiếp theo của khách hàng.
- **Đầu vào:** Thao tác nhấn nút hoàn tất của Agent.
- **Đầu ra:** Trạng thái hội thoại cập nhật thành `Auto`.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-09, US-017

### FR-MSG-011: Tự động chuyển Auto sau thời gian rảnh (Inactivity Auto-Close)
- **Mô tả:** Nếu hội thoại đang ở chế độ `Manual` nhưng không phát sinh bất kỳ tin nhắn mới nào từ cả Agent và khách hàng sau thời gian cấu hình `manual_to_auto_timeout_hours` (mặc định 2 giờ), hệ thống **PHẢI** tự động chuyển trạng thái hội thoại về `Auto`.
- **Đầu vào:** Thời gian rảnh của hội thoại Manual.
- **Đầu ra:** Hệ thống tự động cập nhật trạng thái về `Auto` qua background job.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-09, US-017

### FR-MSG-012: Trạng thái soạn thảo (Typing Indicator)
- **Mô tả:** Hệ thống **PHẢI** truyền nhận và hiển thị trạng thái đang soạn thảo (typing) của cả khách hàng và Agent lên giao diện chat theo thời gian thực (độ trễ < 500ms).
- **Đầu vào:** Sự kiện gõ phím từ client.
- **Đầu ra:** Gửi websocket event và hiển thị ký hiệu typing nhấp nháy trên UI.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-06, US-009

---

## 5.4. Phân hệ Trí tuệ Nhân tạo Chatbot (CB)

### FR-CB-001: Phân loại ý định khách hàng (Intent Classification)
- **Mô tả:** Chatbot Service **PHẢI** phân loại tin nhắn đầu vào của khách hàng thành các ý định cụ thể (FAQ, Đặt hàng, Tư vấn, Khiếu nại, Chào hỏi) với thời gian xử lý < 200ms.
- **Đầu vào:** Văn bản tin nhắn của khách hàng.
- **Đầu ra:** Tên ý định (Intent ID) kèm độ tin cậy (Confidence Score từ 0.0 đến 1.0).
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-10, US-018

### FR-CB-002: Trả lời tự động bằng RAG (Retrieval-Augmented Generation)
- **Mô tả:** Với ý định FAQ, Chatbot **PHẢI** truy vấn Knowledge Base để lấy tài liệu liên quan và gửi kèm prompt tới LLM để sinh câu trả lời chính xác, trung thực dựa trên tài liệu.
- **Đầu vào:** Văn bản câu hỏi của khách hàng, tài liệu ngữ cảnh trích xuất từ Vector DB.
- **Đầu ra:** Câu trả lời hoàn chỉnh được định dạng tự nhiên.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-10, US-018

### FR-CB-003: Quản lý và duy trì ngữ cảnh (Chat Session Memory)
- **Mô tả:** Chatbot **PHẢI** lưu trữ lịch sử chat của phiên hiện tại (tối đa 10 lượt chat gần nhất) vào PostgreSQL thông qua LangGraph state checkpoints và gửi kèm lịch sử này trong các yêu cầu sinh câu trả lời tiếp theo để duy trì ngữ cảnh hội thoại.
- **Đầu vào:** Lịch sử phiên chat từ DB.
- **Đầu ra:** Câu trả lời của LLM nhất quán với ngữ cảnh đã trao đổi.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-10, US-019

### FR-CB-004: Xử lý khi điểm tin cậy thấp (Confidence Threshold Guard)
- **Mô tả:** Nếu điểm tin cậy của ý định được phân loại hoặc điểm relevance của tài liệu RAG thấp hơn cấu hình `confidence_threshold` (mặc định 0.70), Chatbot **PHẢI** ngừng trả lời tự động và kích hoạt sự kiện Handoff sang Agent.
- **Đầu vào:** Điểm tin cậy của kết quả xử lý.
- **Đầu ra:** Trả về mã lệnh Handoff và nội dung tin nhắn thông báo hàng đợi cho khách hàng.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-08, US-014

### FR-CB-005: Trích xuất thông tin hóa đơn từ hình ảnh (AI Vision OCR)
- **Mô tả:** Khi nhận được tin nhắn dạng hình ảnh và cấu hình `ai_vision_invoice_reading = true`, Chatbot **PHẢI** gọi mô hình Vision LLM để phân tích hóa đơn, trích xuất: Số lượng điện tiêu thụ (kWh), Tổng số tiền (VND), Mã khách hàng.
- **Đầu vào:** Ảnh hóa đơn khách gửi.
- **Đầu ra:** JSON chứa các thuộc tính trích xuất.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-11, US-020

### FR-CB-006: Cấu hình Bật/Tắt tính năng AI Vision
- **Mô tả:** Hệ thống **PHẢI** tuân thủ cấu hình `ai_vision_invoice_reading`. Nếu giá trị bằng `false`, Chatbot **PHẢI** bỏ qua bước phân tích ảnh hóa đơn và thực hiện Handoff trực tiếp hoặc trả lời theo kịch bản chuẩn cho tin nhắn ảnh.
- **Đầu vào:** Tin nhắn hình ảnh và giá trị cấu hình Tenant.
- **Đầu ra:** Phản hồi hoặc Handoff theo cấu hình.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-11, US-021

### FR-CB-007: Tự động chạy kịch bản Thu thập thông tin ngoài giờ (Lead Capture)
- **Mô tả:** Khi ngoài khung giờ làm việc cấu hình (`working_hours`) và chế độ ngoài giờ được đặt là `lead_capture`, Chatbot **PHẢI** thực hiện chuỗi câu hỏi tự động để thu thập thông tin khách hàng (Tên, SĐT, Nhu cầu) và lưu lại.
- **Đầu vào:** Tin nhắn ngoài giờ của khách hàng.
- **Đầu ra:** Ghi nhận thông tin lead vào CRM Service và gửi tin nhắn hẹn giờ làm việc lại.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-12, US-022

### FR-CB-008: Validate Số điện thoại khách hàng cung cấp
- **Mô tả:** Trong luồng Lead Capture, Chatbot **PHẢI** kiểm tra định dạng số điện thoại do khách hàng cung cấp. Nếu số điện thoại không hợp lệ theo đầu số Việt Nam (10 chữ số, bắt đầu bằng 03, 05, 07, 08, 09), Chatbot **PHẢI** lịch sự yêu cầu khách hàng cung cấp lại.
- **Đầu vào:** Chuỗi ký tự số điện thoại khách hàng chat.
- **Đầu ra:** Chấp nhận lưu CRM hoặc gửi tin nhắn yêu cầu nhập lại.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-12, US-022

### FR-CB-009: Rào chắn đầu vào bằng Semantic Router (Input Guardrail)
- **Mô tả:** Hệ thống **PHẢI** kiểm tra tin nhắn của khách hàng trước khi chuyển qua LLM để sinh câu trả lời. Nếu bộ định tuyến ngữ nghĩa (Semantic Router) phát hiện tin nhắn thuộc các danh mục cấm (ví dụ: đối thủ cạnh tranh điện mặt trời, chính trị, tôn giáo) hoặc chứa dấu hiệu Jailbreak, hệ thống **PHẢI** lập tức chặn tin nhắn này.
- **Đầu vào:** Văn bản tin nhắn của khách hàng.
- **Đầu ra:** Trả về câu trả lời từ chối được định nghĩa sẵn, không chuyển tiếp yêu cầu tới LLM.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-10, US-018

### FR-CB-010: Xác thực nguồn câu trả lời bằng NLI (Output Guardrail)
- **Mô tả:** Đối với các câu trả lời do LLM sinh ra dựa trên RAG, hệ thống **PHẢI** kiểm tra tính xác thực (Grounding) thông qua mô hình NLI. Nếu mô hình phân loại câu trả lời ở trạng thái Mâu thuẫn (`Contradiction`) hoặc Trung lập (`Neutral` - không thể chứng thực bằng context RAG), hệ thống **PHẢI** chặn câu trả lời đó để tránh ảo giác thông tin.
- **Đầu vào:** Câu trả lời sinh ra từ LLM, các chunks tài liệu RAG lấy từ Vector DB.
- **Đầu ra:** Phê duyệt gửi tin nhắn nếu đạt Grounding Score >= 0.80, ngược lại thì kích hoạt kịch bản sinh lại (Regenerate) hoặc chuyển giao Handoff cho Agent.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-10, US-018

### FR-CB-011: Tự động tóm tắt tin nhắn lịch sử (Sliding Window & Summarization)
- **Mô tả:** Khi số lượng tin nhắn trong `MessagesState` vượt quá giới hạn cấu hình (mặc định 10 tin nhắn hoặc 4,000 tokens), LangGraph node **PHẢI** tự động gọi LLM để tóm tắt các tin nhắn cũ và lưu vào trường `summary` của state, sau đó cắt bỏ (trim) các tin nhắn cũ để tối ưu hóa dung lượng token gửi lên LLM.
- **Đầu vào:** Lịch sử cuộc hội thoại trong MessagesState.
- **Đầu ra:** Trạng thái State được cập nhật với trường `summary` mới và danh sách `messages` đã được rút gọn.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-10, US-019

### FR-AI-001: Quản lý kết nối MCP động cho từng Tenant (Multi-tenant MCP Host)
- **Mô tả:** AI Core Service **PHẢI** đóng vai trò là một MCP Host Gateway. Khi Chatbot của Tenant gửi yêu cầu gọi công cụ, AI Core **PHẢI** đọc thông số cấu hình MCP Server của Tenant đó từ `config_db` (URL, credentials, v.v.), khởi tạo phiên kết nối MCP Client Session độc lập và thực thi công cụ tương ứng.
- **Đầu vào:** Tenant ID, Tool call request từ Chatbot.
- **Đầu ra:** Thực thi công cụ tại MCP Server của Tenant và trả kết quả `ToolMessage` về cho Chatbot.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-10, US-018

### FR-AI-002: Giới hạn ranh giới bảo mật cho MCP Server (Roots Configuration)
- **Mô tả:** Khi kết nối với các MCP Server thao tác hệ thống tệp tin, AI Core **PHẢI** tự động truyền tham số ranh giới `Roots` (dạng URI) dựa trên ID và quota lưu trữ của Tenant, nhằm giới hạn phạm vi đọc/ghi tệp của MCP Server trong thư mục an toàn của Tenant đó.
- **Đầu vào:** Tenant ID, Roots path config.
- **Đầu ra:** MCP Server được cô lập an toàn trong thư mục chỉ định, từ chối đọc ghi các thư mục hệ thống bên ngoài.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-10, US-018

### FR-AI-003: Tạm dừng duyệt hành động nhạy cảm có cấu hình (Dynamic Breakpoints)
- **Mô tả:** Khi Chatbot gọi một công cụ nằm trong danh sách yêu cầu phê duyệt cấu hình bởi Admin (`required_approvals`), đồ thị LangGraph **PHẢI** tự động tạm dừng (pause) tại checkpoint và gửi tín hiệu chờ duyệt lên Dashboard của nhân viên.
- **Đầu vào:** Sự kiện gọi công cụ nhạy cảm, Cấu hình `required_approvals` của Tenant.
- **Đầu ra:** Tạo sự kiện `ActionApproval` ở trạng thái `Pending` trên CRM Dashboard; đồ thị tạm dừng cho đến khi nhận được tín hiệu `Approve` hoặc `Reject` từ Agent để chạy tiếp hoặc rollback.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-08, UC-33, US-014, US-060

---

## 5.5. Phân hệ Cơ sở tri thức (KB)

### FR-KB-001: Upload tài liệu tri thức
- **Mô tả:** Hệ thống **PHẢI** cho phép người dùng (Admin, Manager) tải lên các tài liệu định dạng PDF, DOCX, TXT, MD với kích thước tối đa 50MB mỗi file để làm tài liệu huấn luyện chatbot.
- **Đầu vào:** Tệp tin chọn từ máy tính người dùng.
- **Đầu ra:** Tệp tin được tải lên MinIO Object Storage thành công.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-13, US-023

### FR-KB-002: Tự động phân đoạn tài liệu (Semantic Chunking)
- **Mô tả:** Hệ thống **PHẢI** tự động chia nhỏ nội dung tài liệu thành các đoạn (chunks) có kích thước từ 256-512 tokens, đảm bảo không cắt ngang câu và có độ gối đầu (overlap) từ 10-20% để giữ tính liên tục ngữ nghĩa.
- **Đầu vào:** Nội dung văn bản của tài liệu.
- **Đầu ra:** Danh sách các văn bản chunk.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-13, US-023

### FR-KB-003: Số hóa và Lưu trữ Vector (Embedding Generation)
- **Mô tả:** Hệ thống **PHẢI** sử dụng mô hình embedding (ví dụ: `text-embedding-3-small`) để chuyển đổi các chunks thành vector 512 chiều và lưu vào Qdrant Vector Database, gắn kèm metadata `tenant_id` phục vụ cô lập dữ liệu.
- **Đầu vào:** Các chunks văn bản.
- **Đầu ra:** Vectors được ghi nhận thành công trong Qdrant Collection của Tenant.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-13, US-023

### FR-KB-004: Tìm kiếm hỗn hợp (Hybrid Search)
- **Mô tả:** Khi Chatbot truy vấn, Knowledge Base Service **PHẢI** thực hiện tìm kiếm song song: Dense Search (Vector Search trên Qdrant) + Sparse Search (Keyword Search BM25 trên Postgres) và kết hợp kết quả bằng thuật toán Reciprocal Rank Fusion (RRF).
- **Đầu vào:** Câu hỏi của khách hàng dưới dạng văn bản.
- **Đầu ra:** Danh sách top-20 chunks liên quan nhất kèm điểm số RRF.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-14, US-024

### FR-KB-005: Tối ưu kết quả tìm kiếm bằng Reranking
- **Mô tả:** Hệ thống **PHẢI** đưa top-20 chunks tìm kiếm được qua mô hình Reranker (ví dụ: `bge-reranker-v2-m3`) để đánh giá lại mức độ phù hợp thực tế và chọn ra top-5 chunks tốt nhất gửi lại cho Chatbot.
- **Đầu vào:** Danh sách 20 chunks kết quả.
- **Đầu ra:** Top-5 chunks tối ưu nhất kèm điểm tin cậy ngữ cảnh.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-14, US-024

---

## 5.6. Phân hệ Tạo nội dung (CNT)

### FR-CNT-001: Tạo nội dung bằng AI đa phiên bản
- **Mô tả:** Hệ thống **PHẢI** hỗ trợ người dùng nhập chủ đề/từ khóa và tự động sinh nội dung bài đăng tối ưu riêng biệt cho từng mạng xã hội được chọn (Facebook: viết dài, nhiều hashtag; TikTok: ngắn gọn, kêu gọi hành động; Zalo: trang trọng, xúc tích).
- **Đầu vào:** Chủ đề bài viết, Kênh đích mong muốn, Tông giọng lựa chọn.
- **Đầu ra:** Các phiên bản bài viết tương ứng hiển thị trên Dashboard.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-15, US-025

### FR-CNT-002: Tự động cá nhân hóa theo thương hiệu (Brand Voice Integration)
- **Mô tả:** Hệ thống **PHẢI** tự động đọc định nghĩa giọng điệu thương hiệu (brand voice) lưu trong cấu hình Tenant hoặc Knowledge Base để điều chỉnh từ ngữ bài viết AI sinh ra cho nhất quán với phong cách của Tenant.
- **Đầu vào:** Yêu cầu sinh bài viết, Cấu hình brand voice.
- **Đầu ra:** Bài viết tuân thủ phong cách thương hiệu.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-15, US-025

### FR-CNT-003: Đánh giá chất lượng bài viết tự động (Quality Check)
- **Mô tả:** Hệ thống **PHẢI** tự động quét bài viết AI vừa sinh để kiểm tra: Lỗi chính tả, Ngữ pháp, Số lượng ký tự cho phép của kênh, và đối chiếu với danh sách từ cấm (`banned_keywords`). Trả về điểm chất lượng (Quality Score) từ 0.0 đến 1.0.
- **Đầu vào:** Bài viết do AI hoặc con người soạn thảo.
- **Đầu ra:** Điểm Quality Score kèm danh sách các lỗi phát hiện (nếu có).
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-15, US-026

### FR-CNT-004: Chặn đăng tải bài viết chất lượng thấp
- **Mô tả:** Nếu bài viết có Quality Score < 0.70 hoặc chứa từ cấm, hệ thống **PHẢI** hiển thị cảnh báo đỏ và chặn không cho phép lên lịch hoặc đăng tải cho đến khi được chỉnh sửa lại để đạt điểm tiêu chuẩn.
- **Đầu vào:** Bài viết gửi đăng, Quality Score.
- **Đầu ra:** Thông báo chặn và highlight lỗi trên giao diện.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-15, US-026

### FR-CNT-005: Quy trình Phê duyệt bài viết (Approval Workflow)
- **Mô tả:** Khi cấu hình `require_content_approval = true`, mọi bài viết do nhân viên (Creator) tạo **PHẢI** được chuyển vào hàng đợi trạng thái `Pending Approval`. Chỉ những tài khoản có vai trò Manager hoặc Admin mới có quyền phê duyệt để chuyển trạng thái sang `Approved` để đăng tải.
- **Đầu vào:** Thao tác gửi bài viết của Creator.
- **Đầu ra:** Bài viết được đưa vào hàng đợi duyệt của Manager, gửi notification.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-16, US-027

### FR-CNT-006: Tự động phê duyệt bài đăng (Auto-Approve)
- **Mô tả:** Hệ thống **PHẢI** hỗ trợ cấu hình tự động duyệt bài viết. Nếu `require_content_approval = false` và bài viết đạt điểm Quality Score lớn hơn hoặc bằng cấu hình `auto_approve_quality_threshold` (mặc định 0.85), bài viết **PHẢI** được tự động chuyển sang trạng thái `Approved` mà không cần con người duyệt.
- **Đầu vào:** Sự kiện lưu bài đăng của Creator.
- **Đầu ra:** Trạng thái bài đăng cập nhật trực tiếp thành `Approved`.
- **Mức độ ưu tiên:** 🟢 Could Have
- **Truy vết:** UC-16, US-028

---

## 5.7. Phân hệ Lập lịch và Đăng bài (SCH)

### FR-SCH-001: Lên lịch đăng bài viết múi giờ động
- **Mô tả:** Hệ thống **PHẢI** cho phép người dùng đặt lịch đăng bài viết vào ngày/giờ cụ thể trong tương lai, hỗ trợ tự động quy đổi múi giờ (timezone-aware) tương ứng với múi giờ hoạt động của từng chi nhánh/kênh của Tenant.
- **Đầu vào:** Bài viết ở trạng thái Approved, Ngày giờ đăng, Kênh chọn đăng.
- **Đầu ra:** Bản ghi Quartz Job được đăng ký thành công trong cơ sở dữ liệu `scheduler_db`.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-17, US-029

### FR-SCH-002: Đăng bài tự động lên Facebook Feed và TikTok
- **Mô tả:** Khi đến giờ hẹn lịch của Quartz Job, hệ thống **PHẢI** tự động gửi payload nội dung bài viết qua Channel Connector để đăng tải công khai lên Feed của Facebook Page hoặc TikTok Shop của Tenant.
- **Đầu vào:** Sự kiện Quartz Job kích hoạt.
- **Đầu ra:** Bài viết được publish thành công lên MXH ngoại vi, trạng thái bài viết chuyển thành `Published`.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-17, US-029

### FR-SCH-003: Chuyển đổi bài đăng thành Zalo Broadcast Message
- **Mô tả:** Đối với kênh Zalo OA, do chính sách API không hỗ trợ tự động đăng bài lên bảng tin, hệ thống **PHẢI** tự động chuyển đổi payload bài đăng thành định dạng tin nhắn Broadcast và gửi tới toàn bộ khách hàng đang quan tâm (followers) Zalo OA của Tenant.
- **Đầu vào:** Sự kiện Quartz Job kích hoạt cho kênh Zalo.
- **Đầu ra:** Tin nhắn Broadcast gửi đi thành công tới các followers.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-17, US-029

### FR-SCH-004: Xử lý lỗi đăng bài và Tự động thử lại
- **Mô tả:** Nếu việc đăng tải lên MXH thất bại do lỗi API tạm thời từ phía bên thứ ba, Quartz Scheduler **PHẢI** tự động lên lịch retry tối đa 3 lần bằng cơ chế Exponential Backoff. Nếu vẫn thất bại sau 3 lần, trạng thái bài viết **PHẢI** chuyển thành `Draft_Failed` và gửi notification lỗi chi tiết cho người lên lịch.
- **Đầu vào:** Trạng thái lỗi từ API bên thứ ba.
- **Đầu ra:** Lịch retry được tạo hoặc trạng thái cập nhật thành `Draft_Failed` kèm notification.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-17, US-030

### FR-SCH-005: Xem Lịch trực quan (Calendar View Dashboard)
- **Mô tả:** Hệ thống **PHẢI** cung cấp giao diện Calendar View hiển thị tất cả các bài viết đã lên lịch hoặc đã đăng theo dạng Lịch Tuần/Lịch Tháng.
- **Đầu vào:** Yêu cầu truy cập lịch đăng bài.
- **Đầu ra:** Giao diện Calendar hiển thị các thẻ bài đăng trực quan theo mốc thời gian.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-18, US-031

### FR-SCH-006: Cập nhật lịch đăng bằng thao tác kéo thả (Drag-and-Drop)
- **Mô tả:** Hệ thống **PHẢI** cho phép Agent kéo thả các thẻ bài đăng trên giao diện Calendar để thay đổi thời gian đăng bài. Hệ thống sẽ tự động cập nhật lại thời gian chạy tương ứng trong Quartz Scheduler DB.
- **Đầu vào:** Thao tác kéo thả thẻ bài đăng của người dùng trên Calendar UI.
- **Đầu ra:** Quartz Job cập nhật thời gian kích hoạt mới thành công.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-18, US-031

---

## 5.8. Phân hệ Quản lý khách hàng CRM (CRM)

### FR-CRM-001: Tạo và cập nhật hồ sơ khách hàng tự động
- **Mô tả:** Khi có hội thoại mới phát sinh từ một khách hàng chưa từng tồn tại trên hệ thống, CRM Service **PHẢI** tự động tạo hồ sơ khách hàng mới (Contact) chứa ID ngoại vi, Tên hiển thị, Ảnh đại diện và Kênh liên hệ ban đầu.
- **Đầu vào:** Tin nhắn mới từ khách hàng mới.
- **Đầu ra:** Bản ghi Contact mới được lưu trữ trong cơ sở dữ liệu `crm_db`.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-19, US-032

### FR-CRM-002: Hiển thị hồ sơ 360° khách hàng (Timeline tương tác)
- **Mô tả:** Hệ thống **PHẢI** hiển thị một trang chi tiết khách hàng tích hợp đầy đủ thông tin: Thông tin cá nhân, Lịch sử chat (được gom nhóm từ tất cả các kênh tích hợp với nhãn tag kênh rõ ràng), Lead Score, và các Segment tags được gắn.
- **Đầu vào:** Thao tác click xem chi tiết Contact của Agent.
- **Đầu ra:** Giao diện hồ sơ 360° khách hàng.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-19, US-032

### FR-CRM-003: Ẩn thông tin nhạy cảm của khách hàng (Data Masking)
- **Mô tả:** Khi cấu hình `data_masking_enabled = true`, CRM Service **PHẢI** tự động che các ký tự giữa của Số điện thoại và Email khách hàng trên giao diện Dashboard đối với các tài khoản Agent không có quyền `contacts:mask_data`.
- **Đầu vào:** Dữ liệu Contact thô từ DB và quyền hạn của Agent đăng nhập.
- **Đầu ra:** Số điện thoại định dạng `091****567`, Email định dạng `a***@domain.com`.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-19, US-033

### FR-CRM-004: Tự động gộp hồ sơ khách hàng (Safe Contact Merging)
- **Mô tả:** Khi phát hiện hai Contact có trùng số điện thoại và thỏa mãn điều kiện gộp tự động (Trùng họ tên không dấu HOẶC trùng khớp địa chỉ Email), CRM Service **PHẢI** thực hiện gộp hai Contact này thành một bản ghi chính duy nhất.
- **Đầu vào:** Sự kiện cập nhật thông tin liên hệ của Contact.
- **Đầu ra:** Gộp thực thể vật lý trong DB, di chuyển toàn bộ conversation history và tags liên quan sang Contact chính, đánh dấu xóa/ẩn Contact phụ.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-20, US-034

### FR-CRM-005: Ghi nhận Audit Log gộp dữ liệu khách hàng
- **Mô tả:** Mọi giao dịch gộp khách hàng tự động hoặc thủ công **PHẢI** ghi nhận chi tiết vào Audit Log hệ thống bao gồm: ID các Contact nguồn, ID Contact đích, thời gian gộp và người/sự kiện thực hiện để phục vụ tra cứu khi có tranh chấp dữ liệu.
- **Đầu vào:** Sự kiện gộp Contact thành công.
- **Đầu ra:** Ghi log vào Kafka topic `audit.events`.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-20, US-034

### FR-CRM-006: Gợi ý gộp khách hàng thủ công (Manual Merge Suggestion)
- **Mô tả:** Nếu hai Contact trùng khớp số điện thoại nhưng có Họ tên khác biệt rõ ràng, hệ thống **KHÔNG ĐƯỢC** tự động gộp mà **PHẢI** tạo một đề xuất gộp dữ liệu (`MergeSuggestion`) gửi tới Dashboard.
- **Đầu vào:** Trùng số điện thoại nhưng lệch tên trên 2 Contacts.
- **Đầu ra:** Bản ghi đề xuất gộp được tạo trong DB và hiển thị cảnh báo cho Agent.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-20, US-035

### FR-CRM-007: Giao diện so sánh và Phê duyệt gộp thủ công
- **Mô tả:** Hệ thống **PHẢI** cung cấp giao diện so sánh song song thông tin của hai Contact trong bản ghi `MergeSuggestion` để Agent có thể review và đưa ra quyết định: Xác nhận gộp (Merge) hoặc Bỏ qua đề xuất (Dismiss).
- **Đầu vào:** Thao tác của Agent trên giao diện Merge Suggestion.
- **Đầu ra:** Thực hiện gộp dữ liệu vật lý (nếu chọn Merge) hoặc xóa đề xuất (nếu chọn Dismiss).
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-20, US-035

### FR-CRM-008: Quản lý Deal Pipeline dạng Kanban
- **Mô tả:** Hệ thống **PHẢI** cung cấp giao diện Kanban Board để Sales Agent theo dõi và thay đổi trạng thái của các cơ hội bán hàng (Deal) qua 6 giai đoạn: `Lead` (Tiếp cận) -> `Consult` (Tư vấn) -> `Survey` (Khảo sát) -> `Proposal` (Đề xuất) -> `Negotiation` (Thương thảo) -> `Contract Signed` (Đã ký).
- **Đầu vào:** Thao tác kéo thả Deal của Sales Agent hoặc cập nhật trạng thái Deal từ API.
- **Đầu ra:** Trạng thái Deal mới được ghi nhận trong cơ sở dữ liệu `crm_db` và cập nhật giao diện Kanban thời gian thực cho tất cả Agent cùng phân quyền.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-33, US-059

### FR-CRM-009: Lập lịch khảo sát và Ghi nhận dữ liệu thực địa
- **Mô tả:** Hệ thống **PHẢI** cho phép đặt lịch khảo sát mái nhà thực địa (Site Survey) cho Deal ở trạng thái `Survey`, phân công Kỹ thuật viên hiện trường và cho phép Kỹ thuật viên upload ảnh chụp hiện trường cùng các thông số kỹ thuật mái (diện tích, độ dốc, loại mái, hướng).
- **Đầu vào:** Thời gian khảo sát, ID Kỹ thuật viên, diện tích, độ dốc, loại mái, hướng mái, tệp ảnh chụp hiện trường.
- **Đầu ra:** Bản ghi khảo sát mới lưu trong bảng `crm_surveys`, ảnh chụp lưu trữ trên MinIO thông qua DMS Service, và trạng thái Deal tự động chuyển sang `Proposal`.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-33, US-060

### FR-CRM-010: Tự động tính toán công suất và ROI Solar
- **Mô tả:** Hệ thống **PHẢI** tự động tính toán phương án lắp đặt tối ưu dựa trên dữ liệu hóa đơn tiền điện trung bình của khách hàng và thông số khảo sát mái: công suất tối ưu (kWp), số lượng tấm pin, sản lượng điện hàng tháng dự kiến (kWh), tỷ lệ tiết kiệm hóa đơn điện và thời gian hoàn vốn đầu tư (ROI).
- **Đầu vào:** Tiền điện trung bình hàng tháng, diện tích mái khả dụng từ khảo sát.
- **Đầu ra:** Các thông số tính toán tối ưu gồm công suất hệ thống, sản lượng điện, tiền tiết kiệm và thời gian hoàn vốn (năm).
- **Ràng buộc:** Cho phép gọi API bên thứ ba (HelioScope/OpenSolar) để lấy dữ liệu tính toán sản lượng chi tiết thay thế cho bộ tính toán nội bộ của AI Core.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-34, US-061

### FR-CRM-011: Tự động biên soạn và xuất Solar Proposal PDF
- **Mô tả:** Hệ thống **PHẢI** tự động biên dịch kết quả tính toán tài chính và hình ảnh khảo sát mái thực tế thành một file Proposal đề xuất đầu tư dạng PDF, lưu vào DMS dưới dạng tệp `Private` và tạo liên kết tải tạm thời (Presigned URL) có TTL 15 phút.
- **Đầu vào:** Kết quả tính toán ROI, thông tin khảo sát, ảnh hiện trường, template Proposal PDF của Tenant.
- **Đầu ra:** File Proposal PDF lưu trữ vật lý trên MinIO thông qua DMS Service, bản ghi metadata lưu trong bảng `crm_proposals`, và trả về link presigned cho Agent gửi cho khách hàng.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-34, US-062

### FR-CRM-012: Tiếp nhận báo lỗi và Điều phối Ticket O&M
- **Mô tả:** Hệ thống **PHẢI** hỗ trợ tạo vé hỗ trợ vận hành bảo trì (O&M Ticket) khi khách hàng báo lỗi qua chat hoặc hotline, cho phép thiết lập độ ưu tiên (Low, Medium, High, Critical) và phân công Kỹ thuật viên bảo dưỡng xử lý hiện trường.
- **Đầu vào:** ID khách hàng, mô tả lỗi, độ ưu tiên, ID Kỹ thuật viên bảo trì.
- **Đầu ra:** Bản ghi Ticket mới lưu trong bảng `crm_tickets`, gửi thông báo khẩn qua Notification Service tới Kỹ thuật viên được gán, và lưu log audit hành trình.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-35, US-063, US-064

---

## 5.9. Phân hệ Chiến dịch gửi tin (CAM)

### FR-CAM-001: Lập và Khởi chạy chiến dịch Broadcast gửi tin nhắn hàng loạt
- **Mô tả:** Hệ thống **PHẢI** cho phép Manager thiết lập và gửi tin nhắn hàng loạt tới một Segment khách hàng được chọn trước theo kịch bản thời gian định sẵn.
- **Đầu vào:** Segment khách hàng mục tiêu, Nội dung tin nhắn gửi, Thời gian bắt đầu gửi.
- **Đầu ra:** Tạo chiến dịch gửi tin trong `campaign_db`, xếp hàng đợi gửi tin nhắn bất đồng bộ.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-21, US-036

### FR-CAM-002: Kiểm soát Tốc độ gửi tin chiến dịch (Campaign Throttling)
- **Mô tả:** Quá trình gửi tin chiến dịch **PHẢI** tuân thủ cấu hình `campaign_sending_rate` (số tin nhắn tối đa gửi đi trên một phút) và tự động tạm dừng (pause) hoặc giãn khoảng cách gửi nếu API của bên thứ ba trả về mã lỗi Rate Limit.
- **Đầu vào:** Trạng thái gửi tin nhắn từ Channel Connector.
- **Đầu ra:** Điều khiển tốc độ gửi tin nhắn bất đồng bộ để tránh bị khóa kênh.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-21, US-036

### FR-CAM-003: Xử lý gửi tin ngoài khung 24h đối với Facebook trong Chiến dịch
- **Mô tả:** Hệ thống **PHẢI** kiểm tra cấu hình `campaign_fb_outside_24h_action` để quyết định hành vi gửi tin chiến dịch cho khách Facebook ngoài khung 24h: tự động bỏ qua (`skip`) hoặc gửi kèm Message Tag được Meta cho phép (`use_tag`).
- **Đầu vào:** Cấu hình Tenant và thời gian tương tác cuối của khách hàng.
- **Đầu ra:** Gửi tin nhắn có tag hoặc bỏ qua contact Facebook đó.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-21, US-037

### FR-CAM-004: Gửi thử nghiệm A/B Testing chiến dịch
- **Mô tả:** Hệ thống **PHẢI** hỗ trợ tính năng A/B Testing, cho phép Manager cấu hình gửi 2 mẫu nội dung (Mẫu A và Mẫu B) tới một nhóm nhỏ khách hàng (ví dụ: 10% cho mẫu A, 10% cho mẫu B) trước khi gửi hàng loạt.
- **Đầu vào:** Thiết lập A/B Testing, 2 mẫu nội dung, tỷ lệ gửi thử nghiệm.
- **Đầu ra:** Chiến dịch gửi thử được thực thi bất đồng bộ.
- **Mức độ ưu tiên:** 🟢 Could Have
- **Truy vết:** UC-22, US-038

### FR-CAM-005: Đánh giá và Chọn nội dung chiến thắng (Winner Selection)
- **Mô tả:** Sau khoảng thời gian cấu hình (ví dụ: 2 giờ), hệ thống **PHẢI** tự động tính toán tỷ lệ tương tác (click link, phản hồi) của hai nhóm thử nghiệm, xác định nội dung chiến thắng có hiệu quả cao nhất và tự động dùng nội dung đó gửi tới 80% tập khách hàng còn lại.
- **Đầu vào:** Dữ liệu tương tác phản hồi của khách hàng ghi nhận trên TimescaleDB.
- **Đầu ra:** Tự động gửi nội dung chiến thắng cho phần còn lại của chiến dịch.
- **Mức độ ưu tiên:** 🟢 Could Have
- **Truy vết:** UC-22, US-038

---

## 5.10. Phân hệ Báo cáo và Phân tích (ANL)

### FR-ANL-001: Thu thập và lưu trữ Metrics thời gian thực (Time-series metrics)
- **Mô tả:** Analytics Service **PHẢI** lắng nghe tất cả các sự kiện tương tác hệ thống truyền qua Kafka (tin nhắn nhận/gửi, comment nhận/ẩn, handoff, token lỗi) để lưu trữ vào TimescaleDB phục vụ thống kê báo cáo theo chuỗi thời gian.
- **Đầu vào:** Sự kiện Kafka từ tất cả các microservices.
- **Đầu ra:** Ghi nhận metrics chuỗi thời gian thành công trong `analytics_db`.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-23, US-039

### FR-ANL-002: Hiển thị Báo cáo hiệu suất trực quan (Analytics Dashboard)
- **Mô tả:** Hệ thống **PHẢI** cung cấp giao diện Dashboard hiển thị các chỉ số hiệu suất chính (KPIs) của Tenant: Tổng số hội thoại theo kênh, Thời gian phản hồi trung bình của Agent, Tỷ lệ trả lời thành công của Chatbot, Số ca Handoff theo ngày/tuần/tháng.
- **Đầu vào:** Yêu cầu xem báo cáo kèm khoảng thời gian lọc (date range filter).
- **Đầu ra:** Các biểu đồ (Line, Bar, Pie chart) trực quan hóa dữ liệu hiệu suất.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-23, US-039

### FR-ANL-003: Xuất dữ liệu báo cáo dạng CSV/PDF
- **Mô tả:** Hệ thống **PHẢI** cho phép người dùng (Manager, Admin) xuất các báo cáo thống kê hiệu suất đang xem ra tệp tin định dạng CSV hoặc PDF để chia sẻ nội bộ.
- **Đầu vào:** Thao tác nhấn nút "Xuất báo cáo" của người dùng.
- **Đầu ra:** Tệp tin CSV/PDF tải xuống máy tính người dùng thành công.
- **Mức độ ưu tiên:** 🟢 Could Have
- **Truy vết:** UC-23, US-040

---

## 5.11. Phân hệ Cấu hình hệ thống (CFG)

### FR-CFG-001: Quản lý Cấu hình tập trung (Centralized CRUD Config)
- **Mô tả:** Tenant Config Service **PHẢI** cung cấp giao diện cho phép Tenant Admin thiết lập toàn bộ các tham số cấu hình của Tenant liên quan đến Chatbot, Lộ trình chat, Lập lịch và Bảo mật theo cấu trúc Schema chuẩn.
- **Đầu vào:** Các giá trị cấu hình thay đổi từ giao diện Cấu hình.
- **Đầu ra:** Dữ liệu cấu hình mới được cập nhật vào PostgreSQL `config_db`.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-24, US-041

### FR-CFG-002: Đồng bộ nóng cấu hình qua Redis Pub/Sub (Hot Reload)
- **Mô tả:** Khi Tenant Admin lưu cấu hình mới, Tenant Config Service **PHẢI** cập nhật dữ liệu cấu hình vào Redis Cache đồng thời publish một sự kiện tới Redis channel `config.updates` để thông báo cho tất cả các microservices liên quan cập nhật cấu hình trong bộ nhớ (< 5 giây) mà không cần reload/restart service.
- **Đầu vào:** Sự kiện cập nhật cấu hình trong database.
- **Đầu ra:** Redis channel publish sự kiện, các service đồng bộ cấu hình mới thành công.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-24, US-041

### FR-CFG-003: Kiểm tra tính hợp lệ của Cấu hình đầu vào (Config Validation)
- **Mô tả:** Hệ thống **PHẢI** thực hiện validate chặt chẽ kiểu dữ liệu và khoảng giá trị của tất cả cấu hình đầu vào theo đúng Schema được định nghĩa trước khi thực hiện ghi xuống DB.
- **Đầu vào:** JSON payload chứa cấu hình mới gửi lên.
- **Đầu ra:** Chấp nhận lưu cấu hình hoặc trả về lỗi `400 Bad Request` chi tiết lỗi validate.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-24, US-042

### FR-CFG-004: Phạm vi giới hạn các giá trị Cấu hình trọng yếu
- **Mô tả:** Hệ thống **PHẢI** giới hạn các giá trị cấu hình theo đúng quy tắc nghiệp vụ sau:
  - `ai_kb.confidence_threshold` chỉ được phép nằm trong khoảng `[0.60, 0.95]`.
  - `ai_kb.rag_relevance_threshold` chỉ được phép nằm trong khoảng `[0.0, 1.0]`.
  - `chat_routing.manual_to_auto_timeout_hours` chỉ được phép nằm trong khoảng `[1, 24]`.
  - `chat_routing.auto_close_timeout_hours` chỉ được phép nằm trong khoảng `[1, 72]`.
- **Đầu vào:** Giá trị cấu hình nhập từ client.
- **Đầu ra:** Cho phép lưu hoặc báo lỗi nếu vi phạm khoảng giới hạn.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-24, US-042

### FR-CFG-005: Quản lý khóa API bảo mật và sự kiện Đồng bộ cấu hình
- **Mô tả:** Tenant Config Service **PHẢI** mã hóa đối xứng (AES-256) các khóa API của nhà cung cấp LLM trước khi ghi vào database `config_db`. Khi lưu thành công, hệ thống **PHẢI** tự động publish thông điệp đồng bộ lên kênh Redis Pub/Sub `config.updates` để thông báo cho AI Core Service cập nhật.
- **Đầu vào:** Thao tác lưu API keys và cấu hình định tuyến từ Admin Dashboard.
- **Đầu ra:** API keys được mã hóa lưu DB và event đồng bộ được phát lên kênh `config.updates`.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-24, US-041

---

## 5.12. Phân hệ Quản lý bình luận (CMT)

### FR-CMT-001: Lắng nghe bình luận bài viết tự động
- **Mô tả:** Comment Manager Service **PHẢI** liên tục lắng nghe các webhook sự kiện bình luận mới trên các bài viết Facebook Page và TikTok Shop của Tenant được truyền qua Kafka topic `channel.comment.received`.
- **Đầu vào:** Sự kiện bình luận nhận từ webhook.
- **Đầu ra:** Ghi nhận bình luận vào `comment_db` và kích hoạt phân tích tự động.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-25, US-043

### FR-CMT-002: Tự động Ẩn/Xóa bình luận Spam bằng AI
- **Mô tả:** Hệ thống **PHẢI** gửi nội dung bình luận sang AI Core để chấm điểm Spam. Nếu Spam Score >= 0.85 (ngưỡng tin cậy rất cao), hệ thống **PHẢI** tự động gọi API của bên thứ ba để ẩn hoặc xóa bình luận đó và ghi nhận sự kiện vào audit log.
- **Đầu vào:** Nội dung bình luận, Spam score từ AI Core.
- **Đầu ra:** Gọi API ẩn/xóa bình luận thành công, ghi audit event.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-25, US-043

### FR-CMT-003: Phát hiện và Cảnh báo Bình luận tiêu cực (Negative Sentiment Escalation)
- **Mô tả:** Hệ thống **PHẢI** gửi nội dung bình luận sang AI Core để chấm điểm cảm xúc tiêu cực. Nếu Negative Sentiment Score >= 0.60, hệ thống **PHẢI** tự động đẩy bình luận vào danh sách "Bình luận cần xử lý" trên Dashboard và gửi thông báo khẩn tới Agent để xử lý khủng hoảng truyền thông.
- **Đầu vào:** Nội dung bình luận, Negative sentiment score từ AI Core.
- **Đầu ra:** Thêm bình luận vào hàng đợi xử lý của con người, gửi notify cho Agent.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-25, US-044

### FR-CMT-004: Tự động trả lời bình luận (FAQ Auto-reply)
- **Mô tả:** Đối với các bình luận mang tính chất hỏi đáp chung (FAQ) được AI Core phân loại và có điểm tin cậy đáp án >= 0.70, hệ thống **PHẢI** tự động soạn thảo nội dung phản hồi và gọi API bên thứ ba để đăng bình luận trả lời trực tiếp dưới bình luận của khách hàng.
- **Đầu vào:** Nội dung bình luận FAQ, câu trả lời sinh từ AI Core.
- **Đầu ra:** Đăng bình luận phản hồi thành công lên bài viết.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-25, US-043

---

## 5.13. Phân hệ Thông báo hệ thống (NOT - Supporting Service)

### FR-NOT-001: Gửi thông báo đẩy trên Dashboard (Web Push Notification)
- **Mô tả:** Notification Service **PHẢI** đẩy thông báo đẩy thời gian thực (Web Push) tới trình duyệt của các Agent/Manager online khi có các sự kiện quan trọng phát sinh (Handoff mới, Bình luận tiêu cực cần duyệt, Yêu cầu duyệt bài viết mới).
- **Đầu vào:** Sự kiện thông báo từ Kafka.
- **Đầu ra:** Hiển thị popup thông báo đẩy trên Dashboard của Agent.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-08, UC-16, UC-25, US-014, US-027, US-044

### FR-NOT-002: Gửi email cảnh báo hệ thống
- **Mô tả:** Hệ thống **PHẢI** tự động soạn thảo và gửi email cảnh báo tới địa chỉ email đăng ký của Tenant Admin/Manager khi xảy ra các sự cố nghiêm trọng (mất kết nối kênh MXH, chatbot lỗi liên tục, tài khoản sắp hết hạn).
- **Đầu vào:** Sự kiện sự cố hệ thống.
- **Đầu ra:** Email được gửi đi thành công tới Mail server.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-05, US-008

### FR-NOT-003: Dispatcher thông báo theo cấu hình kênh (Alert Channel Routing)
- **Mô tả:** Hệ thống **PHẢI** tuân thủ cấu hình `security_comments_notif.handoff_alert_channels` (danh sách các kênh nhận thông báo handoff, ví dụ: `web_push`, `email`, `telegram`). Hệ thống chỉ thực hiện gửi thông báo qua đúng các kênh đã được chọn trong cấu hình.
- **Đầu vào:** Sự kiện thông báo và cấu hình kênh nhận tin.
- **Đầu ra:** Gửi thông báo đến đúng các đầu mối đã cấu hình.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-08, UC-24, US-041

---

## 5.14. Phân hệ Quản lý tài liệu (DMS)

### FR-DMS-001: Tải lên tệp tin và Xác thực định dạng
- **Mô tả:** DMS Service **PHẢI** cung cấp API nhận file tải lên, tự động xác thực loại tệp (MIME type), chặn các tệp thực thi nguy hiểm (.exe, .msi, .sh, .bat) và lưu trữ vật lý vào MinIO Object Storage.
- **Đầu vào:** Tệp tin (ảnh, video, PDF, docx), folder_id đích.
- **Đầu ra:** ID tệp tin duy nhất, tên tệp, dung lượng, định dạng và đường dẫn lưu trữ.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-26, US-045

### FR-DMS-002: Kiểm soát Hạn mức lưu trữ (Storage Quota)
- **Mô tả:** Trước khi cho phép ghi file mới lên MinIO, DMS Service **PHẢI** tính tổng dung lượng tệp tin hiện tại của Tenant trong `dms_db` và đối chiếu với giới hạn dung lượng lưu trữ của gói dịch vụ Tenant đang dùng (được lấy từ Tenant Config Service). Hệ thống **PHẢI** chặn tải lên nếu vượt quá hạn mức.
- **Đầu vào:** Kích thước tệp mới tải lên, tenant_id.
- **Đầu ra:** Cho phép upload hoặc trả về lỗi `400 Bad Request` "Dung lượng bộ nhớ đã đầy".
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-26, US-048

### FR-DMS-003: Quản lý Thư mục ảo phân cấp
- **Mô tả:** DMS Service **PHẢI** cho phép người dùng tạo cấu trúc cây thư mục ảo trong phạm vi từng Tenant để dễ dàng phân chia tệp tin theo dự án hoặc chiến dịch.
- **Đầu vào:** Tên thư mục mới, parent_folder_id.
- **Đầu ra:** Thư mục ảo mới được ghi nhận trong DB.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-27, US-046

### FR-DMS-004: Di chuyển tệp tin và thư mục (Drag-and-Drop)
- **Mô tả:** Hệ thống **PHẢI** hỗ trợ API cập nhật mối quan hệ cha-con của thư mục và tệp tin để phục vụ thao tác di chuyển bằng kéo thả của người dùng trên UI.
- **Đầu vào:** target_id (file hoặc folder cần chuyển), new_parent_folder_id.
- **Đầu ra:** Cập nhật DB thành công.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-27, US-046

### FR-DMS-005: Cấu hình Quyền truy cập Hybrid (Public/Private)
- **Mô tả:** DMS Service **PHẢI** cho phép gán quyền truy cập cho từng thư mục/tệp tin:
  - `Public`: Link CDN/MinIO cố định, truy cập không cần token xác thực, dùng cho tệp hình ảnh bài viết tiếp thị.
  - `Private`: Bắt buộc xác thực JWT Token và sinh link có chữ ký thời hạn ngắn (Presigned URL) để tải tệp.
- **Đầu vào:** target_id (file hoặc folder), access_mode (`public` hoặc `private`).
- **Đầu ra:** Cập nhật DB thành công.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-28, US-047

### FR-DMS-006: Sinh liên kết tải bảo mật thời gian ngắn (Presigned URL)
- **Mô tả:** Đối với các tệp tin ở chế độ `Private`, DMS Service **PHẢI** sinh ra một đường dẫn liên kết tải tạm thời (Presigned URL của MinIO/S3) có chứa chữ ký xác thực mã hóa và thời gian hết hạn hiệu lực (TTL) là 15 phút.
- **Đầu vào:** file_id.
- **Đầu ra:** Presigned URL có thời hạn 15 phút.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-28, US-050

### FR-DMS-007: Tự động lưu phiên bản tệp tin mới (File Versioning)
- **Mô tả:** Khi người dùng tải lên một tệp tin trùng tên và trùng đường dẫn thư mục ảo, DMS Service **PHẢI** tự động đẩy tệp cũ vào bảng lịch sử phiên bản (`dms_file_versions`), lưu file mới làm phiên bản chính hiện tại và tăng số hiệu phiên bản lên `version + 1`.
- **Đầu vào:** Tệp tin tải lên trùng tên và path.
- **Đầu ra:** Tạo bản ghi phiên bản mới, lưu file vật lý mới lên MinIO dưới dạng version.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-29, US-049

### FR-DMS-008: Tự động dọn dẹp phiên bản cũ theo giới hạn (Versioning Purge)
- **Mô tả:** DMS Service **PHẢI** kiểm tra cấu hình số lượng phiên bản lưu trữ tối đa (N - lấy cấu hình từ Tenant Config Service, mặc định N = 5). Nếu số lượng bản ghi phiên bản lịch sử vượt quá N, hệ thống **PHẢI** tự động xóa vĩnh viễn tệp tin vật lý của phiên bản cũ nhất (`v1`) trên MinIO để tiết kiệm dung lượng đĩa.
- **Đầu vào:** Bản ghi phiên bản mới được tạo, cấu hình giới hạn N.
- **Đầu ra:** Xóa tệp vật lý cũ nhất nếu vượt quá giới hạn N.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-29, US-049

---

## 5.15. Phân hệ Theo dõi liên kết (SHR - Link Shortener)

### FR-SHR-001: Tự động rút gọn liên kết trong Chiến dịch
- **Mô tả:** Khi Campaign Service bắt đầu gửi tin nhắn hàng loạt có chứa liên kết đích, hệ thống **PHẢI** tự động gọi Link Shortener Service để mã hóa và tạo link rút gọn cá nhân hóa theo từng contact.
- **Đầu vào:** Liên kết gốc, Contact ID, Campaign ID, Variant ID (nếu chạy A/B Testing).
- **Đầu ra:** Bản ghi mapping trong `shortener_db` và liên kết rút gọn định dạng `https://mkt.co/t/{tracking_id}`.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-30, US-051

### FR-SHR-002: Chuyển hướng tốc độ cao và Ghi nhận sự kiện click
- **Mô tả:** Khi khách hàng click vào link rút gọn, Link Shortener Service **PHẢI** nhanh chóng giải mã từ Redis cache, publish sự kiện `campaign.link.clicked` sang Kafka và trả về mã chuyển hướng HTTP `302 Found` tới liên kết gốc.
- **Đầu vào:** Request HTTP GET tới `https://mkt.co/t/{tracking_id}`.
- **Đầu ra:** Publish event click sang Kafka và redirect trình duyệt của người dùng đến trang gốc (< 50ms).
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-30, US-051, US-052

### FR-SHR-003: Xử lý liên kết hết hạn hoặc sai mã
- **Mô tả:** Đối với các yêu cầu click chứa `tracking_id` không hợp lệ, bị lỗi format hoặc đã bị Tenant Admin đánh dấu xóa/hết hạn, hệ thống **PHẢI** chuyển hướng người dùng về trang thông báo lỗi 404 thân thiện hoặc trang chủ mặc định của Tenant.
- **Đầu vào:** Click link rút gọn không tồn tại/sai định dạng.
- **Đầu ra:** HTTP Redirect về trang lỗi/trang chủ mặc định của Tenant.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-30, US-052

---

## 5.16. Phân hệ Xử lý đa phương tiện (MED - Media Processing)

### FR-MED-001: Tự động nén dung lượng hình ảnh tải lên
- **Mô tả:** Khi có hình ảnh tải lên DMS, Media Processor Service **PHẢI** nén dung lượng hình ảnh gốc bất đồng bộ để tối ưu dung lượng lưu trữ trên MinIO nhưng giữ nguyên độ phân giải.
- **Đầu vào:** Sự kiện `dms.media.uploaded` cho tệp hình ảnh (JPEG/PNG).
- **Đầu ra:** Thay thế tệp gốc trên MinIO bằng tệp ảnh đã nén tối ưu, cập nhật dung lượng tệp mới vào `dms_db`.
- **Ràng buộc:** Ảnh JPEG/PNG dung lượng lớn phải được nén tối thiểu 50% dung lượng vật lý mà không làm vỡ hình ảnh (chất lượng nén ảnh 80-85%).
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-31, US-053

### FR-MED-002: Tự động tạo ảnh thu nhỏ (Thumbnails)
- **Mô tả:** Hệ thống **PHẢI** tự động sinh ảnh thu nhỏ (thumbnail) kích thước tối đa 200x200 pixel cho tất cả các định dạng hình ảnh, tài liệu PDF và video tải lên để hiển thị nhanh trên Dashboard quản lý.
- **Đầu vào:** Sự kiện tệp tin mới được tải lên MinIO.
- **Đầu ra:** File thumbnail dạng PNG lưu vào bucket `thumbnails/` và cập nhật `thumbnail_url` trong `dms_db`.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-31, US-054

### FR-MED-003: Chuyển mã video (Video Transcoding)
- **Mô tả:** Media Processor Service **PHẢI** chạy ngầm FFmpeg để chuyển mã tất cả video tải lên về định dạng video chuẩn `.mp4` sử dụng H.264 video codec và AAC audio codec để đảm bảo tương thích hoàn toàn khi đăng tải lên API Facebook và TikTok.
- **Đầu vào:** File video gốc tải lên (MOV, AVI, FLV, v.v.).
- **Đầu ra:** File `.mp4` đã được chuyển mã lưu trên MinIO và cập nhật metadata thời lượng, codec vào `dms_db`.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-31, US-055

---

## 5.17. Phân hệ Dọn dẹp & Lưu trữ dữ liệu (RET - Data Retention)

### FR-RET-001: Lập lịch dọn dẹp và nén dữ liệu cũ sang Cold Storage
- **Mô tả:** Hệ thống **PHẢI** tự động kích hoạt Quartz Job định kỳ hàng ngày (mặc định 02:00 AM) để quét toàn bộ tin nhắn chat và time-series logs cũ hơn 90 ngày, xuất dữ liệu này dưới dạng tệp nén Parquet phân theo từng Tenant.
- **Đầu vào:** Dữ liệu có `created_at` > 90 ngày trong `messaging_db` và `analytics_db`.
- **Đầu ra:** Tệp nén Parquet được tạo thành công và lưu vào MinIO Cold Storage (`s3://archive/{tenant_id}/...`).
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-32, US-056

### FR-RET-002: Xóa sạch dữ liệu đã lưu trữ khỏi Database hoạt động
- **Mô tả:** Sau khi tải tệp nén Parquet lưu trữ lạnh lên MinIO thành công, hệ thống **PHẢI** thực hiện câu lệnh xóa vĩnh viễn các dòng dữ liệu cũ đó ra khỏi các cơ sở dữ liệu chính và chạy dọn dẹp dung lượng trống (VACUUM/ANALYZE) để thu hồi bộ nhớ đĩa cứng.
- **Đầu vào:** Xác nhận tệp Parquet đã được lưu trữ thành công trên MinIO.
- **Đầu ra:** Dữ liệu cũ bị xóa hoàn toàn khỏi database hoạt động, giải phóng dung lượng đĩa cứng vật lý.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-32, US-057

### FR-RET-003: Ghi nhận sự kiện dọn dẹp bảo mật
- **Mô tả:** Tiến trình dọn dẹp **PHẢI** ghi lại nhật ký kiểm toán (Audit Log) chi tiết hành vi dọn dẹp gửi về Kafka topic `audit.events` để đảm bảo khả năng tra cứu bảo mật.
- **Đầu vào:** Thông số dọn dẹp (Số bản ghi đã xóa, dung lượng giải phóng, tên file lưu trữ lạnh, mã SHA256 kiểm tra tệp).
- **Đầu ra:** Ghi audit log thành công.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-32, US-058

---

## 5.18. Phân hệ Bảo mật & Tuân thủ pháp luật (SEC - Security & Compliance)

### FR-SEC-001: Hiển thị thông báo xử lý dữ liệu cá nhân (GDPR/NĐ 13/2023 Consent)
- **Mô tả:** Khi khách hàng gửi tin nhắn đầu tiên tới kênh MXH của Tenant (phiên hội thoại mới hoàn toàn chưa từng có tương tác), Chatbot **PHẢI** tự động gửi một tin nhắn điều khoản xử lý dữ liệu cá nhân theo quy định Nghị định 13/2023/NĐ-CP trước khi bắt đầu phản hồi nội dung. Khách hàng phải phản hồi đồng ý (ví dụ: trả lời "Đồng ý" hoặc nhấn nút Quick Reply "Tôi đồng ý") trước khi Chatbot tiếp tục cuộc trò chuyện. Nội dung thông báo có thể cấu hình bởi Tenant Admin qua Tenant Config.
- **Đầu vào:** Tin nhắn đầu tiên của khách hàng trong phiên mới.
- **Đầu ra:** Tin nhắn điều khoản gửi tự động; trạng thái `consent_given = true/false` lưu vào bảng CRM contacts.
- **Ràng buộc:** Nếu khách hàng không đồng ý hoặc không phản hồi, Chatbot **PHẢI** ngừng xử lý dữ liệu và chỉ lưu lại thông tin ẩn danh hóa.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-37, US-076

### FR-SEC-002: Quyền yêu cầu xóa dữ liệu cá nhân (Right to Erasure)
- **Mô tả:** Hệ thống **PHẢI** cung cấp chức năng cho phép nhân viên có quyền `contacts:delete` thực hiện xóa vĩnh viễn toàn bộ dữ liệu cá nhân của một khách hàng ra khỏi hệ thống khi khách hàng yêu cầu rút lại quyền xử lý thông tin. Quá trình xóa bao gồm: lịch sử chat, thông tin liên hệ, hồ sơ CRM, vector embedding trong Qdrant (nếu có), và tệp tin đính kèm trên MinIO.
- **Đầu vào:** ID Contact cần xóa, xác nhận của nhân viên có quyền.
- **Đầu ra:** Xóa vĩnh viễn dữ liệu khách hàng khỏi tất cả cơ sở dữ liệu liên quan, ghi Audit Log chi tiết (ghi nhận hành động xóa nhưng KHÔNG ghi nhận nội dung dữ liệu đã xóa).
- **Ràng buộc:** Hệ thống **PHẢI** hiển thị cảnh báo xác nhận 2 lần (double confirmation) trước khi thực hiện xóa vĩnh viễn. Hành động này không thể hoàn tác (irreversible).
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-38, US-077

---

## 5.19. Bổ sung Phân hệ CRM — Lead Scoring & CSAT

### FR-CRM-013: Tích hợp API bản đồ bức xạ mặt trời (HelioScope/OpenSolar)
- **Mô tả:** Hệ thống **NÊN** hỗ trợ kết nối với các dịch vụ bên thứ ba (HelioScope hoặc OpenSolar) thông qua API để lấy sơ đồ thiết kế 3D bố trí tấm pin trên mái nhà và sản lượng bức xạ chính xác dựa trên tọa độ GPS của công trình.
- **Đầu vào:** Tọa độ GPS (latitude, longitude) của công trình, diện tích mái khả dụng.
- **Đầu ra:** Sơ đồ bố trí 3D (ảnh) và dữ liệu bức xạ (kWh/m²/năm) lưu vào `crm_surveys`.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-34, US-066

### FR-CRM-014: Tự động gửi tin cảm ơn và Khảo sát CSAT khi đóng O&M Ticket
- **Mô tả:** Khi trạng thái O&M Ticket chuyển sang `Closed`, hệ thống **PHẢI** tự động gửi một tin nhắn cảm ơn qua kênh MXH gốc của khách hàng kèm theo đường link khảo sát đánh giá chất lượng dịch vụ (CSAT - Customer Satisfaction Survey). Link khảo sát có thời hạn hiệu lực 72 giờ.
- **Đầu vào:** Sự kiện Ticket chuyển sang `Closed`.
- **Đầu ra:** Tin nhắn cảm ơn gửi tự động qua Channel Connector, link khảo sát CSAT (Google Forms hoặc form tích hợp), lưu kết quả đánh giá vào `crm_tickets.csat_score`.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-35, US-067

### FR-CRM-015: Tự động chấm điểm tiềm năng khách hàng (Lead Scoring Engine)
- **Mô tả:** Hệ thống **PHẢI** tự động tính toán và cập nhật điểm số tiềm năng (`lead_score`) cho mỗi Contact dựa trên các hành động tương tác của khách hàng. Trọng số điểm cho từng hành động được cấu hình bởi Tenant Admin qua Tenant Config (ví dụ: cung cấp SĐT = +20 điểm, hỏi giá = +15 điểm, yêu cầu khảo sát = +30 điểm, thái độ tiêu cực = -10 điểm).
- **Đầu vào:** Sự kiện tương tác khách hàng (Kafka events: `contact.phone_provided`, `intent.pricing_inquiry`, `survey.requested`, `sentiment.negative`).
- **Đầu ra:** Cập nhật trường `lead_score` trong bảng `crm_contacts`.
- **Ràng buộc:** Lead Score **PHẢI** được tính toán bất đồng bộ qua Kafka consumer để không ảnh hưởng hiệu năng luồng chat chính.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-36, US-073

### FR-CRM-016: Cảnh báo Hot Lead khi đạt ngưỡng điểm VIP
- **Mô tả:** Khi `lead_score` của một Contact vượt qua ngưỡng `hot_lead_threshold` (cấu hình trong Tenant Config, mặc định = 60 điểm), hệ thống **PHẢI** tự động gắn tag `Hot Lead` cho Contact và gửi thông báo khẩn cấp (Push Notification + âm thanh cảnh báo) tới tất cả Sales Agent đang online để ưu tiên liên hệ tư vấn trực tiếp.
- **Đầu vào:** Sự kiện cập nhật `lead_score` vượt ngưỡng.
- **Đầu ra:** Tag `Hot Lead` gắn vào Contact, Notification khẩn gửi đến Sales team, hiển thị biểu tượng ngôi sao trên Unified Inbox.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-36, US-074

### FR-CRM-017: Giao diện cấu hình trọng số Lead Scoring
- **Mô tả:** Tenant Config Service **PHẢI** cung cấp giao diện cho phép Admin cấu hình trọng số điểm cho từng loại hành động khách hàng (dạng bảng key-value: action → score delta) và ngưỡng `hot_lead_threshold`. Thay đổi **PHẢI** có hiệu lực ngay lập tức (hot-reload) qua Redis Pub/Sub.
- **Đầu vào:** Cấu hình trọng số từ giao diện Admin.
- **Đầu ra:** Lưu cấu hình vào `config_db` và đồng bộ Redis cache.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-36, US-075

---

## 5.20. Bổ sung Phân hệ Kênh — TikTok Integration

### FR-CH-006: Kết nối kênh TikTok Business qua OAuth
- **Mô tả:** Hệ thống **PHẢI** hỗ trợ kết nối tài khoản TikTok Business/Shop của Tenant thông qua luồng TikTok Login OAuth 2.0, trích xuất Access Token và lưu trữ mã hóa AES-256 vào cơ sở dữ liệu.
- **Đầu vào:** TikTok Business account authorization.
- **Đầu ra:** Bản ghi kênh TikTok mới với trạng thái `Active`, TikTok User ID, Access Token mã hóa.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-04, US-070

### FR-CH-007: Đăng ký Webhook tự động cho TikTok
- **Mô tả:** Ngay khi kết nối TikTok thành công, Channel Connector Service **PHẢI** gọi TikTok API để đăng ký nhận sự kiện tin nhắn (`direct_messages`), bình luận video (`video_comments`) về Webhook URL của hệ thống.
- **Đầu vào:** TikTok Access Token.
- **Đầu ra:** Webhook được thiết lập thành công.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-04, US-070

### FR-CH-008: Gia hạn Token TikTok tự động
- **Mô tả:** Background job **PHẢI** bao gồm TikTok tokens trong chu kỳ quét 6 giờ định kỳ để tìm tokens sắp hết hạn và tự động gọi TikTok API refresh token.
- **Đầu vào:** TikTok Refresh Token.
- **Đầu ra:** Access Token mới lưu mã hóa vào DB.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-05, US-071

---

## 5.21. Bổ sung Phân hệ Chatbot — Lock & Greeting

### FR-CB-012: Khóa tạm thời Chatbot sau Lead Capture (Chatbot Lock)
- **Mô tả:** Sau khi hoàn thành kịch bản Lead Capture ngoài giờ, hệ thống **PHẢI** tự động khóa Chatbot đối với cuộc hội thoại đó. Chatbot **KHÔNG ĐƯỢC** trả lời tự do bất kỳ tin nhắn mới nào từ khách hàng cho đến khi một Agent online nhận xử lý và bấm mở khóa (claim conversation).
- **Đầu vào:** Sự kiện Lead Capture hoàn thành.
- **Đầu ra:** Trạng thái hội thoại chuyển thành `waiting_agent`, Chatbot bị khóa trả lời.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-12, US-068

### FR-CB-013: Chào khách hàng bằng tên hiển thị MXH (Personalized Greeting)
- **Mô tả:** Khi khách hàng gửi tin nhắn lần đầu (Intent = Chào hỏi), Chatbot **NÊN** tự động trích xuất tên hiển thị (display name) của khách hàng từ metadata của kênh MXH (Facebook profile name, Zalo display name, TikTok username) và sử dụng trong câu chào mở đầu.
- **Đầu vào:** Metadata khách hàng từ Channel Connector (trường `sender_name`).
- **Đầu ra:** Câu chào cá nhân hóa (ví dụ: "Xin chào anh Hùng, Solavie rất vui được hỗ trợ ạ!").
- **Mức độ ưu tiên:** 🟢 Could Have
- **Truy vết:** UC-10, US-018

---

## 5.22. Bổ sung Phân hệ Tin nhắn — Agent Reject & AI Cost

### FR-MSG-013: Agent từ chối Handoff và đưa lại hàng đợi
- **Mô tả:** Hệ thống **PHẢI** cho phép Agent được gán conversation từ Handoff nhấn nút "Từ chối" để trả lại conversation vào hàng đợi chung (Queue). Hệ thống **PHẢI** loại trừ Agent vừa từ chối khỏi danh sách gán tiếp theo và chạy lại Hybrid Routing Algorithm.
- **Đầu vào:** Thao tác nhấn "Từ chối" của Agent.
- **Đầu ra:** Conversation quay lại Queue, routing chạy lại (loại trừ Agent đã từ chối).
- **Mức độ ưu tiên:** 🟢 Could Have
- **Truy vết:** UC-08, US-072

### FR-AI-004: Tối ưu chi phí Token bằng Prompt Caching
- **Mô tả:** AI Core Service **PHẢI** sắp xếp cấu trúc prompt gửi lên LLM theo thứ tự: (1) System Prompt cố định, (2) MCP Tools Schema, (3) RAG Context tĩnh — đặt ở đầu prompt và gắn cache control breakpoints theo đặc tả Anthropic Prompt Caching API. Phần nội dung động (tin nhắn chat mới nhất) đặt cuối prompt.
- **Đầu vào:** System prompt, tools schema, RAG chunks, user message.
- **Đầu ra:** Prompt cấu trúc tối ưu cho cache hit, giảm tối đa 90% chi phí input token lặp lại và giảm 80% độ trễ phản hồi (TTFB).
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-10, US-069

### FR-AI-005: Định tuyến mô hình động (Dynamic Model Routing)
- **Mô tả:** AI Core Service **PHẢI** định tuyến yêu cầu LLM dựa trên cấu hình động lưu trong bảng `llm_route_configs` per-tenant và use case. Cho phép thay đổi runtime không cần khởi động lại.
- **Đầu vào:** Tenant ID, use case, parameters (temperature, max_tokens).
- **Đầu ra:** Model tương ứng được chọn cho primary và fallback.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-10, US-018

### FR-AI-006: Quản lý API Key mã hóa (Encrypted API Key Management)
- **Mô tả:** AI Core Service **PHẢI** quản lý và bảo mật API Keys cùng Custom Endpoint URL (Ollama/vLLM) trong bảng `api_key_configs` sử dụng thuật toán mã hóa đối xứng (AES-256).
- **Đầu vào:** LLM Provider, API Key thô, Base URL.
- **Đầu ra:** Khóa được mã hóa lưu DB và giải mã động khi gọi API.
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-10

### FR-AI-007: Bộ phân tích và giả lập chi phí (LLM Cost Analytics & Simulator)
- **Mô tả:** AI Core Service **PHẢI** lưu vết sử dụng (`llm_usage_logs`), cung cấp API tổng hợp chi phí (`GET /api/v1/analytics/usage-summary`) và cung cấp bộ giả lập chi phí (`POST /api/v1/analytics/simulate-cost`) để ước tính tiền tiết kiệm và độ trễ thay đổi dựa trên 30 ngày lịch sử.
- **Đầu vào:** Dữ liệu cấu hình muốn thay đổi, khoảng thời gian.
- **Đầu ra:** Tổng chi phí, token, và báo cáo phân tích tài chính/độ trễ mô phỏng.
- **Mức độ ưu tiên:** 🟡 Should Have
- **Truy vết:** UC-10

### FR-AI-008: Đồng bộ cấu hình thời gian thực qua Redis Pub/Sub
- **Mô tả:** AI Core Service **PHẢI** đăng ký (subscribe) kênh Redis Pub/Sub `config.updates`. Khi nhận được thông báo thay đổi cấu hình thuộc nhóm `ai_kb` của Tenant, AI Core **PHẢI** tự động gửi yêu cầu gRPC/REST sang Tenant Config Service để lấy cấu hình định tuyến và API keys mới, ghi đè vào database cục bộ và xóa cache Redis cũ.
- **Đầu vào:** Sự kiện thông báo `CONFIG_UPDATED` từ kênh `config.updates`.
- **Đầu ra:** Cấu hình mới được áp dụng tại AI Core và cache Redis cũ bị xóa bỏ (< 5 giây).
- **Mức độ ưu tiên:** 🔴 Must Have
- **Truy vết:** UC-10, US-018

---

*← [Trước: User Stories](./04_User_Stories.md) | [Về Mục lục](./00_SRS_Index.md) | [Tiếp: Non-Functional Requirements →](./06_NonFunctional_Requirements.md)*
