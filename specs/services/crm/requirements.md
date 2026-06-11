# Requirements Document

## Introduction

Dịch vụ quản lý khách hàng đa kênh của Solavie — auto-create contacts, tagging, segmentation, AI lead scoring, interaction history, duplicate merging, Solar Deal Pipeline (Kanban), Site Survey, ROI Calculator, Proposal PDF, O&M Ticketing.

## Glossary

- **CRM_Service**: Dịch vụ quản lý khách hàng (Node.js 20, NestJS, PostgreSQL crm_db)
- **Contact**: Hồ sơ khách hàng tổng hợp từ nhiều kênh
- **Deal**: Cơ hội bán hàng Solar qua 6 giai đoạn: lead → consult → survey → proposal → negotiation → contract_signed
- **Site_Survey**: Khảo sát mái nhà thực địa — đo diện tích, độ dốc, loại kết cấu, hướng mái
- **ROI_Calculator**: Công cụ tính toán công suất tối ưu, sản lượng điện, tiết kiệm và thời gian hoàn vốn
- **Proposal_PDF**: Báo giá Solar chuyên nghiệp dạng PDF — ghép thông tin khách + thông số kỹ thuật + ROI + ảnh mái
- **O&M_Ticket**: Phiếu hỗ trợ vận hành & bảo trì sau bán hàng
- **Lead_Score**: Điểm tiềm năng khách hàng (0-100) dựa trên behavior patterns
- **Hot_Lead**: Khách hàng có lead score vượt ngưỡng hot_lead_threshold — kích hoạt cảnh báo khẩn cấp
- **MergeSuggestion**: Đề xuất gộp Contact trùng lặp chờ Agent xác nhận thủ công
- **Data_Masking**: Che thông tin nhạy cảm (SĐT, email) cho Agent không có quyền xem đầy đủ
- **CSAT**: Customer Satisfaction Survey — khảo sát đánh giá chất lượng dịch vụ sau khi đóng O&M Ticket

## Requirements

### Requirement 1: Contact Management

**User Story:** Là một Agent, tôi muốn hệ thống tự động tạo và quản lý hồ sơ khách hàng từ mọi kênh, để tôi có cái nhìn toàn diện về từng khách hàng.

#### Acceptance Criteria
1. WHEN có hội thoại mới từ khách hàng chưa tồn tại trong hệ thống, THE CRM_Service SHALL tự động tạo Contact mới chứa: external_user_id, tên hiển thị, avatar, kênh liên hệ ban đầu
2. THE CRM_Service SHALL hỗ trợ CRUD contacts per-tenant với tenant_id bắt buộc trong mọi query
3. THE CRM_Service SHALL aggregate interaction history từ tất cả kênh (Facebook, Zalo, TikTok) vào một timeline duy nhất với tag kênh nguồn rõ ràng trên mỗi tin nhắn
4. THE CRM_Service SHALL hiển thị hồ sơ 360° khách hàng: thông tin cá nhân, lịch sử chat đa kênh, Lead Score, Segment tags, Deals liên quan, O&M Tickets
5. WHEN cấu hình data_masking_enabled = true, THE CRM_Service SHALL tự động che các ký tự giữa của SĐT và Email (ví dụ: 091****567) đối với Agent không có quyền contacts:mask_data
6. THE CRM_Service SHALL liên kết nhiều channel identities (Facebook ID, Zalo ID) về một Contact duy nhất qua bảng contact_channels

### Requirement 2: Tagging & Segmentation

**User Story:** Là một Manager, tôi muốn phân nhóm khách hàng linh hoạt để nhắm mục tiêu chiến dịch chính xác.

