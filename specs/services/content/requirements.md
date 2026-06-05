# Requirements — Content Service

## Overview
Dịch vụ quản lý bài đăng và tạo nội dung AI — generate content dựa trên brand voice (RAG), adapt cho từng platform, quality check, approval workflow, versioning.

## Tech Stack
- **Language:** Python 3.12
- **Framework:** FastAPI
- **Database:** PostgreSQL (content_db)
- **Dependencies:** AI Core (REST), Knowledge Base (REST)

## Requirements

### Requirement 1: AI Content Generation

**User Story:** Là content creator, tôi muốn AI tạo nội dung dựa trên brand voice.

#### Acceptance Criteria
1. WHEN user request tạo content, THE Content_Service SHALL lấy brand voice + product info từ Knowledge_Base
2. THE Content_Service SHALL gọi AI_Core để generate content
3. THE Content_Service SHALL include trend data (top performing posts) trong prompt
4. Generated content SHALL match brand voice và target audience

### Requirement 2: Platform Adaptation

**User Story:** Là marketer, tôi muốn 1 nội dung được adapt cho nhiều platform.

#### Acceptance Criteria
1. THE Content_Service SHALL adapt content cho Facebook (dài, hashtags), Zalo (formal, ngắn), TikTok (ngắn, trending)
2. THE Content_Service SHALL respect character limits per platform
3. THE Content_Service SHALL suggest hashtags phù hợp per platform
4. THE Content_Service SHALL suggest best posting time

### Requirement 3: Quality Check

**User Story:** Là brand manager, tôi muốn content luôn đạt chuẩn trước khi publish.

#### Acceptance Criteria
1. THE Content_Service SHALL check grammar và spelling
2. THE Content_Service SHALL check brand consistency (tone, keywords)
3. THE Content_Service SHALL check platform compliance (character limits, banned words)
4. IF quality score < 0.7, THEN mark content cần revision với lý do cụ thể

### Requirement 4: Approval Workflow

**User Story:** Là manager, tôi muốn review và approve content trước khi publish.

#### Acceptance Criteria
1. THE Content_Service SHALL đưa content vào approval queue sau generation
2. THE Content_Service SHALL hỗ trợ approve/reject với feedback
3. WHEN approved, THE Content_Service SHALL chuyển đến Scheduler_Service
4. THE Content_Service SHALL hỗ trợ dynamic approval flow (configurable per tenant)

### Requirement 5: Content Versioning

**User Story:** Là editor, tôi muốn xem lịch sử chỉnh sửa content.

#### Acceptance Criteria
1. THE Content_Service SHALL lưu tất cả versions (draft, edited, approved, published)
2. THE Content_Service SHALL track who changed what và when
3. THE Content_Service SHALL hỗ trợ rollback to previous version

### Requirement 6: MCP Server Integration

**User Story:** Là hệ thống AI Core Agent, tôi muốn tự động ra lệnh sinh nội dung hoặc thích ứng nội dung cho các nền tảng mạng xã hội khác nhau thông qua giao thức MCP.

#### Acceptance Criteria
1. THE Content_Service SHALL expose một endpoint HTTP/SSE tương thích Model Context Protocol (MCP) tại `/api/v1/content/mcp`.
2. THE Content_Service SHALL cung cấp công cụ `generate_content` để sinh nội dung quảng cáo hoặc bài viết mới dựa trên thương hiệu của tenant.
3. THE Content_Service SHALL cung cấp công cụ `adapt_content` để tự động điều chỉnh văn bản phù hợp với giới hạn và văn phong của kênh đích.
4. THE Content_Service SHALL bảo đảm cách ly dữ liệu thuê (Multi-tenancy Isolation): chỉ chấp nhận kết nối mang header `X-Tenant-ID` và tự động tiêm giá trị này để bảo vệ dữ liệu trong cơ sở dữ liệu PostgreSQL và MinIO.

## Security & Access Control
- **Authentication & Authorization:** APIs và SSE endpoints của Content Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `content`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Content Service.
- **Tenant Isolation:** Dữ liệu Content và các phiên kết nối MCP **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.

