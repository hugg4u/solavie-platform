# Task Checklist — OBSERVABILITY Service

## Overview
This document tracks the implementation checklist for **OBSERVABILITY Service** based on the system specifications.

### Technical Stack & Configuration
- **Metrics:** Prometheus
- **Logs:** Loki + Promtail
- **Tracing:** Jaeger
- **Dashboard:** Grafana
- **Collector:** OpenTelemetry Collector
- **Alerting:** Alertmanager + Grafana Alerts

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/observability/requirements.md)
- [Design](file:///specs/solavie-system/services/observability/design.md)

---

## Tasks Checklist

### Task 1: 1: Metrics Collection
> *User Story: Là DevOps, tôi muốn thu thập metrics từ tất cả services.*

**Acceptance Criteria Implementation:**
- [ ] AC 1.1: THE Observability_Service SHALL scrape metrics từ tất cả services mỗi 15 giây
- [ ] AC 1.2: THE Observability_Service SHALL lưu trữ metrics tối thiểu 30 ngày
- [ ] AC 1.3: THE Observability_Service SHALL hỗ trợ custom metrics per service
- [ ] AC 1.4: THE Observability_Service SHALL thu thập system metrics: CPU, RAM, disk, network per container

### Task 2: 2: Centralized Logging
> *User Story: Là developer, tôi muốn search logs từ tất cả services ở 1 nơi.*

**Acceptance Criteria Implementation:**
- [ ] AC 2.1: THE Observability_Service SHALL thu thập logs từ tất cả services
- [ ] AC 2.2: THE Observability_Service SHALL index logs theo labels: service_name, level, tenant_id, trace_id
- [ ] AC 2.3: THE Observability_Service SHALL hỗ trợ search logs theo time range, service, level
- [ ] AC 2.4: THE Observability_Service SHALL lưu trữ logs tối thiểu 14 ngày
- [ ] AC 2.5: THE Observability_Service SHALL hỗ trợ log correlation với traces (via trace_id)

### Task 3: 3: Distributed Tracing
> *User Story: Là developer, tôi muốn trace 1 request qua nhiều services để debug.*

**Acceptance Criteria Implementation:**
- [ ] AC 3.1: THE Observability_Service SHALL thu thập traces từ tất cả services
- [ ] AC 3.2: THE Observability_Service SHALL hiển thị full request path (service A → B → C)
- [ ] AC 3.3: THE Observability_Service SHALL hiển thị latency breakdown per service
- [ ] AC 3.4: THE Observability_Service SHALL hỗ trợ search traces theo trace_id, service, duration
- [ ] AC 3.5: THE Observability_Service SHALL sample 10% traces trong production (100% trong staging)

### Task 4: 4: Dashboards
> *User Story: Là DevOps/Manager, tôi muốn dashboards trực quan cho system health.*

**Acceptance Criteria Implementation:**
- [ ] AC 4.1: THE Observability_Service SHALL cung cấp System Health dashboard (all services status)
- [ ] AC 4.2: THE Observability_Service SHALL cung cấp per-service dashboards (latency, error rate, throughput)
- [ ] AC 4.3: THE Observability_Service SHALL cung cấp AI Performance dashboard (token usage, cost, confidence distribution)
- [ ] AC 4.4: THE Observability_Service SHALL cung cấp Business Metrics dashboard (messages/day, posts published, handoff rate)

### Task 5: 5: Alerting
> *User Story: Là DevOps, tôi muốn nhận alert khi có sự cố.*

**Acceptance Criteria Implementation:**
- [ ] AC 5.1: THE Observability_Service SHALL alert khi service health check fail > 30 giây
- [ ] AC 5.2: THE Observability_Service SHALL alert khi error rate > 5% trong 5 phút
- [ ] AC 5.3: THE Observability_Service SHALL alert khi latency p95 > threshold per service
- [ ] AC 5.4: THE Observability_Service SHALL alert khi Kafka consumer lag > 1000 messages
- [ ] AC 5.5: THE Observability_Service SHALL gửi alerts qua Slack và email
- [ ] AC 5.6: THE Observability_Service SHALL hỗ trợ alert silencing (maintenance windows)

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

### Task: Security Integration & Dynamic RBAC (MỚI)
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `observability`.
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`.
- [ ] Triển khai HMAC Signature Verification Guard/Interceptor sử dụng `GATEWAY_SIGNING_SECRET` để xác thực request từ Gateway.
- [ ] Triển khai cơ chế so khớp quyền hạn Dynamic RBAC in-memory O(1) hỗ trợ wildcard (`*`, `observability:*`, `observability:{resource}:*`).
- [ ] Thực hiện tích hợp Endpoint `/api/v1/permissions/manifest` trả về danh sách tài nguyên và quyền hạn của service.
- [ ] Bổ sung các test cases kiểm tra Signature Verification và Access Control Denied.