#### Acceptance Criteria
1. THE CRM_Service SHALL hỗ trợ gán custom tags thủ công per contact per-tenant
2. THE CRM_Service SHALL hỗ trợ tạo Segments với bộ lọc động: kênh nguồn, tags, lead score range, thời gian tương tác gần nhất, trạng thái Deal
3. THE CRM_Service SHALL auto-tag contacts dựa trên conversation patterns theo configurable rules từ Tenant Config
4. THE CRM_Service SHALL cung cấp API trả về danh sách Contact IDs thuộc một Segment để Campaign Service sử dụng

### Requirement 3: AI Lead Scoring

**User Story:** Là một Sales Agent, tôi muốn biết khách hàng nào có tiềm năng cao nhất để ưu tiên tư vấn.

#### Acceptance Criteria
1. THE CRM_Service SHALL tính lead score (0-100) dựa trên behavior patterns: tần suất nhắn tin, hỏi giá, cung cấp SĐT, sentiment history, engagement
2. THE CRM_Service SHALL áp dụng dynamic weights từ cấu hình lead_scoring_rules của Tenant Config
3. WHEN lead score thay đổi > 10 điểm, THE CRM_Service SHALL publish event crm.lead.score.changed lên Kafka cho Notification Service
4. WHEN lead score vượt ngưỡng hot_lead_threshold cấu hình, THE CRM_Service SHALL kích hoạt Push Notification khẩn cấp kèm âm thanh cảnh báo cho Agent phụ trách
5. THE CRM_Service SHALL cache lead score trong Redis để truy vấn nhanh; invalidate cache khi có tương tác mới

### Requirement 4: Duplicate Contact Merging

**User Story:** Là một Agent, tôi muốn gộp các hồ sơ trùng lặp của cùng một khách hàng để có thông tin đầy đủ.

#### Acceptance Criteria
1. WHEN có cập nhật SĐT cho một Contact, THE CRM_Service SHALL tìm kiếm các Contact khác có trùng SĐT trong cùng tenant
2. IF trùng SĐT + trùng Họ tên (không phân biệt dấu/hoa thường) HOẶC trùng SĐT + Email, THEN THE CRM_Service SHALL tự động chạy transaction gộp (Auto-Merge): chuyển toàn bộ conversation history, Deals, Tickets sang Contact chính
3. IF trùng SĐT nhưng Họ tên khác biệt hoàn toàn, THEN THE CRM_Service SHALL tạo bản ghi MergeSuggestion với similarity_score và KHÔNG tự động gộp
4. THE CRM_Service SHALL hiển thị MergeSuggestion trên Dashboard để Agent xác nhận thủ công (Approve/Dismiss)
5. WHEN merge hoàn tất, THE CRM_Service SHALL gộp toàn bộ lịch sử chat từ tất cả kênh vào một timeline duy nhất, giữ nguyên tag kênh nguồn trên mỗi tin nhắn

### Requirement 5: Solar Deal Pipeline (Kanban Board)

**User Story:** Là một Sales Agent, tôi muốn theo dõi và quản lý cơ hội bán hàng Solar qua các giai đoạn trực quan.

#### Acceptance Criteria
1. THE CRM_Service SHALL cung cấp Kanban Board với 6 giai đoạn: lead → consult → survey → proposal → negotiation → contract_signed (và closed_lost)
2. WHEN khách hàng cung cấp Tên và SĐT hợp lệ qua chat, THE CRM_Service SHALL tự động tạo Deal mới ở giai đoạn lead và liên kết với Contact
3. THE CRM_Service SHALL cho phép Agent thay đổi giai đoạn Deal thủ công qua drag-and-drop trên Kanban Board
4. WHEN Kỹ thuật viên lưu biên bản khảo sát thực địa thành công, THE CRM_Service SHALL tự động chuyển Deal từ giai đoạn survey sang proposal
5. THE CRM_Service SHALL hỗ trợ phân công nhân viên phụ trách (assigned_to) cho từng Deal
6. THE CRM_Service SHALL lưu lý do thất bại (lost_reason) khi Deal chuyển sang closed_lost

### Requirement 6: Site Survey — Khảo sát mái thực địa

