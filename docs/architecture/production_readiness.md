# Production Readiness & Architecture Migration Guide

Tài liệu này ghi nhận các quyết định kiến trúc và hướng dẫn chuyển đổi hệ thống **Solavie Marketing Platform** từ phiên bản thử nghiệm (Local Dev / MVP) sang phiên bản sản phẩm thực tế (**Production-ready SaaS**).

---

## 1. Nâng cấp API Gateway (Kong Gateway)

### Quyết định Kiến trúc: Lựa chọn Kong DB-Mode cho Production
Hệ thống Solavie chính thức lựa chọn **Phương án A: Chuyển sang DB Mode** cho môi trường Production để loại bỏ hoàn toàn các rủi ro nghẽn CPU và gián đoạn kết nối của khách hàng khi reload cấu hình.

1.  **Dựng Database riêng cho Kong**: Dùng một instance PostgreSQL (hoặc schema riêng `kong_db`) để lưu trữ cấu hình động của Kong.
2.  **Quản trị qua REST Admin API**: Khi có Tenant mới đăng ký (Onboarding) hoặc khi Service Discovery cập nhật Upstream targets:
    *   Hệ thống Provisioning Service hoặc Sync Daemon sẽ gọi REST API trực tiếp tới cổng Admin API của Kong (`:8001`) để đăng ký các Upstream targets, Services, Routes.
    *   **Ưu điểm**: Mọi thay đổi cấu hình có hiệu lực tức thời, không cần reload hay restart Gateway, đảm bảo tính liên tục của hệ thống (High Availability).
3.  **Kích hoạt Native Healthchecks**: Cấu hình active và passive healthchecks trực tiếp trong Upstream của Kong. Thiết lập ngưỡng tự động ngắt kết nối (Circuit Breaker) khi một target bị lỗi liên tiếp quá 3 lần, giúp tự động gỡ bỏ các node chết trong vòng dưới 1 giây.

---

## 2. Quy hoạch Dịch vụ Người dùng (User Service vs HRM)

### Hiện trạng (Local Dev)
*   `user-service` quản lý hồ sơ nghiệp vụ của nhân viên (Hybrid Profile) phục vụ cho nền tảng Marketing.

### Định hướng Production
*   **Tuyệt đối không gộp chung nghiệp vụ nhân sự chuyên sâu (HRM)** vào `user-service`.
*   **Kiến trúc đề xuất**:
    *   **`user-service`**: Giữ vai trò là dịch vụ IAM Core tinh gọn (quản lý Name, Avatar, Roles, Status hoạt động và bộ tùy chọn Preferences).
    *   **`hrm-service`**: Xây dựng thành một Microservice hoàn toàn độc lập, sở hữu cơ sở dữ liệu riêng để quản lý thông tin chấm công, lương thưởng (payroll), hợp đồng lao động, KPIs bảo mật.
    *   **Liên kết**: Hai dịch vụ liên kết với nhau lỏng lẻo thông qua mã **User UUID** (`sub` claim từ Keycloak). Khi `user-service` có sự kiện thay đổi trạng thái user (như khóa/mở khóa), nó sẽ publish sự kiện qua Kafka để `hrm-service` cập nhật trạng thái tương ứng.

---

## 3. Đồng bộ cấu hình qua Event Streaming tin cậy với Kafka

### Hiện trạng (Local Dev)
*   Sử dụng Redis Pub/Sub và Redis Streams đơn giản trên 1 node Redis duy nhất.

### Định hướng Production
1.  **Hạ tầng truyền tin**: Chuyển đổi hoàn toàn cơ chế đồng bộ tin cậy từ Redis Streams sang cụm **Apache Kafka Cluster** (sử dụng tối thiểu 3 Brokers trong chế độ KRaft để loại bỏ single point of failure).
2.  **Đảm bảo Idempotency**: Thiết lập cơ chế nhận tin và xử lý sự kiện trùng lặp (Idempotent Consumer) tại các downstream services.
3.  **Tách biệt Topic theo chức năng**: Cấu hình các topic riêng biệt cho từng luồng nghiệp vụ (`auth.events.user`, `token.revoked`, `config.updates`, `scheduler.post.due`, `notification.send`, `audit.events`) với tối thiểu 3 partitions mỗi topic.

---

## 4. Chiến lược Triển khai Kubernetes (K8s) Song Song

Để tối ưu hóa tốc độ phát triển và tính ổn định khi scale, Solavie áp dụng chiến lược **"Dev on Compose, Deploy on K8s"**:

1.  **Local Development (Docker Compose):** Giữ nguyên Docker Compose cho lập trình viên để tận dụng tính năng hot-reload và phản hồi nhanh khi viết code.
2.  **Môi trường Staging/UAT & Production (Kubernetes):**
    *   Sử dụng **Helm Charts** để quản lý các stateful infra (Postgres, Redis Cluster, Kafka).
    *   Viết K8s Manifests (Deployment, Service, Ingress) cho 20 microservices.
    *   Sử dụng **Kong Ingress Controller** để tự động đồng bộ hóa Endpoint của K8s Service vào bảng định tuyến của Kong Gateway ngay khi Pod được sinh ra hoặc biến mất, thay thế cho script sync registry tự chế.

---

## 5. Checklist Sẵn Sàng Vận Hành Cụm Kafka (Production Kafka Readiness Checklist)

Để triển khai Apache Kafka an toàn trên môi trường Production, nhóm vận hành (DevOps/SRE) bắt buộc tuân thủ các quy tắc cấu hình và giám sát sau:

### 5.1. Cấu hình Hạ tầng & Độ tin cậy (Infrastructure & Reliability)
- [ ] **Multi-Broker Setup:** Sử dụng tối thiểu 3 Kafka Brokers chạy KRaft mode, phân bố trên các Availability Zones (AZs) khác nhau.
- [ ] **Replication Factor:** Tất cả các production topics bắt buộc cấu hình `replication.factor = 3`.
- [ ] **Min In-Sync Replicas:** Cấu hình `min.insync.replicas = 2` kết hợp với producer option `acks = all`.
- [ ] **Retention Policy:** Thiết lập thời gian lưu trữ dữ liệu mặc định `log.retention.hours = 168` (7 ngày).

### 5.2. Bảo mật Cụm Kafka (Security Hardening)
- [ ] **Encryption in Transit:** Kích hoạt giao thức mã hóa TLS (SSL) cho toàn bộ kết nối.
- [ ] **Authentication:** Áp dụng cơ chế xác thực SASL/SCRAM hoặc SASL/GSSAPI.
- [ ] **Authorization (ACLs):** Thiết lập chính sách phân quyền chi tiết (Kafka ACLs) giới hạn quyền Read/Write của từng service.
- [ ] **Network Isolation:** Đặt cụm Kafka vào mạng nội bộ (Private VPC).

### 5.3. Giám sát & Cảnh báo (Observability & Alerting)
- [ ] **Consumer Lag Monitoring:** Tích hợp Burrow hoặc Prometheus JMX Exporter để giám sát lag.
- [ ] **Disk Usage Alert:** Thiết lập cảnh báo dung lượng ổ đĩa ở mức 70% (Warning) và 85% (Critical).
- [ ] **Broker Health Monitoring:** Giám sát Under-Replicated Partitions, Active Controller Count.
- [ ] **JVM & OS Metrics:** Giám sát RAM heap usage (tối đa 50% RAM vật lý cho Kafka).
