# Task Checklist — LINK-SHORTENER Service

## Overview
This document tracks the implementation checklist for **LINK-SHORTENER Service** based on the system specifications.

### Technical Stack & Configuration
- **Language:** Node.js 20
- **Framework:** Fastify
- **Database:** PostgreSQL
- **Cache:** Redis
- **Port:** 3009

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/link-shortener/requirements.md)
- [Design](file:///specs/solavie-system/services/link-shortener/design.md)

---

## Tasks Checklist

### Task 1: 1: Tạo Short Link
> *User Story: Là một Marketing Manager, tôi muốn rút gọn URL chiến dịch thành short link ngắn gọn để gửi cho khách hàng qua Zalo/Facebook.*

**Acceptance Criteria Implementation:**
- [ ] AC 1.1: WHEN Campaign Service gửi yêu cầu tạo short link với original_url, campaign_id, contact_id và variant_label tùy chọn, THE Link_Shortener SHALL sinh short_code duy nhất dài 8-12 ký tự gồm chữ cái a-z, A-Z và chữ số 0-9
- [ ] AC 1.2: THE Link_Shortener SHALL đảm bảo short_code là duy nhất toàn hệ thống; nếu collision, THE Link_Shortener SHALL tự động sinh lại tối đa 5 lần trước khi trả về lỗi
- [ ] AC 1.3: THE Link_Shortener SHALL lưu bản ghi shortened_links vào shortener_db với: short_code, tenant_id, original_url, campaign_id, contact_id, variant_label, created_at
- [ ] AC 1.4: WHEN short link được tạo thành công, THE Link_Shortener SHALL ghi ánh xạ vào Redis cache key `{tenant_id}:shortener:link:{short_code}` với TTL 30 ngày
- [ ] AC 1.5: IF original_url không bắt đầu bằng `https://` hoặc `http://`, THEN THE Link_Shortener SHALL từ chối và trả về lỗi URL không hợp lệ
- [ ] AC 1.6: IF original_url vượt quá 2048 ký tự, THEN THE Link_Shortener SHALL từ chối và trả về lỗi vượt giới hạn độ dài
- [ ] AC 1.7: IF variant_label được cung cấp nhưng không phải `A` hoặc `B`, THEN THE Link_Shortener SHALL từ chối và trả về lỗi giá trị không hợp lệ
- [ ] AC 1.8: THE Link_Shortener SHALL trả về short URL hoàn chỉnh dạng `https://{domain}/{short_code}` trong response

### Task 2: 2: Redirect và Ghi nhận Click
> *User Story: Là một khách hàng, tôi muốn click vào short link và được chuyển hướng ngay đến trang đích mà không bị gián đoạn.*

**Acceptance Criteria Implementation:**
- [ ] AC 2.1: WHEN khách hàng gửi HTTP GET đến `/{short_code}`, THE Link_Shortener SHALL tra cứu original_url từ Redis cache trước; nếu cache hit, THE Link_Shortener SHALL trả về HTTP 302 redirect trong vòng 50ms
- [ ] AC 2.2: WHEN Redis cache miss, THE Link_Shortener SHALL tra cứu từ shortener_db, ghi lại vào Redis cache TTL 30 ngày, sau đó trả về HTTP 302 redirect
- [ ] AC 2.3: WHEN redirect thành công, THE Link_Shortener SHALL ghi nhận Click_Event bất đồng bộ vào link_clicks với: id, tenant_id, short_code, clicked_at (UTC), ip_address, user_agent (tối đa 512 ký tự), country (từ GeoIP lookup)
- [ ] AC 2.4: IF short_code không tồn tại trong cả Redis lẫn DB, THEN THE Link_Shortener SHALL trả về HTTP 404 và không ghi Click_Event
- [ ] AC 2.5: THE Link_Shortener SHALL ghi Click_Event bất đồng bộ để không làm chậm thời gian redirect
- [ ] AC 2.6: IF GeoIP lookup thất bại, THE Link_Shortener SHALL lưu country là `UNKNOWN` và vẫn hoàn thành redirect bình thường

### Task 3: 3: Circuit Breaker — Fallback khi Redis không khả dụng
> *User Story: Là một System Admin, tôi muốn hệ thống redirect vẫn hoạt động khi Redis gặp sự cố.*

**Acceptance Criteria Implementation:**
- [ ] AC 3.1: WHILE Redis không khả dụng (connection timeout > 200ms hoặc connection refused), THE Link_Shortener SHALL tự động fallback sang tra cứu original_url trực tiếp từ shortener_db
- [ ] AC 3.2: WHILE circuit breaker ở trạng thái Open, THE Link_Shortener SHALL ghi Click_Event vào DB đồng bộ thay vì bất đồng bộ qua Redis queue
- [ ] AC 3.3: WHEN Redis khôi phục kết nối, THE Link_Shortener SHALL tự động chuyển circuit breaker về Closed và tiếp tục dùng Redis cache
- [ ] AC 3.4: THE Link_Shortener SHALL expose trạng thái circuit breaker qua GET /health để monitoring

### Task 4: 4: Rate Limiting chống Bot
> *User Story: Là một System Admin, tôi muốn ngăn chặn bot tự động cào link để dữ liệu analytics phản ánh đúng hành vi thực.*

**Acceptance Criteria Implementation:**
- [ ] AC 4.1: THE Gateway SHALL áp dụng rate limiting cho redirect endpoint: tối đa 60 requests/phút per IP; vượt ngưỡng trả về HTTP 429 kèm header Retry-After
- [ ] AC 4.2: THE Gateway SHALL áp dụng rate limiting cho API tạo short link: tối đa 100 requests/phút per tenant_id
- [ ] AC 4.3: IF User-Agent vắng mặt hoặc khớp bot patterns (bot, crawler, spider, scraper), THEN THE Link_Shortener SHALL ghi Click_Event với flag is_bot = true và không tính vào Unique_Click analytics
- [ ] AC 4.4: THE Link_Shortener SHALL lưu trạng thái rate limiting trong Redis key `{tenant_id}:shortener:ratelimit:{ip}` TTL 60 giây

### Task 5: 5: Analytics — Thống kê Click
> *User Story: Là một Marketing Manager, tôi muốn xem báo cáo hiệu quả click và so sánh A/B variants để tối ưu chiến dịch.*

**Acceptance Criteria Implementation:**
- [ ] AC 5.1: THE Link_Shortener SHALL cung cấp API analytics per short_code: tổng click, Unique_Click, phân bổ theo country (top 10), phân bổ theo device type (Mobile/Desktop/Tablet)
- [ ] AC 5.2: THE Link_Shortener SHALL cung cấp API analytics per campaign_id: tổng click toàn chiến dịch, click theo từng short_code, so sánh variant A vs B
- [ ] AC 5.3: THE Link_Shortener SHALL áp dụng tenant isolation: mọi analytics query phải filter theo tenant_id từ JWT; query không có tenant_id hợp lệ SHALL bị reject với HTTP 403
- [ ] AC 5.4: THE Link_Shortener SHALL trả về kết quả analytics trong vòng 2 giây cho khoảng thời gian tối đa 90 ngày
- [ ] AC 5.5: IF campaign_id không tồn tại hoặc không thuộc tenant hiện tại, THEN THE Link_Shortener SHALL trả về HTTP 404

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