**User Story:** Là một Kỹ thuật viên, tôi muốn ghi nhận thông số khảo sát mái nhà và upload ảnh hiện trường trực tiếp từ điện thoại.

#### Acceptance Criteria
1. THE CRM_Service SHALL cho phép đặt lịch khảo sát cho Deal ở giai đoạn survey: chọn ngày giờ, phân công Kỹ thuật viên hiện trường
2. WHEN lịch khảo sát được tạo, THE CRM_Service SHALL gửi thông báo nhiệm vụ đến tài khoản Kỹ thuật viên được phân công qua Notification Service
3. THE CRM_Service SHALL cho phép Kỹ thuật viên nhập thông số thực địa: diện tích mái (m²), độ dốc (độ), loại kết cấu mái (ngói/tôn/bê tông), hướng mái (Nam/Đông Nam/Tây Nam/...)
4. THE CRM_Service SHALL cho phép Kỹ thuật viên upload ảnh hiện trường (kết cấu khung sắt, tủ điện, toàn cảnh mái) lên MinIO/DMS và liên kết với hồ sơ Deal
5. WHEN biên bản khảo sát được lưu, THE CRM_Service SHALL tự động trigger chuyển giai đoạn Deal sang proposal (xem Requirement 5, AC 4)

### Requirement 7: Solar ROI Calculator & Proposal PDF

**User Story:** Là một Sales Agent, tôi muốn tính toán phương án lắp đặt tối ưu và tự động xuất báo giá chuyên nghiệp gửi khách hàng.

#### Acceptance Criteria
1. THE CRM_Service SHALL tính toán tự động dựa trên hóa đơn tiền điện và diện tích mái: công suất tối ưu (kWp), số lượng tấm pin, sản lượng điện dự kiến/tháng (kWh), tỷ lệ tiết kiệm (%), thời gian hoàn vốn (năm)
2. THE CRM_Service SHALL áp dụng công thức chuẩn: 1 kWp ≈ 6-7m² diện tích mái; giờ nắng miền Nam 4.0-4.5h/ngày; bảng giá điện EVN hiện hành
3. THE CRM_Service SHALL hỗ trợ kết nối API bên thứ ba (HelioScope/OpenSolar) qua AI Core để lấy sơ đồ thiết kế 3D và sản lượng bức xạ chính xác theo vị trí GPS
4. WHEN Agent nhấn "Xuất báo giá", THE CRM_Service SHALL tự động biên soạn Proposal PDF gồm: thông tin khách hàng, thông số kỹ thuật mái, kết quả tính toán ROI, ảnh hiện trường. Khi gọi `get_proposal_preview` qua MCP, kết quả trả về PHẢI là Presigned URL tới tệp Proposal PDF này (hạn dùng 15 phút) kèm theo tóm tắt ROI dưới dạng cấu trúc JSON, KHÔNG chỉ trả về tóm tắt văn bản thông thường.
5. THE CRM_Service SHALL lưu Proposal PDF vào DMS dạng Private và tạo Presigned URL TTL 15 phút để Agent gửi cho khách qua Zalo/Facebook
6. THE CRM_Service SHALL liên kết dms_file_id của Proposal PDF với bản ghi crm_proposals trong DB

### Requirement 8: O&M Ticketing — Bảo trì & Vận hành sau bán hàng

**User Story:** Là một Agent, tôi muốn tạo và quản lý phiếu hỗ trợ kỹ thuật khi khách hàng báo lỗi hệ thống Solar.

