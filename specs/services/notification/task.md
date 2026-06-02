# Task Checklist — NOTIFICATION Service

## Overview
This document tracks the implementation checklist for **NOTIFICATION Service** based on the system specifications.

### Technical Stack & Configuration
- **Language:** Node.js 20
- **Framework:** NestJS
- **Database:** PostgreSQL
- **Queue:** Kafka

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/notification/requirements.md)
- [Design](file:///specs/solavie-system/services/notification/design.md)
- [Logging](file:///specs/solavie-system/services/notification/logging.md)
- [Business Logic](file:///specs/solavie-system/services/notification/business-logic.md)

---

## Tasks Checklist

### Task 1: 1: Multi-channel Delivery
**Acceptance Criteria Implementation:**
- [ ] AC 1.1: THE Notification_Service SHALL hỗ trợ: Slack, email, in-app push
- [ ] AC 1.2: THE Notification_Service SHALL route notification theo user preferences
- [ ] AC 1.3: THE Notification_Service SHALL retry nếu delivery thất bại
- [ ] AC 1.4: Handoff notifications SHALL delivered trong < 3 giây

### Task 2: 2: User Preferences
**Acceptance Criteria Implementation:**
- [ ] AC 2.1: THE Notification_Service SHALL cho phép user cấu hình: channels, quiet hours, priority levels
- [ ] AC 2.2: THE Notification_Service SHALL respect quiet hours (không gửi ngoài giờ làm việc)
- [ ] AC 2.3: THE Notification_Service SHALL hỗ trợ priority levels: critical (always), high, normal, low

### Task 3: 3: Delivery Guarantee
**Acceptance Criteria Implementation:**
- [ ] AC 3.1: IF primary channel thất bại, THEN fallback sang channel khác
- [ ] AC 3.2: IF tất cả channels thất bại, THEN queue cho retry sau
- [ ] AC 3.3: THE Notification_Service SHALL log delivery status per notification

### Task 4: Implement Business Logic Rules
**Business Validations:**
- [ ] Tổng quan vai trò: Consume events từ Kafka (handoff, lead score, failures)
- [ ] Tổng quan vai trò: Resolve recipient + preferences
- [ ] Tổng quan vai trò: Deliver qua Slack/email/push (với fallback)
- [ ] Tổng quan vai trò: Track delivery status, respect quiet hours

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
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `notification`
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`
