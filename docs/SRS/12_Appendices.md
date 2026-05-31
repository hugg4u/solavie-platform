# 12. PHỤ LỤC (APPENDICES)

> Phần này tuân thủ cấu trúc IEEE 830-1998 Section 5. Cung cấp các thông tin bổ trợ quan trọng bao gồm Thuật ngữ glossary mở rộng, Danh mục các bên liên quan và phê duyệt, Tài liệu tham chiếu, và Mẫu yêu cầu thay đổi (Change Request Template).

---

## 12.1. Phụ lục A: Thuật ngữ mở rộng (Glossary)

Dưới đây là định nghĩa chi tiết của các thuật ngữ chuyên môn và chữ viết tắt sử dụng trong tài liệu SRS này:

| Thuật ngữ | Viết tắt | Định nghĩa chi tiết |
|-----------|----------|---------------------|
| **OpenID Connect** | OIDC | Giao thức xác thực xây dựng trên nền tảng OAuth 2.0, được Keycloak sử dụng để cấp phát ID Token và Access Token. |
| **Row-Level Security** | RLS | Cơ chế bảo mật cấp dòng trong PostgreSQL, dùng để cô lập dữ liệu multi-tenant bằng cách tự động áp filter theo ID của Tenant. |
| **Retrieval-Augmented Generation** | RAG | Kỹ thuật kết hợp giữa mô hình ngôn ngữ lớn (LLM) với cơ sở tri thức ngoài để cải thiện độ chính xác và giảm thiểu hiện tượng ảo tưởng của AI. |
| **Model Context Protocol** | MCP | Giao thức mở chuẩn hóa cách thức tích hợp công cụ (Tools) và nguồn tài nguyên (Resources) từ hệ thống bên ngoài vào mô hình AI. |
| **Requirements Traceability Matrix** | RTM | Ma trận truy vết yêu cầu liên kết các thực thể từ Yêu cầu kinh doanh (BRD), Yêu cầu chức năng (FR), Use Case (UC) đến Kịch bản kiểm thử (TC). |
| **Document Management System** | DMS | Hệ thống quản lý tài liệu, tệp tin tập trung cho các doanh nghiệp, quản lý thư mục ảo, phân quyền và lịch sử phiên bản tệp tin. |
| **Official Account** | OA | Tài khoản chính thức của doanh nghiệp trên Zalo, tương tự như Fanpage trên Facebook. |
| **Response Time** | RT | Khoảng thời gian từ khi hệ thống nhận được yêu cầu đến khi gửi đi phản hồi đầu tiên cho Client. |
| **Horizontal Pod Autoscaler** | HPA | Thành phần trong Kubernetes tự động điều chỉnh số lượng Pods chạy dịch vụ dựa trên mức sử dụng CPU/RAM thực tế. |
| **Software-as-a-Service** | SaaS | Mô hình phân phối phần mềm trong đó nhà cung cấp cấp quyền sử dụng ứng dụng cho khách hàng (Tenants) thông qua internet dưới dạng dịch vụ trả phí định kỳ. |
| **Reciprocal Rank Fusion** | RRF | Thuật toán xếp hạng kết hợp kết quả từ nhiều công cụ tìm kiếm khác nhau (ví dụ: Vector search và BM25 search) thành một danh sách xếp hạng duy nhất. |
| **Single Page Application** | SPA | Ứng dụng web tải một trang HTML duy nhất và tự động cập nhật nội dung động mà không cần tải lại toàn bộ trang từ máy chủ. |
| **Application Load Balancer** | ALB | Bộ cân bằng tải hoạt động ở tầng ứng dụng (Layer 7) điều hướng lưu lượng truy cập HTTP/HTTPS tới các container thích hợp trong Kubernetes. |
| **Identity Provider** | IdP | Hệ thống quản lý thông tin định danh và cung cấp dịch vụ xác thực người dùng cho các ứng dụng tin cậy (Keycloak). |
| **Json Web Token** | JWT | Chuỗi ký tự mã hóa Base64 chứa các thông tin định danh (claims) đã được ký số, dùng để xác thực các request API. |
| **Event-Driven Architecture** | EDA | Kiến trúc phần mềm trong đó các thành phần giao tiếp với nhau bằng cách tạo ra và tiêu thụ các sự kiện (Events) bất đồng bộ. |
| **Time-to-Live** | TTL | Khoảng thời gian tồn tại tối đa của một bản ghi cache hoặc đường dẫn liên kết trước khi bị tự động xóa bỏ hoặc hết hiệu lực. |
| **Click-Through Rate** | CTR | Tỷ lệ nhấp chuột — Tỷ lệ phần trăm số lượt nhấp chuột trên tổng số lượt tin nhắn chứa link gửi đi thành công. |
| **Transcoding** | - | Quá trình chuyển mã đa phương tiện — Giải nén, tối ưu hóa và mã hóa lại tệp video/image sang định dạng tiêu chuẩn. |
| **Cold Storage** | - | Lưu trữ lạnh — Phương thức lưu trữ dữ liệu lịch sử nén ít truy cập nhằm tiết kiệm chi phí đĩa cứng cho hot databases. |

