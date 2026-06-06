# 6. YÊU CẦU PHI CHỨC NĂNG (NON-FUNCTIONAL REQUIREMENTS)

> Phần này tuân thủ cấu trúc IEEE 830-1998 Section 3.2 - 3.5 và tiêu chuẩn chất lượng phần mềm ISO/IEC 25010:2011. Các yêu cầu phi chức năng được phân loại rõ ràng và gắn mã định danh duy nhất `NFR-[XXX]`.

---

## 6.1. Hiệu năng & Khả năng đáp ứng (Performance Efficiency - NFR-PER)

### NFR-PER-001: Thời gian phản hồi của API (API Response Time)
- **Mô tả:** Thời gian phản hồi (Response Time) của Kong API Gateway cho các yêu cầu HTTP/gRPC nội bộ (không bao gồm kết nối AI bên ngoài và webhook MXH) **PHẢI** đạt:
  - Dưới 200 mili-giây (ms) đối với 95% số lượng requests (p95).
  - Dưới 500 mili-giây (ms) đối với 99% số lượng requests (p99).
- **Phép đo:** Hệ thống giám sát Jaeger và Prometheus exporter tại API Gateway.

### NFR-PER-002: Thời gian phản hồi của Chatbot AI (AI Response Latency)
- **Mô tả:** Thời gian chatbot phản hồi lại khách hàng kể từ lúc nhận được webhook (bao gồm trích xuất intent, tìm kiếm RAG, và gọi API LLM sinh câu trả lời) **PHẢI** đạt:
  - Dưới 3.0 giây đối với câu hỏi thông thường (FAQ) sử dụng mô hình GPT-4o-mini.
  - Dưới 5.0 giây đối với các câu hỏi phức tạp hoặc có chứa hình ảnh/tài liệu.
- **Phép đo:** Thời gian log ghi nhận từ khi nhận webhook `channel.message.received` đến khi gửi đi qua `channel.message.sent`.

### NFR-PER-003: Thời gian sinh nội dung (Content Generation Latency)
- **Mô tả:** Thời gian Content Service gọi LLM (Claude 3.5 Sonnet) để sinh và định dạng xong bài viết đa phiên bản **PHẢI** dưới 15 giây.
- **Phép đo:** Kiểm tra hiệu năng tải API của Content Service.

### NFR-PER-004: Khả năng chịu tải đồng thời (Throughput & Concurrency)
- **Mô tả:** Mỗi microservice trong hệ thống **PHẢI** có khả năng xử lý tối thiểu 1,000 yêu cầu đồng thời trên giây (Requests Per Second - RPS) trong điều kiện tài nguyên tiêu chuẩn (2 Core CPU, 4GB RAM).
- **Phép đo:** Tải kiểm thử (Load testing) bằng công cụ K6 hoặc Locust.

---

## 6.2. Khả năng mở rộng (Scalability - NFR-SCA)

### NFR-SCA-001: Mở rộng hàng ngang (Horizontal Scaling)
- **Mô tả:** Tất cả 15 microservices **PHẢI** được thiết kế ở dạng stateless (không lưu trạng thái phiên làm việc cục bộ) để có thể tự động mở rộng hàng ngang (scale-out) bằng Kubernetes Horizontal Pod Autoscaler (HPA) khi mức tiêu thụ CPU > 70% hoặc RAM > 80%.
- **Ràng buộc:** Trạng thái session, cache và lock phân tán bắt buộc phải lưu trữ tập trung trên Redis Cluster.

### NFR-SCA-002: Khả năng mở rộng của Message Broker (Kafka Partitions)
- **Mô tả:** Các Kafka Topics chính (ví dụ: `channel.message.received`) **PHẢI** được cấu hình tối thiểu 3 partitions và 3 replication factors để hỗ trợ chạy song song nhiều instances của Consumer Service mà không xảy ra xung đột hoặc mất thứ tự xử lý sự kiện trong cùng một Tenant.

---

## 6.3. Độ tin cậy & Khả năng chịu lỗi (Reliability & Fault Tolerance - NFR-REL)

