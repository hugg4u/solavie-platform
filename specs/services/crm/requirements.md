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
4. WHEN Agent nhấn "Xuất báo giá", THE CRM_Service SHALL tự động biên soạn Proposal PDF gồm: thông tin khách hàng, thông số kỹ thuật mái, kết quả tính toán ROI, ảnh hiện trường
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

## Security & Access Control
- **Authentication & Authorization:** APIs của CRM Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `crm`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến CRM Service.
- **Tenant Isolation:** Dữ liệu CRM **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.

