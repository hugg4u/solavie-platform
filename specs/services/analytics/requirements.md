# Requirements — Analytics Service

## Overview
Dịch vụ thu thập metrics, engagement tracking, AI-powered insights, report generation. Sử dụng TimescaleDB cho time-series data.

## Tech Stack
- **Language:** Java 21
- **Framework:** Spring Boot 3
- **Database:** PostgreSQL 16 + TimescaleDB extension
- **Queue:** Kafka (consumer)

## Requirements

### Requirement 1: Metrics Collection

#### Acceptance Criteria
1. THE Analytics_Service SHALL thu thập engagement metrics: likes, comments, shares, reach, clicks
2. THE Analytics_Service SHALL consume events từ Kafka (messages, posts, campaigns)
3. THE Analytics_Service SHALL aggregate metrics per-channel, per-post, per-campaign
4. Metrics SHALL cập nhật trong vòng 5 phút

### Requirement 2: Dashboard Metrics

#### Acceptance Criteria
1. THE Analytics_Service SHALL cung cấp realtime metrics API
2. THE Analytics_Service SHALL hỗ trợ custom date range filtering
3. THE Analytics_Service SHALL hỗ trợ period comparison (this week vs last week)
4. THE Analytics_Service SHALL cung cấp per-channel và cross-channel views

### Requirement 3: AI Insights

#### Acceptance Criteria
1. THE Analytics_Service SHALL generate weekly insights report tự động (via AI Core)
2. Insights SHALL include: top performing content, best posting times, audience trends
3. THE Analytics_Service SHALL detect anomalies (sudden drops/spikes)

### Requirement 4: Report Export

#### Acceptance Criteria
1. THE Analytics_Service SHALL export reports dạng PDF và CSV
2. THE Analytics_Service SHALL hỗ trợ scheduled reports (weekly email)
3. Reports SHALL customizable per-tenant

### Requirement 5: MCP Server Integration

**User Story:** Là hệ thống AI Core Agent, tôi muốn truy vấn trực tiếp dữ liệu phân tích và hiệu suất chiến dịch qua giao thức MCP để hỗ trợ ra quyết định và lập báo cáo.

#### Acceptance Criteria
1. THE Analytics_Service SHALL expose một endpoint HTTP/SSE tương thích Model Context Protocol (MCP) tại `/api/v1/analytics/mcp`.
2. THE Analytics_Service SHALL cung cấp công cụ `analytics_query` phục vụ việc lấy báo cáo phân tích theo loại chỉ số (engagement, reach, campaign_performance, v.v.).
3. THE Analytics_Service SHALL kiểm chứng bảo mật đa thuê (Multi-tenancy Isolation): chỉ chấp nhận kết nối chứa header `X-Tenant-ID` và tự động áp dụng giá trị này để lọc dữ liệu truy vấn từ TimescaleDB.

## Security & Access Control
- **Authentication & Authorization:** APIs và SSE endpoints của Analytics Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `analytics`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Analytics Service.
- **Tenant Isolation:** Dữ liệu Analytics và các phiên kết nối MCP **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.

