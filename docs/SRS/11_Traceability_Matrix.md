# 11. MA TRẬN TRUY VẾT YÊU CẦU (REQUIREMENTS TRACEABILITY MATRIX - RTM)

> Phần này tuân thủ cấu trúc ISO/IEC/IEEE 29148:2018. Ma trận RTM thiết lập mối liên kết hai chiều giữa các yêu cầu nghiệp vụ trong BRD, các yêu cầu chức năng (FR), các ca sử dụng (UC), câu chuyện người dùng (US) và các kịch bản kiểm thử (TC). Điều này đảm bảo tính đầy đủ của hệ thống và tránh hiện tượng phát sinh tính năng ngoài phạm vi (Scope Creep).

---

## 11.1. Bảng Ma trận truy vết yêu cầu (RTM Table)

| FR ID | Tóm tắt Yêu cầu Chức năng | Use Case | User Story | BRD Section | Test Case ID | Trạng thái |
|-------|---------------------------|----------|------------|-------------|--------------|------------|
| **FR-AUTH-001** | Xác thực Keycloak OIDC | UC-01 | US-001 | BRD §4 | TC-AUTH-001 | 🔴 Hoạt động |
| **FR-AUTH-002** | Tự động làm mới Token | UC-01 | US-001 | BRD §4 | TC-AUTH-002 | 🔴 Hoạt động |
| **FR-AUTH-003** | Đăng xuất khi hết hạn phiên rảnh | UC-01 | US-002 | BRD §4 | TC-AUTH-003 | 🟡 Đang dev |
| **FR-AUTH-004** | Kiểm tra quyền hạn Kong Gateway | UC-02 | US-003 | BRD §4 | TC-AUTH-004 | 🔴 Hoạt động |
| **FR-AUTH-005** | Giao diện CRUD Vai trò & Quyền | UC-02 | US-003 | BRD §4 | TC-AUTH-005 | 🔴 Hoạt động |
| **FR-AUTH-006** | Invalidate cache Redis tức thì | UC-02 | US-004 | BRD §4 | TC-AUTH-006 | 🔴 Hoạt động |
| **FR-AUTH-007** | Khởi tạo Organization & Admin Tenant mới | UC-03 | US-005 | BRD §1 | TC-AUTH-007 | 🔴 Hoạt động |
| **FR-AUTH-008** | Gửi email kích hoạt tài khoản | UC-03 | US-005 | BRD §1 | TC-AUTH-008 | 🔴 Hoạt động |
| **FR-AUTH-009** | Phân quyền mức Client (Scopes) | UC-01 | US-001 | BRD §4 | TC-AUTH-009 | 🟡 Đang dev |
| **FR-AUTH-010** | Phân tách Danh tính & Hồ sơ User | UC-01 | US-001 | BRD §4 | TC-AUTH-010 | 🔴 Hoạt động |
| **FR-AUTH-011** | Thu hồi Token và Session tức thời | UC-01 | US-002 | BRD §4 | TC-AUTH-011 | 🟢 Lên kế hoạch |
| **FR-AUTH-012** | Tự kích hoạt User (Lazy Sync) | UC-01 | US-001 | BRD §4 | TC-AUTH-012 | 🟢 Lên kế hoạch |
| **FR-AUTH-013** | Xác thực chữ ký Webhook (HMAC) | UC-02 | US-003 | BRD §4 | TC-AUTH-013 | 🟢 Lên kế hoạch |