#### Acceptance Criteria
1. THE CRM_Service SHALL cho phép Agent tạo O&M Ticket từ cuộc chat với một click, tự động lấy thông tin Contact và mô tả sự cố từ tin nhắn
2. THE CRM_Service SHALL hỗ trợ 4 mức độ ưu tiên: low, medium, high, critical
3. THE CRM_Service SHALL cho phép Trưởng bộ phận phân công Kỹ thuật viên bảo trì phụ trách Ticket
4. WHEN Ticket được phân công, THE CRM_Service SHALL gửi thông báo nhiệm vụ đến Kỹ thuật viên qua Notification Service
5. THE CRM_Service SHALL cho phép Kỹ thuật viên upload ảnh nghiệm thu (thiết bị hoạt động bình thường) và cập nhật resolution_notes
6. WHEN Ticket chuyển sang trạng thái closed, THE CRM_Service SHALL tự động gửi tin nhắn cảm ơn kèm CSAT survey link qua kênh nguồn của khách hàng (Zalo OA hoặc Facebook)
7. THE CRM_Service SHALL theo dõi trạng thái Ticket: open → assigned → in_progress → closed


### Requirement: Zero-Trust Access Control & Permission Manifest

**User Story:** Là Tenant Admin, tôi muốn xem danh sách quyền hạn mà dịch vụ `crm` hỗ trợ để thiết lập vai trò tùy chỉnh trên Dashboard và đảm bảo bảo mật Zero-Trust downstream.

