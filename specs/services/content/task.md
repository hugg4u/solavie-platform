# Task Checklist — CONTENT Service

## Overview
This document tracks the implementation checklist for **CONTENT Service** based on the system specifications.

### Technical Stack & Configuration
- **Language:** Python 3.12
- **Framework:** FastAPI
- **Database:** PostgreSQL
- **Dependencies:** AI Core

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/content/requirements.md)
- [Design](file:///specs/solavie-system/services/content/design.md)
- [Logging](file:///specs/solavie-system/services/content/logging.md)
- [Business Logic](file:///specs/solavie-system/services/content/business-logic.md)

---

## Tasks Checklist

### Task 1: 1: AI Content Generation
> *User Story: Là content creator, tôi muốn AI tạo nội dung dựa trên brand voice.*

**Acceptance Criteria Implementation:**
- [ ] AC 1.1: WHEN user request tạo content, THE Content_Service SHALL lấy brand voice + product info từ Knowledge_Base
- [ ] AC 1.2: THE Content_Service SHALL gọi AI_Core để generate content
- [ ] AC 1.3: THE Content_Service SHALL include trend data (top performing posts) trong prompt
- [ ] AC 1.4: Generated content SHALL match brand voice và target audience

### Task 2: 2: Platform Adaptation
> *User Story: Là marketer, tôi muốn 1 nội dung được adapt cho nhiều platform.*

**Acceptance Criteria Implementation:**
- [ ] AC 2.1: THE Content_Service SHALL adapt content cho Facebook (dài, hashtags), Zalo (formal, ngắn), TikTok (ngắn, trending)
- [ ] AC 2.2: THE Content_Service SHALL respect character limits per platform
- [ ] AC 2.3: THE Content_Service SHALL suggest hashtags phù hợp per platform
- [ ] AC 2.4: THE Content_Service SHALL suggest best posting time

### Task 3: 3: Quality Check
> *User Story: Là brand manager, tôi muốn content luôn đạt chuẩn trước khi publish.*

**Acceptance Criteria Implementation:**
- [ ] AC 3.1: THE Content_Service SHALL check grammar và spelling
- [ ] AC 3.2: THE Content_Service SHALL check brand consistency (tone, keywords)
- [ ] AC 3.3: THE Content_Service SHALL check platform compliance (character limits, banned words)
- [ ] AC 3.4: IF quality score < 0.7, THEN mark content cần revision với lý do cụ thể

### Task 4: 4: Approval Workflow
> *User Story: Là manager, tôi muốn review và approve content trước khi publish.*

**Acceptance Criteria Implementation:**
- [ ] AC 4.1: THE Content_Service SHALL đưa content vào approval queue sau generation
- [ ] AC 4.2: THE Content_Service SHALL hỗ trợ approve/reject với feedback
- [ ] AC 4.3: WHEN approved, THE Content_Service SHALL chuyển đến Scheduler_Service
- [ ] AC 4.4: THE Content_Service SHALL hỗ trợ dynamic approval flow (configurable per tenant)

### Task 5: 5: Content Versioning
> *User Story: Là editor, tôi muốn xem lịch sử chỉnh sửa content.*

**Acceptance Criteria Implementation:**
- [ ] AC 5.1: THE Content_Service SHALL lưu tất cả versions (draft, edited, approved, published)
- [ ] AC 5.2: THE Content_Service SHALL track who changed what và when
- [ ] AC 5.3: THE Content_Service SHALL hỗ trợ rollback to previous version

### Task 6: Implement Business Logic Rules
**Business Validations:**
- [ ] Tổng quan vai trò (CẬP NHẬT): Content Service không cần tự gọi Knowledge Base + Analytics riêng nữa
- [ ] Tổng quan vai trò (CẬP NHẬT): Gọi AI Core agent (use_case="content_generation") → AI Core tự:
- [ ] Tổng quan vai trò (CẬP NHẬT): Search KB cho brand voice + product info (tool: knowledge_base_search)
- [ ] Tổng quan vai trò (CẬP NHẬT): Search web cho trends + tin tức (tool: web_search)
- [ ] Tổng quan vai trò (CẬP NHẬT): Query analytics cho top posts (tool: analytics_query)
- [ ] Tổng quan vai trò (CẬP NHẬT): Get trending hashtags (tool: get_social_trends)
- [ ] Tổng quan vai trò (CẬP NHẬT): Generate content dựa trên tất cả context thu thập được
- [ ] Tổng quan vai trò (CẬP NHẬT): Content Service chỉ lo: approval workflow, versioning, scheduling
- [ ] Luồng 1: AI Content Generation: Max {config['optimal_chars']} characters
- [ ] Luồng 1: AI Content Generation: Tone: {config['tone']}
- [ ] Luồng 1: AI Content Generation: Include: {config['features']}
- [ ] Luồng 1: AI Content Generation: Keep the core message intact
- [ ] Luồng 1: AI Content Generation: {f"Add {config['hashtag_count']} relevant hashtags" if config['hashtag_count'] else "No hashtags"}""",

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
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `content`
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`