| **FR-CH-001** | Kết nối Facebook Page qua OAuth | UC-04 | US-006 | BRD §5 | TC-CH-001 | 🔴 Hoạt động |
| **FR-CH-002** | Đăng ký Webhook Page Facebook | UC-04 | US-006 | BRD §5 | TC-CH-002 | 🔴 Hoạt động |
| **FR-CH-003** | Kết nối Zalo OA qua OAuth | UC-04 | US-007 | BRD §5 | TC-CH-003 | 🔴 Hoạt động |
| **FR-CH-004** | Background job quét rotate token | UC-05 | US-008 | BRD §5 | TC-CH-004 | 🔴 Hoạt động |
| **FR-CH-005** | Đổi trạng thái và cảnh báo Token lỗi | UC-05 | US-008 | BRD §5 | TC-CH-005 | 🔴 Hoạt động |
| **FR-CH-006** | Kết nối TikTok Business qua OAuth | UC-04 | US-070 | BRD §5 | TC-CH-006 | 🟡 Đang dev |
| **FR-CH-007** | Đăng ký Webhook TikTok | UC-04 | US-070 | BRD §5 | TC-CH-007 | 🟡 Đang dev |
| **FR-CH-008** | Gia hạn Token TikTok tự động | UC-05 | US-071 | BRD §5 | TC-CH-008 | 🟡 Đang dev |
| **FR-MSG-001** | Hiển thị Hộp thư hợp nhất | UC-06 | US-009 | BRD §6 | TC-MSG-001 | 🔴 Hoạt động |
| **FR-MSG-002** | Bộ lọc hội thoại nâng cao | UC-06 | US-010 | BRD §6 | TC-MSG-002 | 🔴 Hoạt động |
| **FR-MSG-003** | Truyền tin nhắn qua WebSocket <1s | UC-06 | US-011 | BRD §6 | TC-MSG-003 | 🔴 Hoạt động |
| **FR-MSG-004** | Gửi tin nhắn phản hồi khách hàng | UC-07 | US-012 | BRD §6 | TC-MSG-004 | 🔴 Hoạt động |
| **FR-MSG-005** | Retry gửi tin & đánh dấu `Failed` | UC-07 | US-012 | BRD §6 | TC-MSG-005 | 🔴 Hoạt động |
| **FR-MSG-006** | Khóa ô chat & chọn Tag ngoài 24h | UC-07 | US-013 | BRD §5 | TC-MSG-006 | 🟡 Đang dev |
| **FR-MSG-007** | Đổi Auto sang Manual khi Handoff | UC-08 | US-014 | BRD §6 | TC-MSG-007 | 🔴 Hoạt động |
| **FR-MSG-008** | Nhận diện tức giận để handoff khẩn | UC-08 | US-015 | BRD §3 | TC-MSG-008 | 🔴 Hoạt động |
| **FR-MSG-009** | Thuật toán phân bổ Hybrid Routing | UC-08 | US-016 | BRD §6 | TC-MSG-009 | 🟡 Đang dev |
| **FR-MSG-010** | Đóng hội thoại chuyển về Auto | UC-09 | US-017 | BRD §6 | TC-MSG-010 | 🔴 Hoạt động |
| **FR-MSG-011** | Tự động chuyển Auto sau 2h rảnh | UC-09 | US-017 | BRD §6 | TC-MSG-011 | 🟡 Đang dev |
| **FR-MSG-012** | Đẩy sự kiện trạng thái typing | UC-06 | US-009 | BRD §6 | TC-MSG-012 | 🟡 Đang dev |
| **FR-MSG-013** | Agent từ chối Handoff → đưa lại Queue | UC-08 | US-072 | BRD §6 | TC-MSG-013 | 🟢 Lên kế hoạch |
| **FR-CB-001** | Phân loại ý định khách hàng <200ms | UC-10 | US-018 | BRD §3 | TC-CB-001 | 🔴 Hoạt động |
| **FR-CB-002** | Sinh câu trả lời tự động bằng RAG | UC-10 | US-018 | BRD §3 | TC-CB-002 | 🔴 Hoạt động |
| **FR-CB-003** | Lưu state checkpoint LangGraph | UC-10 | US-019 | BRD §3 | TC-CB-003 | 🔴 Hoạt động |
| **FR-CB-004** | Kích hoạt handoff khi điểm tin cậy <0.7 | UC-08 | US-014 | BRD §3 | TC-CB-004 | 🔴 Hoạt động |
| **FR-CB-005** | Trích xuất ảnh hóa đơn bằng Vision | UC-11 | US-020 | BRD §3 | TC-CB-005 | 🟡 Đang dev |
| **FR-CB-006** | Handoff khi tắt tính năng Vision | UC-11 | US-021 | BRD §3 | TC-CB-006 | 🟡 Đang dev |
| **FR-CB-007** | Script Lead Capture ngoài giờ | UC-12 | US-022 | BRD §3 | TC-CB-007 | 🟡 Đang dev |
| **FR-CB-008** | Validate định dạng số điện thoại | UC-12 | US-022 | BRD §3 | TC-CB-008 | 🟡 Đang dev |
| **FR-CB-009** | Rào chắn đầu vào Semantic Router | UC-10 | US-018 | BRD §3 | TC-CB-009 | 🟡 Đang dev |
| **FR-CB-010** | Xác thực câu trả lời NLI Validator | UC-10 | US-018 | BRD §3 | TC-CB-010 | 🟡 Đang dev |
| **FR-CB-011** | Tự động tóm tắt tin nhắn lịch sử | UC-10 | US-019 | BRD §3 | TC-CB-011 | 🟡 Đang dev |
| **FR-CB-012** | Khóa Chatbot sau Lead Capture | UC-12 | US-068 | BRD §3 | TC-CB-012 | 🟡 Đang dev |
| **FR-CB-013** | Chào khách bằng tên MXH | UC-10 | US-018 | BRD §3 | TC-CB-013 | 🟢 Lên kế hoạch |
| **FR-CB-014** | Ghi nhận và gắn tag Chatbot Action | UC-10 | US-079 | BRD §3 | TC-CB-014 | 🟡 Đang dev |
| **FR-CB-015** | Log chi tiết Handoff Reason | UC-08 | US-080 | BRD §3 | TC-CB-015 | 🟡 Đang dev |
| **FR-KB-001** | Upload tài liệu PDF/DOCX <50MB | UC-13 | US-023 | BRD §3 | TC-KB-001 | 🔴 Hoạt động |
| **FR-KB-002** | Phân đoạn Semantic Chunking | UC-13 | US-023 | BRD §3 | TC-KB-002 | 🔴 Hoạt động |
| **FR-KB-003** | Embed vector lưu vào Qdrant với RLS | UC-13 | US-023 | BRD §3 | TC-KB-003 | 🔴 Hoạt động |
| **FR-KB-004** | Tìm kiếm hỗn hợp Hybrid (Vector+BM25) | UC-14 | US-024 | BRD §3 | TC-KB-004 | 🔴 Hoạt động |
| **FR-KB-005** | Reranking bge-reranker-v2-m3 | UC-14 | US-024 | BRD §3 | TC-KB-005 | 🔴 Hoạt động |
| **FR-KB-006** | Trả về Similarity Score tối đa | UC-14 | US-024 | BRD §3 | TC-KB-006 | 🟡 Đang dev |
| **FR-KB-007** | Xác thực Tenant ID nghiêm ngặt | UC-14 | US-024 | BRD §3 | TC-KB-007 | 🟡 Đang dev |
| **FR-CNT-001** | Sinh nội dung tiếp thị đa phiên bản | UC-15 | US-025 | BRD §3 | TC-CNT-001 | 🔴 Hoạt động |
| **FR-CNT-002** | Tích hợp brand voice của Tenant | UC-15 | US-025 | BRD §3 | TC-CNT-002 | 🔴 Hoạt động |
| **FR-CNT-003** | Đánh giá Quality Score bài viết | UC-15 | US-026 | BRD §3 | TC-CNT-003 | 🟡 Đang dev |
| **FR-CNT-004** | Chặn đăng bài khi score <0.7 | UC-15 | US-026 | BRD §3 | TC-CNT-004 | 🟡 Đang dev |
| **FR-CNT-005** | Luồng phê duyệt bài viết của Manager | UC-16 | US-027 | BRD §3 | TC-CNT-005 | 🟡 Đang dev |
| **FR-CNT-006** | Tự động duyệt bài đạt điểm >0.85 | UC-16 | US-028 | BRD §3 | TC-CNT-006 | 🟢 Lên kế hoạch |
| **FR-SCH-001** | Lên lịch đăng bài Quartz dynamic timezone | UC-17 | US-029 | BRD §5 | TC-SCH-001 | 🔴 Hoạt động |
| **FR-SCH-002** | Đăng bài tự động lên FB/TikTok Feed | UC-17 | US-029 | BRD §5 | TC-SCH-002 | 🔴 Hoạt động |
| **FR-SCH-003** | Đăng Zalo OA bằng Broadcast Message | UC-17 | US-029 | BRD §5 | TC-SCH-003 | 🔴 Hoạt động |
| **FR-SCH-004** | Retry đăng bài và chuyển `Draft_Failed` | UC-17 | US-030 | BRD §5 | TC-SCH-004 | 🔴 Hoạt động |
| **FR-SCH-005** | Giao diện Calendar View | UC-18 | US-031 | BRD §5 | TC-SCH-005 | 🟡 Đang dev |
| **FR-SCH-006** | Cập nhật Quartz DB bằng kéo thả | UC-18 | US-031 | BRD §5 | TC-SCH-006 | 🟡 Đang dev |
| **FR-CRM-001** | Tạo contact tự động từ hội thoại | UC-19 | US-032 | BRD §7 | TC-CRM-001 | 🔴 Hoạt động |
| **FR-CRM-002** | Hiển thị Timeline 360 độ khách hàng | UC-19 | US-032 | BRD §7 | TC-CRM-002 | 🔴 Hoạt động |
| **FR-CRM-003** | Che dấu SĐT & Email (Data Masking) | UC-19 | US-033 | BRD §10 | TC-CRM-003 | 🟡 Đang dev |
| **FR-CRM-004** | Tự động gộp Contact trùng SĐT & Tên | UC-20 | US-034 | BRD §7 | TC-CRM-004 | 🔴 Hoạt động |
| **FR-CRM-005** | Ghi Audit Log gộp dữ liệu khách hàng | UC-20 | US-034 | BRD §7 | TC-CRM-005 | 🔴 Hoạt động |
| **FR-CRM-006** | Tạo đề xuất gộp thủ công MergeSuggestion | UC-20 | US-035 | BRD §7 | TC-CRM-006 | 🔴 Hoạt động |
| **FR-CRM-007** | Giao diện Agent phê duyệt gộp thủ công | UC-20 | US-035 | BRD §7 | TC-CRM-007 | 🔴 Hoạt động |
| **FR-CRM-008** | Quản lý Deal Pipeline dạng Kanban | UC-33 | US-059, US-065 | BRD §2 | TC-CRM-008 | 🔴 Hoạt động |
| **FR-CRM-009** | Lập lịch khảo sát và Ghi nhận dữ liệu thực địa | UC-33 | US-060 | BRD §2 | TC-CRM-009 | 🔴 Hoạt động |
| **FR-CRM-010** | Tự động tính toán công suất và ROI Solar | UC-34 | US-061 | BRD §2 | TC-CRM-010 | 🔴 Hoạt động |
| **FR-CRM-011** | Tự động biên soạn và xuất Solar Proposal PDF | UC-34 | US-062 | BRD §2 | TC-CRM-011 | 🔴 Hoạt động |
| **FR-CRM-012** | Proposal PDF qua MCP | UC-33 | US-060 | BRD §2 | TC-PDF-001 | 🟡 Đang dev |
| **FR-CRM-013** | O&M Ticket qua MCP | UC-33 | US-061 | BRD §2 | TC-OM-001 | 🟡 Đang dev |
| **FR-CRM-020** | Tiếp nhận báo lỗi và Điều phối Ticket O&M | UC-35 | US-063, US-064 | BRD §2 | TC-CRM-012 | 🟡 Đang dev |
| **FR-CRM-021** | Tích hợp API HelioScope/OpenSolar | UC-34 | US-066 | BRD §2 | TC-CRM-013 | 🟢 Lên kế hoạch |
| **FR-CRM-014** | Gửi CSAT survey khi đóng O&M Ticket | UC-35 | US-067 | BRD §2 | TC-CRM-014 | 🟡 Đang dev |
| **FR-CRM-015** | Lead Scoring Engine tự động | UC-36 | US-073 | BRD §8 | TC-CRM-015 | 🟡 Đang dev |
| **FR-CRM-016** | Cảnh báo Hot Lead vượt ngưỡng | UC-36 | US-074 | BRD §8 | TC-CRM-016 | 🟡 Đang dev |
| **FR-CRM-017** | Cấu hình trọng số Lead Scoring | UC-36 | US-075 | BRD §8 | TC-CRM-017 | 🟡 Đang dev |
| **FR-CAM-001** | Gửi tin nhắn Broadcast theo Segment | UC-21 | US-036 | BRD §8 | TC-CAM-001 | 🟡 Đang dev |
| **FR-CAM-002** | Giãn và pause gửi khi lỗi rate limit | UC-21 | US-036 | BRD §8 | TC-CAM-002 | 🟡 Đang dev |
| **FR-CAM-003** | Lọc bỏ/tag tin nhắn Facebook ngoài 24h | UC-21 | US-037 | BRD §8 | TC-CAM-003 | 🟡 Đang dev |
| **FR-CAM-004** | Gửi thử nghiệm A/B Testing chiến dịch | UC-22 | US-038 | BRD §8 | TC-CAM-004 | 🟢 Lên kế hoạch |
| **FR-CAM-005** | Tự động chọn nội dung chiến thắng Winner | UC-22 | US-038 | BRD §8 | TC-CAM-005 | 🟢 Lên kế hoạch |
| **FR-ANL-001** | Ghi nhận metrics chuỗi thời gian | UC-23 | US-039 | BRD §8 | TC-ANL-001 | 🟡 Đang dev |
| **FR-ANL-002** | Trực quan hóa biểu đồ Analytics | UC-23 | US-039 | BRD §8 | TC-ANL-002 | 🟡 Đang dev |
| **FR-ANL-003** | Xuất báo cáo CSV/PDF | UC-23 | US-040 | BRD §8 | TC-ANL-003 | 🟢 Lên kế hoạch |
| **FR-ANA-001** | Lắng nghe sự kiện hội thoại từ Kafka | UC-39 | US-079 | BRD §8 | TC-ANA-001 | 🟡 Đang dev |
| **FR-ANA-002** | Lưu trữ RAG Metrics vào TimescaleDB | UC-39 | US-079 | BRD §8 | TC-ANA-002 | 🟡 Đang dev |
| **FR-ANA-003** | Đảm bảo tính duy nhất (Idempotent Consumer) | UC-39 | US-079 | BRD §8 | TC-ANA-003 | 🟡 Đang dev |
| **FR-ANA-004** | API thống kê hiệu năng RAG | UC-39 | US-079 | BRD §8 | TC-ANA-004 | 🟡 Đang dev |
| **FR-ANA-005** | API phát hiện khoảng trống tri thức | UC-40 | US-080 | BRD §8 | TC-ANA-005 | 🟡 Đang dev |
| **FR-ANA-006** | Bảo mật API bằng chữ ký HMAC | UC-02 | US-004 | BRD §8 | TC-ANA-006 | 🟡 Đang dev |
| **FR-ANA-007** | Phân quyền Dynamic RBAC đối với Analytics | UC-02 | US-003 | BRD §8 | TC-ANA-007 | 🟡 Đang dev |
| **FR-ANA-008** | Tự động đăng ký dịch vụ (Service Discovery) | UC-38 | US-041 | BRD §8 | TC-ANA-008 | 🟡 Đang dev |
| **FR-ANA-009** | Báo cáo định kỳ và AI Insights | UC-41 | US-080 | BRD §8 | TC-ANA-009 | 🟡 Đang dev |
| **FR-CFG-001** | Giao diện CRUD cấu hình Tenant | UC-24 | US-041 | BRD §8 | TC-CFG-001 | 🔴 Hoạt động |
| **FR-CFG-002** | Đồng bộ cấu hình nóng qua Redis Pub/Sub| UC-24 | US-041 | BRD §8 | TC-CFG-002 | 🔴 Hoạt động |
| **FR-CFG-003** | Thực hiện validate cấu hình đầu vào | UC-24 | US-042 | BRD §8 | TC-CFG-003 | 🔴 Hoạt động |
| **FR-CFG-004** | Giới hạn khoảng giá trị cấu hình | UC-24 | US-042 | BRD §8 | TC-CFG-004 | 🔴 Hoạt động |
| **FR-CMT-001** | Lắng nghe comment qua webhook Kafka | UC-25 | US-043 | BRD §5 | TC-CMT-001 | 🟡 Đang dev |
| **FR-CMT-002** | Tự động ẩn/xóa bình luận spam AI | UC-25 | US-043 | BRD §5 | TC-CMT-002 | 🟡 Đang dev |
| **FR-CMT-003** | Escalate bình luận tiêu cực về UI Agent | UC-25 | US-044 | BRD §5 | TC-CMT-003 | 🟡 Đang dev |
| **FR-CMT-004** | Tự động reply bình luận FAQ | UC-25 | US-043 | BRD §5 | TC-CMT-004 | 🟡 Đang dev |
| **FR-NOT-001** | Thông báo đẩy Web Push trên Dashboard | UC-08 | US-014 | BRD §6 | TC-NOT-001 | 🔴 Hoạt động |
| **FR-NOT-002** | Gửi email cảnh báo sự cố | UC-05 | US-008 | BRD §5 | TC-NOT-002 | 🔴 Hoạt động |
| **FR-NOT-003** | Lọc gửi alert theo kênh cấu hình | UC-24 | US-041 | BRD §8 | TC-NOT-003 | 🟡 Đang dev |
| **FR-DMS-001** | Tải lên tệp và xác thực định dạng tệp | UC-26 | US-045 | BRD §8 | TC-DMS-001 | 🔴 Hoạt động |
| **FR-DMS-002** | Kiểm tra hạn mức dung lượng Tenant | UC-26 | US-048 | BRD §8 | TC-DMS-002 | 🔴 Hoạt động |
| **FR-DMS-003** | Quản lý cấu trúc thư mục ảo | UC-27 | US-046 | BRD §8 | TC-DMS-003 | 🟡 Đang dev |
| **FR-DMS-004** | Cập nhật di chuyển kéo thả folder/file | UC-27 | US-046 | BRD §8 | TC-DMS-004 | 🟡 Đang dev |
| **FR-DMS-005** | Phân quyền truy cập Public/Private | UC-28 | US-047 | BRD §8 | TC-DMS-005 | 🔴 Hoạt động |
| **FR-DMS-006** | Sinh Presigned URL tải file Private 15p | UC-28 | US-050 | BRD §8 | TC-DMS-006 | 🟡 Đang dev |
| **FR-DMS-007** | Tự động tạo phiên bản mới trùng tên | UC-29 | US-049 | BRD §8 | TC-DMS-007 | 🟡 Đang dev |
| **FR-DMS-008** | Dọn dẹp version cũ quá giới hạn N | UC-29 | US-049 | BRD §8 | TC-DMS-008 | 🟡 Đang dev |
| **FR-SHR-001** | Tự động rút gọn liên kết Campaign | UC-30 | US-051 | BRD §8 | TC-SHR-001 | 🔴 Hoạt động |
| **FR-SHR-002** | Chuyển hướng click và ghi nhận event | UC-30 | US-051, US-052 | BRD §8 | TC-SHR-002 | 🔴 Hoạt động |
| **FR-SHR-003** | Xử lý click sai mã hoặc hết hạn | UC-30 | US-052 | BRD §8 | TC-SHR-003 | 🟡 Đang dev |
| **FR-MED-001** | Tự động nén dung lượng hình ảnh | UC-31 | US-053 | BRD §8 | TC-MED-001 | 🟡 Đang dev |
| **FR-MED-002** | Tự động tạo ảnh thu nhỏ (Thumbnails) | UC-31 | US-054 | BRD §8 | TC-MED-002 | 🟡 Đang dev |
| **FR-MED-003** | Chuyển mã video tương thích MXH | UC-31 | US-055 | BRD §8 | TC-MED-003 | 🟡 Đang dev |
| **FR-RET-001** | Quét và đóng gói dữ liệu cũ sang Parquet | UC-32 | US-056 | BRD §8 | TC-RET-001 | 🟡 Đang dev |
| **FR-RET-002** | Xóa dữ liệu cũ khỏi DB hoạt động | UC-32 | US-057 | BRD §8 | TC-RET-002 | 🟡 Đang dev |
| **FR-RET-003** | Ghi nhận sự kiện dọn dẹp kiểm toán | UC-32 | US-058 | BRD §8 | TC-RET-003 | 🟡 Đang dev |
| **FR-AI-001** | Cổng kết nối MCP Gateway đa tenant | UC-10 | US-018 | BRD §3 | TC-AI-001 | 🟡 Đang dev |
| **FR-AI-002** | Roots Security Boundary cho MCP | UC-10 | US-018 | BRD §3 | TC-AI-002 | 🟡 Đang dev |
| **FR-AI-003** | Duyệt hành động nhạy cảm có cấu hình | UC-08, UC-33 | US-014, US-060 | BRD §3 | TC-AI-003 | 🟡 Đang dev |
| **FR-AI-004** | Prompt Caching tối ưu chi phí AI | UC-10 | US-069 | BRD §3 | TC-AI-004 | 🟡 Đang dev |
| **FR-AI-005** | Định tuyến mô hình động | UC-10 | US-018 | BRD §3 | TC-AI-005 | 🟡 Đang dev |
| **FR-AI-006** | Khóa API Tenant (BYOK) | UC-10 | US-018 | BRD §3 | TC-AI-006 | 🟡 Đang dev |
| **FR-AI-007** | Báo cáo & giả lập chi phí | UC-10 | US-018 | BRD §3 | TC-AI-007 | 🟡 Đang dev |
| **FR-AI-008** | Hot-reload Redis Pub/Sub | UC-10 | US-018 | BRD §3 | TC-AI-008 | 🟡 Đang dev |
| **FR-AI-009** | Cảnh báo chi phí vượt hạn mức | UC-10 | US-069 | BRD §3 | TC-AI-009 | 🟡 Đang dev |
| **FR-AI-010** | Bảng giá LLM mặc định hệ thống | UC-10 | US-018 | BRD §3 | TC-AI-010 | 🟡 Đang dev |
| **FR-AI-011** | Phòng vệ model bị khai tử | UC-10 | US-018 | BRD §3 | TC-AI-011 | 🟡 Đang dev |
| **FR-AI-012** | Tự động khởi tạo LLM config | UC-10 | US-018 | BRD §3 | TC-AI-012 | 🟡 Đang dev |
| **FR-AI-014** | API /models động từ Registry | UC-10 | US-018 | BRD §3 | TC-AI-014 | 🟡 Đang dev |
| **FR-AI-015** | Bộ nhớ đệm ngữ nghĩa (Semantic Cache) | UC-10 | US-018 | BRD §3 | TC-CACHE-001 | 🟡 Đang dev |
| **FR-AI-016** | Query Rewriting cho Multi-turn | UC-10 | US-078 | BRD §3 | TC-AI-016 | 🟡 Đang dev |
| **FR-AI-017** | Query Rewrite Cache | UC-10 | US-078 | BRD §3 | TC-AI-017 | 🟡 Đang dev |
| **FR-AI-018** | Phát sự kiện Conversation Completed sang Kafka | UC-10 | US-079 | BRD §3 | TC-AI-018 | 🟡 Đang dev |
| **FR-SEC-001** | Consent popup NĐ 13/2023 | UC-37 | US-076 | BRD §10 | TC-SEC-001 | 🟡 Đang dev |
| **FR-SEC-002** | Right to Erasure (xóa dữ liệu KH) | UC-38 | US-077 | BRD §10 | TC-SEC-002 | 🟡 Đang dev |