#### Acceptance Criteria
1. THE CRM_Service SHALL cung cấp API manifest tại `GET /api/v1/permissions/manifest` trả về danh sách tài nguyên (resources) và hành động (actions) được hỗ trợ.
2. THE CRM_Service SHALL thực hiện kiểm tra chữ ký số HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET` để xác thực request được gửi trực tiếp từ API Gateway tin cậy.
3. THE CRM_Service SHALL thực hiện kiểm tra quyền in-memory O(1) dựa trên HTTP Header `X-User-Permissions` truyền từ Gateway. Định dạng quyền của dịch vụ tuân theo cấu trúc `crm:{resource}:{action}` hỗ trợ ký tự đại diện `*` (Super Admin), `crm:*` (Toàn quyền trên service), và `crm:{resource}:*` (Toàn quyền trên tài nguyên).

## Security & Access Control
- **Authentication & Authorization:** APIs của CRM Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `crm`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến CRM Service.
- **Tenant Isolation:** Dữ liệu CRM **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.

### Requirement 9: Custom MCP Server Integration

**User Story:** Là một nhà phát triển hệ thống, tôi muốn CRM Service cung cấp các chuẩn giao diện Model Context Protocol (MCP) Server để AI Core có thể truy vấn và thực hiện các thao tác nghiệp vụ (tính toán Solar ROI, truy xuất dữ liệu CRM 360, và quản lý O&M Tickets) một cách động và bảo mật.

#### Acceptance Criteria
1. THE CRM_Service SHALL expose three distinct MCP Server modules over SSE (Server-Sent Events) transport:
   - **Solar Calc MCP Server**: Exposes `calculate_solar_roi` and `get_proposal_preview`.
   - **CRM MCP Server**: Exposes `get_contact_360`, `create_lead_deal`, and `update_deal_stage`.
   - **O&M Ticket MCP Server**: Exposes `create_om_ticket`, `get_ticket_status`, and `update_ticket_notes`.
2. THE CRM_Service SHALL validate the JWT bearer token in incoming SSE requests.
3. THE CRM_Service SHALL extract `tenant_id` from the HTTP header `X-Tenant-ID` (or custom JWT claim) and strictly restrict all tool executions within that tenant.
4. THE CRM_Service SHALL enforce parameter validation against the schema declared by the MCP server for each tool.
5. THE CRM_Service SHALL return standard JSON-RPC 2.0 responses wrapped in the MCP response format.

### Requirement 10: MCP Solar Calc Full Spec

**User Story:** Là một AI Agent hoặc Sales Agent, tôi muốn có đầy đủ đặc tả chi tiết của Solar Calc tools để thực hiện tính toán ROI chính xác theo các công thức quy định.

#### Acceptance Criteria
1. THE CRM_Service SHALL hỗ trợ công cụ `calculate_solar_roi` thực hiện tính toán ROI tự động:
   - Inputs: `monthly_bill` (số, VND), `roof_area_sqm` (số, m2), `location_zone` (chuỗi, enum: 'south', 'central', 'north')
   - Formula:
     * `sqm_per_kwp` = 6.5
     * `peak_sun_hours` = South: 4.25, Central: 3.75, North: 3.25
     * `system_efficiency` = 0.80
     * `max_kwp_by_area` = `roof_area_sqm` / `sqm_per_kwp`
     * `monthly_kwh_needed` = `monthly_bill` / `evn_price_per_kwh` (giả định EVN tier pricing trung bình 2,700 VND/kWh)
     * `optimal_kwp` = min(`max_kwp_by_area`, `monthly_kwh_needed` / (`peak_sun_hours` * 30 * `system_efficiency`))
     * `system_size_kwp` = round(`optimal_kwp`, 1)
     * `panel_quantity` = ceil(`system_size_kwp` / 0.4) (tấm pin 400Wp)
     * `estimated_kwh_month` = `system_size_kwp` * `peak_sun_hours` * 30 * `system_efficiency`
     * `monthly_savings_vnd` = `estimated_kwh_month` * `evn_price_per_kwh`
     * `savings_percentage` = (`monthly_savings_vnd` / `monthly_bill`) * 100
     * `total_investment` = `system_size_kwp` * `unit_price_per_kwp` (15,000,000 VND/kWp)
     * `payback_years` = `total_investment` / (`monthly_savings_vnd` * 12)
   - Outputs: roi_summary chứa đầy đủ các chỉ số tính toán trên.
2. THE CRM_Service SHALL hỗ trợ công cụ `get_proposal_preview` để truy xuất liên kết và tóm tắt đề xuất đã tạo:
   - Inputs: `deal_id` (UUID)
   - Outputs: `{ pdf_url, roi_summary }`.

### Requirement 11: Semantic Cache Integration

**User Story:** Là một hệ thống, tôi muốn CRM Service hỗ trợ AI Core tích hợp Semantic Cache để tối ưu chi phí hội thoại và giảm độ trễ phản hồi cho các yêu cầu nghiệp vụ tương đương.

#### Acceptance Criteria
1. THE CRM_Service SHALL hỗ trợ thiết lập và truy vấn dữ liệu ngữ nghĩa trên cache Redis Stack (DB 0) kết hợp khoảng cách Cosine.
2. THE CRM_Service SHALL đảm bảo tính cô lập dữ liệu tuyệt đối giữa các tenant trong cache (tenant isolation) thông qua metadata filter `tenant_id` trong mọi truy vấn `FT.SEARCH`.
3. THE CRM_Service SHALL hỗ trợ thời gian sống của tài liệu cache (TTL) mặc định là 86,400 giây (24 giờ).

---

## Service Discovery (Self-Registration)

**User Story:** Là một developer, tôi muốn service của mình tự động đăng ký và duy trì heartbeat trên Redis Registry khi khởi động để Gateway có thể định tuyến động chính xác mà không phụ thuộc vào hạ tầng.

### Acceptance Criteria
1. THE CRM Service SHALL tự động phát hiện IP nội bộ của card mạng chính khi khởi động bằng cơ chế socket UDP ảo.
2. THE CRM Service SHALL đăng ký địa chỉ `IP:Port` của mình vào Redis Set `registry:service:crm` khi startup.
3. THE CRM Service SHALL gửi tin nhắn sống (heartbeat) định kỳ mỗi 5 giây lên Redis key `registry:service:crm:node:{ip}:{port}` với TTL là 15 giây.
4. THE CRM Service SHALL dọn dẹp (hủy đăng ký) thông tin của mình trên Redis Set `registry:service:crm` và xóa key TTL khi nhận tín hiệu shutdown (`SIGTERM`/`SIGINT`).
