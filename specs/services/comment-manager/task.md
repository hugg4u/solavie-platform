# Task Checklist — COMMENT-MANAGER Service

## Overview
This document tracks the implementation checklist for **COMMENT-MANAGER Service** based on the system specifications.

### Technical Stack & Configuration
- **Language:** Node.js 20
- **Framework:** NestJS
- **Database:** PostgreSQL
- **Queue:** Kafka
- **AI:** AI Core (REST) cho classification + auto-reply

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/comment-manager/requirements.md)
- [Design](file:///specs/solavie-system/services/comment-manager/design.md)
- [Logging](file:///specs/solavie-system/services/comment-manager/logging.md)
- [Business Logic](file:///specs/solavie-system/services/comment-manager/business-logic.md)

---

## Tasks Checklist

### Task 1: 1: Comment Classification
**Acceptance Criteria Implementation:**
- [ ] AC 1.1: WHEN comment mới nhận được, THE Comment_Manager SHALL classify: spam, negative, question, praise, neutral
- [ ] AC 1.2: Classification SHALL dùng AI_Core (semantic, không chỉ keyword)
- [ ] AC 1.3: THE Comment_Manager SHALL cho phép human override classification
- [ ] AC 1.4: THE Comment_Manager SHALL learn từ overrides để improve accuracy

### Task 2: 2: Auto-Actions
**Acceptance Criteria Implementation:**
- [ ] AC 2.1: WHEN spam detected, THE Comment_Manager SHALL auto-hide comment
- [ ] AC 2.2: WHEN question detected, THE Comment_Manager SHALL generate auto-reply (via AI Core + Knowledge Base)
- [ ] AC 2.3: WHEN negative detected, THE Comment_Manager SHALL escalate cho agent (via Notification)
- [ ] AC 2.4: WHEN praise detected, THE Comment_Manager SHALL auto-like (if platform supports)

### Task 3: 3: Comment Management UI
**Acceptance Criteria Implementation:**
- [ ] AC 3.1: THE Comment_Manager SHALL list comments per post (filterable by classification)
- [ ] AC 3.2: THE Comment_Manager SHALL hỗ trợ manual reply, hide, unhide
- [ ] AC 3.3: THE Comment_Manager SHALL show classification stats (accuracy, volume)

### Task 4: Implement Business Logic Rules
**Business Validations:**
- [ ] Tổng quan vai trò (CẬP NHẬT): Comment Manager gọi AI Core agent (use_case="comment_management")
- [ ] Tổng quan vai trò (CẬP NHẬT): AI Core tự handle: classify comment + quyết định action
- [ ] Tổng quan vai trò (CẬP NHẬT): AI Core có thể gọi tools: knowledge_base_search (tìm answer cho questions), hide_comment, send_notification (escalate)
- [ ] Tổng quan vai trò (CẬP NHẬT): Comment Manager chỉ lo: trigger AI Core khi comment mới đến, lưu kết quả, handle overrides
- [ ] Luồng 1: Comment Classification & Auto-Action: spam: Promotional, irrelevant links, bot-like repetitive text
- [ ] Luồng 1: Comment Classification & Auto-Action: negative: Complaints, insults, dissatisfaction, threats
- [ ] Luồng 1: Comment Classification & Auto-Action: question: Asking about product, price, availability, how-to
- [ ] Luồng 1: Comment Classification & Auto-Action: praise: Compliments, positive feedback, recommendations
- [ ] Luồng 1: Comment Classification & Auto-Action: neutral: General remarks, reactions, neither positive nor negative

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
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `comment-manager`.
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`.
- [ ] Triển khai HMAC Signature Verification Guard/Interceptor sử dụng `GATEWAY_SIGNING_SECRET` để xác thực request từ Gateway.
- [ ] Triển khai cơ chế so khớp quyền hạn Dynamic RBAC in-memory O(1) hỗ trợ wildcard (`*`, `comment-manager:*`, `comment-manager:{resource}:*`).
- [ ] Thực hiện tích hợp Endpoint `/api/v1/permissions/manifest` trả về danh sách tài nguyên và quyền hạn của service.
- [ ] Bổ sung các test cases kiểm tra Signature Verification và Access Control Denied.

### Task 5: Custom MCP Server Integration
- [ ] Tích hợp `@modelcontextprotocol/sdk` vào dự án NestJS.
- [ ] Thiết kế endpoint SSE `GET /api/v1/comments/mcp` và endpoint nhận thông điệp `POST /api/v1/comments/mcp/messages`.
- [ ] Đăng ký công cụ `hide_comment` nhận tham số `comment_id`, `is_hidden`, `reason`.
- [ ] Thực thi cơ chế tiêm `tenant_id` từ header của request trực tiếp vào các Prisma query để cô lập tenant và gọi API platform tương ứng.
- [ ] Viết unit tests và integration các kịch bản kiểm soát truy cập chéo tenant trên comment.