---

## 12.2. Phụ lục B: Danh sách Stakeholders & Sign-off

Tài liệu này được đồng thuận và phê duyệt bởi các bên liên quan sau. Chữ ký xác nhận đại diện cho việc đồng ý với toàn bộ nội dung yêu cầu mô tả trong tài liệu SRS này:

| Vai trò dự án | Họ và tên | Chức vụ | Ngày ký | Chữ ký |
|---------------|-----------|---------|---------|--------|
| **Product Owner** | Nguyễn Văn A | Trưởng phòng Sản phẩm | ____/____/2026 | |
| **Technical Lead** | Trần Văn B | Trưởng nhóm Kỹ thuật | ____/____/2026 | |
| **QA Lead** | Phạm Thị C | Trưởng nhóm Kiểm thử | ____/____/2026 | |
| **Project Manager** | Lê Văn D | Quản lý Dự án | ____/____/2026 | |

---

## 12.3. Phụ lục C: Tài liệu tham chiếu (References)

1. **IEEE Std 830-1998:** *IEEE Recommended Practice for Software Requirements Specifications.*
2. **ISO/IEC/IEEE 29148:2018:** *Systems and software engineering — Life cycle processes — Requirements engineering.*
3. **RFC 2119:** *Key words for use in RFCs to Indicate Requirement Levels.*
4. **Business Requirements Document (BRD):** [Tài liệu Yêu cầu Nghiệp vụ BRD.md](../BRD.md)
5. **BA Interview Notes:** [Tài liệu Ghi chép BA Interview.md](../BA_Interview_Questions.md)

---

## 12.4. Phụ lục D: Mẫu Nhật ký yêu cầu thay đổi (Change Request Log Template)

Mọi thay đổi phát sinh sau khi tài liệu SRS này được ký duyệt **PHẢI** được ghi nhận thông qua Change Request Log dưới đây để kiểm soát phiên bản:

| CR ID | Ngày yêu cầu | Người yêu cầu | Mô tả thay đổi đề xuất | Lý do thay đổi | Tác động ước lượng | Trạng thái duyệt |
|-------|--------------|---------------|------------------------|----------------|--------------------|-------------------|
| *CR-001* | *05/06/2026* | *Product Owner* | *Bổ sung thêm kênh tích hợp Viber OA.* | *Yêu cầu mở rộng thị trường khách hàng doanh nghiệp.* | *Ảnh hưởng tới Channel Connector, Database, và Messaging Service.* | *Đang đánh giá* |
| | | | | | | |
| | | | | | | |

---

*← [Trước: Traceability Matrix](./11_Traceability_Matrix.md) | [Về Mục lục](./00_SRS_Index.md)*
