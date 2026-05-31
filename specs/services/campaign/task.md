# Task Checklist — CAMPAIGN Service

## Overview
This document tracks the implementation checklist for **CAMPAIGN Service** based on the system specifications.

### Technical Stack & Configuration
- **Language:** Java 21
- **Framework:** Spring Boot 3
- **Database:** PostgreSQL
- **Queue:** Kafka

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/campaign/requirements.md)
- [Design](file:///specs/solavie-system/services/campaign/design.md)
- [Logging](file:///specs/solavie-system/services/campaign/logging.md)
- [Business Logic](file:///specs/solavie-system/services/campaign/business-logic.md)

---

## Tasks Checklist

### Task 1: 1: Campaign Management
**Acceptance Criteria Implementation:**
- [ ] AC 1.1: THE Campaign_Service SHALL cho phép tạo campaign gồm nhiều posts trên nhiều channels
- [ ] AC 1.2: THE Campaign_Service SHALL hỗ trợ lifecycle: Draft → Active → Paused → Completed
- [ ] AC 1.3: THE Campaign_Service SHALL track performance metrics per-campaign
- [ ] AC 1.4: THE Campaign_Service SHALL hỗ trợ campaign goals (reach, engagement, conversion targets)

### Task 2: 2: A/B Testing
**Acceptance Criteria Implementation:**
- [ ] AC 2.1: THE Campaign_Service SHALL hỗ trợ A/B testing với >= 2 variants
- [ ] AC 2.2: THE Campaign_Service SHALL distribute traffic evenly across variants
- [ ] AC 2.3: WHEN statistical significance đạt (p < 0.05), THE Campaign_Service SHALL auto-select winner
- [ ] AC 2.4: THE Campaign_Service SHALL report variant performance comparison

### Task 3: 3: Performance Tracking
**Acceptance Criteria Implementation:**
- [ ] AC 3.1: THE Campaign_Service SHALL track: reach, engagement rate, click-through, conversion
- [ ] AC 3.2: THE Campaign_Service SHALL generate performance summary khi campaign kết thúc
- [ ] AC 3.3: THE Campaign_Service SHALL compare performance vs campaign goals

### Task 4: Implement Business Logic Rules
**Business Validations:**
- [ ] Luồng 1: Campaign Lifecycle: Draft: Có thể edit, add/remove posts, chưa publish gì
- [ ] Luồng 1: Campaign Lifecycle: Active: Posts đang được schedule/publish, metrics collecting
- [ ] Luồng 1: Campaign Lifecycle: Paused: Tạm dừng publish, giữ metrics
- [ ] Luồng 1: Campaign Lifecycle: Completed: Kết thúc, generate final report

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