### NFR-REL-001: Cam kết thời gian hoạt động liên tục (Uptime SLA)
- **Mô tả:** Hệ thống **PHẢI** đảm bảo tính sẵn sàng cao (High Availability) với thời gian hoạt động liên tục (Uptime) tối thiểu đạt 99.9% hàng năm (tương đương tổng thời gian dừng hoạt động ngoài dự kiến không quá 8.76 giờ/năm).
- **Phép đo:** Uptime robot/Grafana alerts theo dõi API endpoints.

### NFR-REL-002: Khả năng chịu lỗi dịch vụ phụ thuộc (Circuit Breaker Pattern)
- **Mô tả:** Các cuộc gọi đồng bộ REST/gRPC giữa các services nội bộ (ví dụ: Chatbot gọi AI Core) hoặc gọi ra API ngoại vi **PHẢI** được bọc trong một Circuit Breaker (sử dụng Resilience4j hoặc Opossum).
- **Quy tắc kích hoạt:** Circuit Breaker **PHẢI** chuyển sang trạng thái `Open` (ngắt kết nối trực tiếp và trả về fallback) nếu tỷ lệ cuộc gọi lỗi > 50% hoặc thời gian phản hồi > 10 giây trong cửa sổ trượt 20 lần gọi.

### NFR-REL-003: Nhất quán dữ liệu phân tán (Transactional Consistency)
- **Mô tả:** Các luồng nghiệp vụ liên kết nhiều services **PHẢI** thực thi Saga Pattern thông qua Kafka Event-driven. Hệ thống **PHẢI** đảm bảo tính toàn vẹn dữ liệu bằng cách thực hiện các compensating transactions để đảo ngược trạng thái (rollback logic) ở các service phía trước nếu một bước ở phía sau bị lỗi nghiêm trọng.

---

## 6.4. An toàn & Bảo mật thông tin (Security & Privacy - NFR-SEC)

### NFR-SEC-001: Cô lập dữ liệu đa người thuê (Multi-tenant Isolation)
- **Mô tả:** Hệ thống **PHẢI** ngăn chặn tuyệt đối hiện tượng rò rỉ dữ liệu chéo giữa các Tenants (Data Leakage). 
- **Giải pháp:**
  - Ở tầng cơ sở dữ liệu Postgres: Áp dụng PostgreSQL Row-Level Security (RLS) bắt buộc trên tất cả các bảng. Mọi truy vấn SQL từ ứng dụng **PHẢI** thực thi dưới context `tenant_id` của phiên làm việc.
  - Ở tầng Vector DB (Qdrant): Mọi câu lệnh tìm kiếm ngữ cảnh **PHẢI** áp dụng metadata filter `tenant_id`.
  - Ở tầng Object Storage (MinIO): Lưu trữ tệp tách biệt theo cấu trúc thư mục `{tenant_id}/...`.

### NFR-SEC-002: Mã hóa dữ liệu truyền tải (Data in Transit)
- **Mô tả:** Tất cả các luồng giao tiếp bên ngoài và giữa Dashboard tới Kong Gateway **PHẢI** sử dụng giao thức bảo mật HTTPS/WSS mã hóa TLS 1.3 (tương thích ngược TLS 1.2). Mọi kết nối nội bộ giữa các microservices qua gRPC, REST, Kafka, Redis, Postgres **PHẢI** được mã hóa bằng SSL/TLS.

### NFR-SEC-003: Mã hóa dữ liệu lưu trữ (Data at Rest)
- **Mô tả:** Các thông tin nhạy cảm lưu trữ trong cơ sở dữ liệu bao gồm: Page/OA Access Token, API keys bên thứ ba, mật khẩu dịch vụ, thông tin cá nhân khách hàng **PHẢI** được mã hóa bằng thuật toán đối xứng AES-256 ở mức ứng dụng trước khi ghi xuống đĩa cứng vật lý.

### NFR-SEC-004: Che dấu dữ liệu cá nhân (GDPR & Data Masking Compliance)
- **Mô tả:** Để bảo vệ quyền riêng tư của khách hàng, hệ thống **PHẢI** cung cấp tính năng che dấu dữ liệu (Data Masking) cho các trường thông tin Số điện thoại và Email khi hiển thị cho Agent (chỉ Admin hoặc người có quyền xem thô mới được mở khóa xem đầy đủ).

