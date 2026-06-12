# Requirements — Observability Service

## Overview
Dịch vụ giám sát tập trung — thu thập metrics, logs, traces từ tất cả services. Cung cấp dashboards, alerting, distributed tracing. Deploy stack: Prometheus + Loki + Jaeger + Grafana + OpenTelemetry Collector.

## Tech Stack
- **Metrics:** Prometheus
- **Logs:** Loki + Promtail
- **Tracing:** Jaeger
- **Dashboard:** Grafana
- **Collector:** OpenTelemetry Collector
- **Alerting:** Alertmanager + Grafana Alerts

## Requirements

### Requirement 1: Metrics Collection

**User Story:** Là DevOps, tôi muốn thu thập metrics từ tất cả services.

#### Acceptance Criteria
1. THE Observability_Service SHALL scrape metrics từ tất cả services mỗi 15 giây
2. THE Observability_Service SHALL lưu trữ metrics tối thiểu 30 ngày
3. THE Observability_Service SHALL hỗ trợ custom metrics per service
4. THE Observability_Service SHALL thu thập system metrics: CPU, RAM, disk, network per container

### Requirement 2: Centralized Logging

**User Story:** Là developer, tôi muốn search logs từ tất cả services ở 1 nơi.

#### Acceptance Criteria
1. THE Observability_Service SHALL thu thập logs từ tất cả services
2. THE Observability_Service SHALL index logs theo labels: service_name, level, tenant_id, trace_id
3. THE Observability_Service SHALL hỗ trợ search logs theo time range, service, level
4. THE Observability_Service SHALL lưu trữ logs tối thiểu 14 ngày
5. THE Observability_Service SHALL hỗ trợ log correlation với traces (via trace_id)

### Requirement 3: Distributed Tracing

**User Story:** Là developer, tôi muốn trace 1 request qua nhiều services để debug.

#### Acceptance Criteria
1. THE Observability_Service SHALL thu thập traces từ tất cả services
2. THE Observability_Service SHALL hiển thị full request path (service A → B → C)
3. THE Observability_Service SHALL hiển thị latency breakdown per service
4. THE Observability_Service SHALL hỗ trợ search traces theo trace_id, service, duration
5. THE Observability_Service SHALL sample 10% traces trong production (100% trong staging)

### Requirement 4: Dashboards

**User Story:** Là DevOps/Manager, tôi muốn dashboards trực quan cho system health.

#### Acceptance Criteria
1. THE Observability_Service SHALL cung cấp System Health dashboard (all services status)
2. THE Observability_Service SHALL cung cấp per-service dashboards (latency, error rate, throughput)
3. THE Observability_Service SHALL cung cấp AI Performance dashboard (token usage, cost, confidence distribution)
4. THE Observability_Service SHALL cung cấp Business Metrics dashboard (messages/day, posts published, handoff rate)

### Requirement 5: Alerting

**User Story:** Là DevOps, tôi muốn nhận alert khi có sự cố.

#### Acceptance Criteria
1. THE Observability_Service SHALL alert khi service health check fail > 30 giây
2. THE Observability_Service SHALL alert khi error rate > 5% trong 5 phút
3. THE Observability_Service SHALL alert khi latency p95 > threshold per service
4. THE Observability_Service SHALL alert khi Kafka consumer lag > 1000 messages
5. THE Observability_Service SHALL gửi alerts qua Slack và email
6. THE Observability_Service SHALL hỗ trợ alert silencing (maintenance windows)

### Requirement 6: Audit Logging System (Luồng 6 - MỚI)

**User Story:** Là Security Auditor, tôi muốn tất cả hành động nhạy cảm hoặc thay đổi trạng thái trong toàn bộ microservices được ghi nhận tập trung để kiểm toán bảo mật.

#### Acceptance Criteria
1. THE Observability_Service SHALL đóng vai trò Kafka Consumer tiêu thụ (consume) mọi sự kiện kiểm toán gửi tới Kafka topic `audit.events` (Luồng 6).
2. THE Observability_Service SHALL lưu trữ các sự kiện kiểm toán này vào cơ sở dữ liệu chuyên biệt (ClickHouse hoặc Elasticsearch) có hiệu năng ghi cao và tối ưu hóa dung lượng lưu trữ đĩa.
3. THE Observability_Service SHALL đảm bảo an toàn dữ liệu: áp dụng cơ chế idempotent để tránh ghi lặp sự kiện và lưu trữ logs kiểm toán tối thiểu 1 năm (hoặc theo quy định pháp lý của tenant).
4. THE Observability_Service SHALL hỗ trợ query logs kiểm toán theo `tenant_id` (đảm bảo tenant isolation), `user_id`, `action`, `resource`, `status` và `time_range`.

### Requirement: Zero-Trust Access Control & Permission Manifest

**User Story:** Là Tenant Admin, tôi muốn xem danh sách quyền hạn mà dịch vụ `observability` hỗ trợ để thiết lập vai trò tùy chỉnh trên Dashboard và đảm bảo bảo mật Zero-Trust downstream.

#### Acceptance Criteria
1. THE OBSERVABILITY_Service SHALL cung cấp API manifest tại `GET /api/v1/permissions/manifest` trả về danh sách tài nguyên (resources) và hành động (actions) được hỗ trợ.
2. THE OBSERVABILITY_Service SHALL thực hiện kiểm tra chữ ký số HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET` để xác thực request được gửi trực tiếp từ API Gateway tin cậy.
3. THE OBSERVABILITY_Service SHALL thực hiện kiểm tra quyền in-memory O(1) dựa trên HTTP Header `X-User-Permissions` truyền từ Gateway. Định dạng quyền của dịch vụ tuân theo cấu trúc `observability:{resource}:{action}` hỗ trợ ký tự đại diện `*` (Super Admin), `observability:*` (Toàn quyền trên service), và `observability:{resource}:*` (Toàn quyền trên tài nguyên).

## Security & Access Control
- **Authentication & Authorization:** APIs của Observability Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `observability`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Observability Service.
- **Tenant Isolation:** Dữ liệu Observability **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.


---

## Service Discovery (Self-Registration) & Health Endpoint (Tối ưu hóa)
1. THE Service SHALL tự phát hiện IP card mạng nội bộ khi khởi chạy theo độ ưu tiên: Biến môi trường `CONTAINER_IP` > Quét các interface card mạng vật lý của OS > Fallback kết nối UDP fake đến `8.8.8.8`.
2. THE Service SHALL tự động đăng ký địa chỉ `IP:Port` của mình vào Redis Set `registry:service:observability` khi startup.
3. THE Service SHALL gửi tin nhắn sống (heartbeat) định kỳ mỗi 5 giây lên Redis key `registry:service:observability:node:{ip}:{port}` với TTL là 15 giây.
4. THE Service SHALL tự động xóa IP của mình trên Redis Set và xóa key TTL khi nhận tín hiệu shutdown (`SIGTERM`/`SIGINT`).
5. THE Service SHALL cung cấp API endpoint `/health` (hoặc `/healthz`) trả về HTTP 200 OK để phục vụ Active Healthcheck của API Gateway.
6. THE Service SHALL tích hợp cơ chế Fail-Safe: Registry client không crash ứng dụng nếu Redis tạm thời mất kết nối khi khởi chạy.
