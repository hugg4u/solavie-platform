# Requirements — Comment Manager Service

## Overview
Dịch vụ quản lý bình luận trên bài đăng — auto-classify (spam/negative/question/praise), auto-hide spam, auto-reply questions, escalate negatives, learn from overrides.

## Tech Stack
- **Language:** Node.js 20
- **Framework:** NestJS
- **Database:** PostgreSQL (comment_db)
- **Queue:** Kafka (consumer + producer)
- **AI:** AI Core (REST) cho classification + auto-reply

## Requirements

### Requirement 1: Comment Classification

#### Acceptance Criteria
1. WHEN comment mới nhận được, THE Comment_Manager SHALL classify: spam, negative, question, praise, neutral
2. Classification SHALL dùng AI_Core (semantic, không chỉ keyword)
3. THE Comment_Manager SHALL cho phép human override classification
4. THE Comment_Manager SHALL learn từ overrides để improve accuracy

### Requirement 2: Auto-Actions

#### Acceptance Criteria
1. WHEN spam detected, THE Comment_Manager SHALL auto-hide comment
2. WHEN question detected, THE Comment_Manager SHALL generate auto-reply (via AI Core + Knowledge Base)
3. WHEN negative detected, THE Comment_Manager SHALL escalate cho agent (via Notification)
4. WHEN praise detected, THE Comment_Manager SHALL auto-like (if platform supports)

### Requirement 3: Comment Management UI

#### Acceptance Criteria
1. THE Comment_Manager SHALL list comments per post (filterable by classification)
2. THE Comment_Manager SHALL hỗ trợ manual reply, hide, unhide
3. THE Comment_Manager SHALL show classification stats (accuracy, volume)

### Requirement 4: MCP Server Integration

**User Story:** Là hệ thống AI Core Agent, tôi muốn tự động ẩn bình luận vi phạm hoặc phản cảm thông qua giao thức MCP.

#### Acceptance Criteria
1. THE Comment_Manager SHALL expose một endpoint HTTP/SSE tương thích Model Context Protocol (MCP) tại `/api/v1/comments/mcp`.
2. THE Comment_Manager SHALL cung cấp công cụ `hide_comment` để ẩn bình luận được chỉ định.
3. THE Comment_Manager SHALL thực thi bảo mật đa thuê (Multi-tenancy Isolation): chỉ chấp nhận kết nối mang header `X-Tenant-ID` và tự động tiêm giá trị này để lọc/ẩn bình luận trong cơ sở dữ liệu và gọi API platform tương ứng.


### Requirement: Zero-Trust Access Control & Permission Manifest

**User Story:** Là Tenant Admin, tôi muốn xem danh sách quyền hạn mà dịch vụ `comment-manager` hỗ trợ để thiết lập vai trò tùy chỉnh trên Dashboard và đảm bảo bảo mật Zero-Trust downstream.

#### Acceptance Criteria
1. THE COMMENT_MANAGER_Service SHALL cung cấp API manifest tại `GET /api/v1/permissions/manifest` trả về danh sách tài nguyên (resources) và hành động (actions) được hỗ trợ.
2. THE COMMENT_MANAGER_Service SHALL thực hiện kiểm tra chữ ký số HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET` để xác thực request được gửi trực tiếp từ API Gateway tin cậy.
3. THE COMMENT_MANAGER_Service SHALL thực hiện kiểm tra quyền in-memory O(1) dựa trên HTTP Header `X-User-Permissions` truyền từ Gateway. Định dạng quyền của dịch vụ tuân theo cấu trúc `comment-manager:{resource}:{action}` hỗ trợ ký tự đại diện `*` (Super Admin), `comment-manager:*` (Toàn quyền trên service), và `comment-manager:{resource}:*` (Toàn quyền trên tài nguyên).

## Security & Access Control
- **Authentication & Authorization:** APIs và SSE endpoints của Comment Manager Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `comment-manager`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Comment Manager Service.
- **Tenant Isolation:** Dữ liệu Comment Manager và các phiên kết nối MCP **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.

