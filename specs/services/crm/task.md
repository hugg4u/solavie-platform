# Task Checklist — CRM Service

## Overview
This document tracks the implementation checklist for **CRM Service** based on the system specifications.

### Technical Stack & Configuration
- **Platform/Tech:** Node.js 20, NestJS, PostgreSQL crm_db

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/crm/requirements.md)
- [Design](file:///specs/solavie-system/services/crm/design.md)
- [Logging](file:///specs/solavie-system/services/crm/logging.md)
- [Business Logic](file:///specs/solavie-system/services/crm/business-logic.md)

---

## Tasks Checklist

### Task 1: 1: Contact Management
> *User Story: Là một Agent, tôi muốn hệ thống tự động tạo và quản lý hồ sơ khách hàng từ mọi kênh, để tôi có cái nhìn toàn diện về từng khách hàng.*

**Acceptance Criteria Implementation:**
- [ ] AC 1.1: WHEN có hội thoại mới từ khách hàng chưa tồn tại trong hệ thống, THE CRM_Service SHALL tự động tạo Contact mới chứa: external_user_id, tên hiển thị, avatar, kênh liên hệ ban đầu
- [ ] AC 1.2: THE CRM_Service SHALL hỗ trợ CRUD contacts per-tenant với tenant_id bắt buộc trong mọi query
- [ ] AC 1.3: THE CRM_Service SHALL aggregate interaction history từ tất cả kênh (Facebook, Zalo, TikTok) vào một timeline duy nhất với tag kênh nguồn rõ ràng trên mỗi tin nhắn
- [ ] AC 1.4: THE CRM_Service SHALL hiển thị hồ sơ 360° khách hàng: thông tin cá nhân, lịch sử chat đa kênh, Lead Score, Segment tags, Deals liên quan, O&M Tickets
- [ ] AC 1.5: WHEN cấu hình data_masking_enabled = true, THE CRM_Service SHALL tự động che các ký tự giữa của SĐT và Email (ví dụ: 091****567) đối với Agent không có quyền contacts:mask_data
- [ ] AC 1.6: THE CRM_Service SHALL liên kết nhiều channel identities (Facebook ID, Zalo ID) về một Contact duy nhất qua bảng contact_channels

### Task 2: 2: Tagging & Segmentation
> *User Story: Là một Manager, tôi muốn phân nhóm khách hàng linh hoạt để nhắm mục tiêu chiến dịch chính xác.*

**Acceptance Criteria Implementation:**
- [ ] AC 2.1: THE CRM_Service SHALL hỗ trợ gán custom tags thủ công per contact per-tenant
- [ ] AC 2.2: THE CRM_Service SHALL hỗ trợ tạo Segments với bộ lọc động: kênh nguồn, tags, lead score range, thời gian tương tác gần nhất, trạng thái Deal
- [ ] AC 2.3: THE CRM_Service SHALL auto-tag contacts dựa trên conversation patterns theo configurable rules từ Tenant Config
- [ ] AC 2.4: THE CRM_Service SHALL cung cấp API trả về danh sách Contact IDs thuộc một Segment để Campaign Service sử dụng

### Task 3: 3: AI Lead Scoring
> *User Story: Là một Sales Agent, tôi muốn biết khách hàng nào có tiềm năng cao nhất để ưu tiên tư vấn.*

**Acceptance Criteria Implementation:**
- [ ] AC 3.1: THE CRM_Service SHALL tính lead score (0-100) dựa trên behavior patterns: tần suất nhắn tin, hỏi giá, cung cấp SĐT, sentiment history, engagement
- [ ] AC 3.2: THE CRM_Service SHALL áp dụng dynamic weights từ cấu hình lead_scoring_rules của Tenant Config
- [ ] AC 3.3: WHEN lead score thay đổi > 10 điểm, THE CRM_Service SHALL publish event crm.lead.score.changed lên Kafka cho Notification Service
- [ ] AC 3.4: WHEN lead score vượt ngưỡng hot_lead_threshold cấu hình, THE CRM_Service SHALL kích hoạt Push Notification khẩn cấp kèm âm thanh cảnh báo cho Agent phụ trách
- [ ] AC 3.5: THE CRM_Service SHALL cache lead score trong Redis để truy vấn nhanh; invalidate cache khi có tương tác mới

### Task 4: 4: Duplicate Contact Merging
> *User Story: Là một Agent, tôi muốn gộp các hồ sơ trùng lặp của cùng một khách hàng để có thông tin đầy đủ.*

**Acceptance Criteria Implementation:**
- [ ] AC 4.1: WHEN có cập nhật SĐT cho một Contact, THE CRM_Service SHALL tìm kiếm các Contact khác có trùng SĐT trong cùng tenant
- [ ] AC 4.2: IF trùng SĐT + trùng Họ tên (không phân biệt dấu/hoa thường) HOẶC trùng SĐT + Email, THEN THE CRM_Service SHALL tự động chạy transaction gộp (Auto-Merge): chuyển toàn bộ conversation history, Deals, Tickets sang Contact chính
- [ ] AC 4.3: IF trùng SĐT nhưng Họ tên khác biệt hoàn toàn, THEN THE CRM_Service SHALL tạo bản ghi MergeSuggestion với similarity_score và KHÔNG tự động gộp
- [ ] AC 4.4: THE CRM_Service SHALL hiển thị MergeSuggestion trên Dashboard để Agent xác nhận thủ công (Approve/Dismiss)
- [ ] AC 4.5: WHEN merge hoàn tất, THE CRM_Service SHALL gộp toàn bộ lịch sử chat từ tất cả kênh vào một timeline duy nhất, giữ nguyên tag kênh nguồn trên mỗi tin nhắn

### Task 5: 5: Solar Deal Pipeline (Kanban Board)
> *User Story: Là một Sales Agent, tôi muốn theo dõi và quản lý cơ hội bán hàng Solar qua các giai đoạn trực quan.*

**Acceptance Criteria Implementation:**
- [ ] AC 5.1: THE CRM_Service SHALL cung cấp Kanban Board với 6 giai đoạn: lead → consult → survey → proposal → negotiation → contract_signed (và closed_lost)
- [ ] AC 5.2: WHEN khách hàng cung cấp Tên và SĐT hợp lệ qua chat, THE CRM_Service SHALL tự động tạo Deal mới ở giai đoạn lead và liên kết với Contact
- [ ] AC 5.3: THE CRM_Service SHALL cho phép Agent thay đổi giai đoạn Deal thủ công qua drag-and-drop trên Kanban Board
- [ ] AC 5.4: WHEN Kỹ thuật viên lưu biên bản khảo sát thực địa thành công, THE CRM_Service SHALL tự động chuyển Deal từ giai đoạn survey sang proposal
- [ ] AC 5.5: THE CRM_Service SHALL hỗ trợ phân công nhân viên phụ trách (assigned_to) cho từng Deal
- [ ] AC 5.6: THE CRM_Service SHALL lưu lý do thất bại (lost_reason) khi Deal chuyển sang closed_lost

### Task 6: 6: Site Survey — Khảo sát mái thực địa
> *User Story: Là một Kỹ thuật viên, tôi muốn ghi nhận thông số khảo sát mái nhà và upload ảnh hiện trường trực tiếp từ điện thoại.*

**Acceptance Criteria Implementation:**
- [ ] AC 6.1: THE CRM_Service SHALL cho phép đặt lịch khảo sát cho Deal ở giai đoạn survey: chọn ngày giờ, phân công Kỹ thuật viên hiện trường
- [ ] AC 6.2: WHEN lịch khảo sát được tạo, THE CRM_Service SHALL gửi thông báo nhiệm vụ đến tài khoản Kỹ thuật viên được phân công qua Notification Service
- [ ] AC 6.3: THE CRM_Service SHALL cho phép Kỹ thuật viên nhập thông số thực địa: diện tích mái (m²), độ dốc (độ), loại kết cấu mái (ngói/tôn/bê tông), hướng mái (Nam/Đông Nam/Tây Nam/...)
- [ ] AC 6.4: THE CRM_Service SHALL cho phép Kỹ thuật viên upload ảnh hiện trường (kết cấu khung sắt, tủ điện, toàn cảnh mái) lên MinIO/DMS và liên kết với hồ sơ Deal
- [ ] AC 6.5: WHEN biên bản khảo sát được lưu, THE CRM_Service SHALL tự động trigger chuyển giai đoạn Deal sang proposal (xem Requirement 5, AC 4)

### Task 7: 7: Solar ROI Calculator & Proposal PDF
> *User Story: Là một Sales Agent, tôi muốn tính toán phương án lắp đặt tối ưu và tự động xuất báo giá chuyên nghiệp gửi khách hàng.*

**Acceptance Criteria Implementation:**
- [ ] AC 7.1: THE CRM_Service SHALL tính toán tự động dựa trên hóa đơn tiền điện và diện tích mái: công suất tối ưu (kWp), số lượng tấm pin, sản lượng điện dự kiến/tháng (kWh), tỷ lệ tiết kiệm (%), thời gian hoàn vốn (năm)
- [ ] AC 7.2: THE CRM_Service SHALL áp dụng công thức chuẩn: 1 kWp ≈ 6-7m² diện tích mái; giờ nắng miền Nam 4.0-4.5h/ngày; bảng giá điện EVN hiện hành
- [ ] AC 7.3: THE CRM_Service SHALL hỗ trợ kết nối API bên thứ ba (HelioScope/OpenSolar) qua AI Core để lấy sơ đồ thiết kế 3D và sản lượng bức xạ chính xác theo vị trí GPS
- [ ] AC 7.4: WHEN Agent nhấn "Xuất báo giá", THE CRM_Service SHALL tự động biên soạn Proposal PDF gồm: thông tin khách hàng, thông số kỹ thuật mái, kết quả tính toán ROI, ảnh hiện trường
- [ ] AC 7.5: THE CRM_Service SHALL lưu Proposal PDF vào DMS dạng Private và tạo Presigned URL TTL 15 phút để Agent gửi cho khách qua Zalo/Facebook
- [ ] AC 7.6: THE CRM_Service SHALL liên kết dms_file_id của Proposal PDF với bản ghi crm_proposals trong DB

### Task 8: 8: O&M Ticketing — Bảo trì & Vận hành sau bán hàng
> *User Story: Là một Agent, tôi muốn tạo và quản lý phiếu hỗ trợ kỹ thuật khi khách hàng báo lỗi hệ thống Solar.*

**Acceptance Criteria Implementation:**
- [ ] AC 8.1: THE CRM_Service SHALL cho phép Agent tạo O&M Ticket từ cuộc chat với một click, tự động lấy thông tin Contact và mô tả sự cố từ tin nhắn
- [ ] AC 8.2: THE CRM_Service SHALL hỗ trợ 4 mức độ ưu tiên: low, medium, high, critical
- [ ] AC 8.3: THE CRM_Service SHALL cho phép Trưởng bộ phận phân công Kỹ thuật viên bảo trì phụ trách Ticket
- [ ] AC 8.4: WHEN Ticket được phân công, THE CRM_Service SHALL gửi thông báo nhiệm vụ đến Kỹ thuật viên qua Notification Service
- [ ] AC 8.5: THE CRM_Service SHALL cho phép Kỹ thuật viên upload ảnh nghiệm thu (thiết bị hoạt động bình thường) và cập nhật resolution_notes
- [ ] AC 8.6: WHEN Ticket chuyển sang trạng thái closed, THE CRM_Service SHALL tự động gửi tin nhắn cảm ơn kèm CSAT survey link qua kênh nguồn của khách hàng (Zalo OA hoặc Facebook)
- [ ] AC 8.7: THE CRM_Service SHALL theo dõi trạng thái Ticket: open → assigned → in_progress → closed

### Task 9: Implement Business Logic Rules
**Business Validations:**
- [ ] Luồng 2: AI Lead Scoring: Message frequency (last 7 days): {message_frequency}
- [ ] Luồng 2: AI Lead Scoring: Product/price mentions: {product_interest}
- [ ] Luồng 2: AI Lead Scoring: Sentiment trend: {sentiment_trend}
- [ ] Luồng 2: AI Lead Scoring: Response speed: {engagement_speed}
- [ ] Luồng 2: AI Lead Scoring: Days since last contact: {recency}
- [ ] Luồng 2: AI Lead Scoring: Multi-channel contact: {channel_diversity}
- [ ] Luồng 2: AI Lead Scoring: 80-100: Ready to buy (asking about price, availability, how to order)
- [ ] Luồng 2: AI Lead Scoring: 50-79: Interested (asking about features, comparing)
- [ ] Luồng 2: AI Lead Scoring: 20-49: Exploring (general questions, browsing)
- [ ] Luồng 2: AI Lead Scoring: 0-19: Cold (one-time contact, no engagement)

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

### Task: Security Integration (MỚI)
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `crm`
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`

### Task 10: Custom MCP Server Integration (MỚI)
- [ ] Thiết lập SSE transport endpoints `/api/v1/mcp/solar`, `/api/v1/mcp/crm`, `/api/v1/mcp/om` bằng `@modelcontextprotocol/sdk` trong NestJS.
- [ ] Đăng ký các schema tools tương ứng (`calculate_solar_roi`, `get_contact_360`, `create_om_ticket`, v.v.).
- [ ] Triển khai middleware xác thực JWT và so khớp chéo `tenant_id` từ arguments của tool call với JWT payload.
- [ ] Thực thi ghi nhận Prometheus metrics: `crm_mcp_tool_executions_total` và `crm_mcp_security_violations_total`.
- [ ] Viết unit tests kiểm tra việc chặn truy cập trái phép khi gửi lệch `tenant_id` trong tool call.