### NFR-SEC-005: Xác thực Chữ ký Quyền hạn Downstream (Downstream Permission Signature Verification)
- **Mô tả:** Để ngăn chặn hoàn toàn nguy cơ giả mạo Header (Header Spoofing) trong mạng nội bộ, tất cả các microservices nghiệp vụ (downstream services) khi nhận request **PHẢI** xác thực chữ ký HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng cách tính toán lại chữ ký từ các header `X-Tenant-ID`, `X-User-ID`, `X-User-Permissions` và khóa bí mật `GATEWAY_SIGNING_SECRET`. Bất kỳ request nào không khớp chữ ký **PHẢI** bị từ chối ngay lập tức với mã lỗi `403 Forbidden`. Thời gian xử lý của lớp bảo vệ này **PHẢI** dưới 2 mili-giây (ms) để không ảnh hưởng đến hiệu năng chung của hệ thống.
- **Phép đo:** Tracing log của middleware/guard đo bằng OpenTelemetry.

---

## 6.5. Tính khả dụng & Trải nghiệm người dùng (Usability - NFR-USA)

### NFR-USA-001: Khả năng tương thích thiết bị (Responsive Design)
- **Mô tả:** Giao diện Unified Inbox và Dashboard **PHẢI** hiển thị tương thích tốt trên nhiều loại màn hình khác nhau (Desktop độ phân giải từ 1280px trở lên, Tablet độ phân giải từ 768px trở lên) và tối ưu hóa giao diện di động (Mobile Web) cho các tác vụ chat khẩn cấp của Agent.

### NFR-USA-002: Khả năng tương thích trình duyệt (Browser Compatibility)
- **Mô tả:** Dashboard **PHẢI** chạy ổn định và hiển thị nhất quán trên 4 trình duyệt phổ biến nhất hiện nay: Google Chrome, Apple Safari, Mozilla Firefox và Microsoft Edge (bao gồm các phiên bản phát hành trong vòng 2 năm gần nhất).

### NFR-USA-003: Khả năng tiếp cận (Accessibility Compliance)
- **Mô tả:** Hệ thống **NÊN** tuân thủ các quy tắc thiết kế giao diện dễ tiếp cận Web Content Accessibility Guidelines (WCAG) 2.1 cấp độ AA nhằm hỗ trợ người dùng có khiếm khuyết nhẹ về thị lực (độ tương phản màu sắc chữ tối thiểu 4.5:1, hỗ trợ zoom màn hình lên 200% không bị vỡ layout).

---

## 6.6. Khả năng bảo trì & Phát triển (Maintainability & Portability - NFR-MNT)

### NFR-MNT-001: Tự động hóa cập nhật lược đồ cơ sở dữ liệu (Database Migrations)
- **Mô tả:** Mọi thay đổi về cấu trúc bảng (schema changes) của các database **PHẢI** được quản lý bằng các công cụ migration tự động (Liquibase cho Java, Prisma/Knex cho Node.js, Alembic cho Python).
- **Ràng buộc:** Các file script migration **PHẢI** được thiết kế tương thích ngược để có thể triển khai hệ thống mà không cần tắt ứng dụng (zero-downtime rolling deployment).

### NFR-MNT-002: Đóng gói và Triển khai độc lập (Containerization)
- **Mô tả:** Toàn bộ 15 microservices và các thành phần hạ tầng **PHẢI** được đóng gói dưới dạng các Docker Images độc lập, nhẹ (sử dụng base image Alpine hoặc Distroless) và sẵn sàng triển khai trên môi trường Kubernetes thông qua Helm Charts.

### NFR-MNT-003: Quản lý phiên bản API (API Versioning)
- **Mô tả:** Tất cả các REST API endpoints công khai hoặc nội bộ của hệ thống **PHẢI** được đánh phiên bản thông qua tiền tố URL (ví dụ: `/api/v1/conversations`, `/api/v2/...`). Phiên bản API cũ **PHẢI** được duy trì hỗ trợ tối thiểu 6 tháng kể từ khi phiên bản mới được release và thông báo deprecation.

---

*← [Trước: Functional Requirements](./05_Functional_Requirements.md) | [Về Mục lục](./00_SRS_Index.md) | [Tiếp: External Interfaces →](./07_External_Interfaces.md)*