---

## 11.2. Ánh xạ BRD Section ↔ Phân hệ SRS

| BRD § | Tiêu đề BRD | Phân hệ SRS liên quan | FR Modules |
|-------|-------------|----------------------|------------|
| §1 | Mục tiêu & Đặc thù nghiệp vụ | AUTH (Onboarding Tenant) | FR-AUTH-007~008 |
| §2 | 3 Quy trình Solar cốt lõi | CRM (Deal, Survey, ROI, O&M) | FR-CRM-008~014 |
| §3 | Trợ lý ảo AI (Chatbot) | CB, KB, AI, CNT | FR-CB-001~013, FR-KB-*, FR-AI-*, FR-CNT-* |
| §4 | Phân quyền RBAC & Scopes | AUTH | FR-AUTH-001~006, 009 |

| §5 | Tích hợp Kênh MXH | CH, SCH, CMT | FR-CH-001~008, FR-SCH-*, FR-CMT-* |
| §6 | Điều phối Tin nhắn & Ngoài giờ | MSG, NOT | FR-MSG-001~013, FR-NOT-* |
| §7 | Gộp Hồ sơ KH (Contact Merge) | CRM | FR-CRM-001~007 |
| §8 | Cấu hình Động Tenant Config | CFG, CAM, ANL, DMS, SHR, MED, RET | FR-CFG-*, FR-CAM-*, FR-ANL-*, FR-DMS-*, FR-SHR-*, FR-MED-*, FR-RET-*, FR-CRM-015~017 |
| §9 | Phần cứng & Chi phí | NFR (06_NonFunctional_Requirements.md) | — |
| §10 | Bảo mật & Pháp lý | SEC, CRM (Masking) | FR-SEC-001~002, FR-CRM-003 |
| §11 | Mẫu Duyệt tài liệu (Sign-off) | — (Quy trình ngoài phần mềm) | — |

---

*← [Trước: Standards & Resilience](./10_Standards_Resilience.md) | [Về Mục lục](./00_SRS_Index.md) | [Tiếp: Appendices →](./12_Appendices.md)*

