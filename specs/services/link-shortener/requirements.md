# Requirements Document

## Introduction

Dịch vụ rút gọn URL và theo dõi click cho chiến dịch marketing của Solavie. Mỗi short link được gắn với một chiến dịch cụ thể, cho phép đo lường hiệu quả từng kênh gửi tin và so sánh A/B variants. Redis cache toàn bộ ánh xạ short_code → original_url để đảm bảo redirect không cần DB lookup trong trường hợp bình thường.

## Tech Stack
- **Language:** Node.js 20
- **Framework:** Fastify
- **Database:** PostgreSQL (shortener_db)
- **Cache:** Redis (ánh xạ link, rate limiting)
- **Port:** 3009

## Glossary
- **short_code**: Mã định danh duy nhất 8-12 ký tự (a-z, A-Z, 0-9)
- **variant_label**: Nhãn A/B Testing, nhận giá trị `A` hoặc `B`
- **Unique_Click**: Click từ một IP chưa từng click cùng short_code trong 24 giờ
- **Circuit_Breaker**: Cơ chế fallback sang DB khi Redis không khả dụng

## Requirements

### Requirement 1: Tạo Short Link

**User Story:** Là một Marketing Manager, tôi muốn rút gọn URL chiến dịch thành short link ngắn gọn để gửi cho khách hàng qua Zalo/Facebook.

#### Acceptance Criteria
1. WHEN Campaign Service gửi yêu cầu tạo short link với original_url, campaign_id, contact_id và variant_label tùy chọn, THE Link_Shortener SHALL sinh short_code duy nhất dài 8-12 ký tự gồm chữ cái a-z, A-Z và chữ số 0-9
2. THE Link_Shortener SHALL đảm bảo short_code là duy nhất toàn hệ thống; nếu collision, THE Link_Shortener SHALL tự động sinh lại tối đa 5 lần trước khi trả về lỗi
3. THE Link_Shortener SHALL lưu bản ghi shortened_links vào shortener_db với: short_code, tenant_id, original_url, campaign_id, contact_id, variant_label, created_at
4. WHEN short link được tạo thành công, THE Link_Shortener SHALL ghi ánh xạ vào Redis cache key `{tenant_id}:shortener:link:{short_code}` với TTL 30 ngày
5. IF original_url không bắt đầu bằng `https://` hoặc `http://`, THEN THE Link_Shortener SHALL từ chối và trả về lỗi URL không hợp lệ
6. IF original_url vượt quá 2048 ký tự, THEN THE Link_Shortener SHALL từ chối và trả về lỗi vượt giới hạn độ dài
7. IF variant_label được cung cấp nhưng không phải `A` hoặc `B`, THEN THE Link_Shortener SHALL từ chối và trả về lỗi giá trị không hợp lệ
8. THE Link_Shortener SHALL trả về short URL hoàn chỉnh dạng `https://{domain}/{short_code}` trong response

### Requirement 2: Redirect và Ghi nhận Click

**User Story:** Là một khách hàng, tôi muốn click vào short link và được chuyển hướng ngay đến trang đích mà không bị gián đoạn.

#### Acceptance Criteria
1. WHEN khách hàng gửi HTTP GET đến `/{short_code}`, THE Link_Shortener SHALL tra cứu original_url từ Redis cache trước; nếu cache hit, THE Link_Shortener SHALL trả về HTTP 302 redirect trong vòng 50ms
2. WHEN Redis cache miss, THE Link_Shortener SHALL tra cứu từ shortener_db, ghi lại vào Redis cache TTL 30 ngày, sau đó trả về HTTP 302 redirect
3. WHEN redirect thành công, THE Link_Shortener SHALL ghi nhận Click_Event bất đồng bộ vào link_clicks với: id, tenant_id, short_code, clicked_at (UTC), ip_address, user_agent (tối đa 512 ký tự), country (từ GeoIP lookup)
4. IF short_code không tồn tại trong cả Redis lẫn DB, THEN THE Link_Shortener SHALL trả về HTTP 404 và không ghi Click_Event
5. THE Link_Shortener SHALL ghi Click_Event bất đồng bộ để không làm chậm thời gian redirect
6. IF GeoIP lookup thất bại, THE Link_Shortener SHALL lưu country là `UNKNOWN` và vẫn hoàn thành redirect bình thường

### Requirement 3: Circuit Breaker — Fallback khi Redis không khả dụng

**User Story:** Là một System Admin, tôi muốn hệ thống redirect vẫn hoạt động khi Redis gặp sự cố.

#### Acceptance Criteria
1. WHILE Redis không khả dụng (connection timeout > 200ms hoặc connection refused), THE Link_Shortener SHALL tự động fallback sang tra cứu original_url trực tiếp từ shortener_db
2. WHILE circuit breaker ở trạng thái Open, THE Link_Shortener SHALL ghi Click_Event vào DB đồng bộ thay vì bất đồng bộ qua Redis queue
3. WHEN Redis khôi phục kết nối, THE Link_Shortener SHALL tự động chuyển circuit breaker về Closed và tiếp tục dùng Redis cache
4. THE Link_Shortener SHALL expose trạng thái circuit breaker qua GET /health để monitoring

### Requirement 4: Rate Limiting chống Bot

**User Story:** Là một System Admin, tôi muốn ngăn chặn bot tự động cào link để dữ liệu analytics phản ánh đúng hành vi thực.

#### Acceptance Criteria
1. THE Gateway SHALL áp dụng rate limiting cho redirect endpoint: tối đa 60 requests/phút per IP; vượt ngưỡng trả về HTTP 429 kèm header Retry-After
2. THE Gateway SHALL áp dụng rate limiting cho API tạo short link: tối đa 100 requests/phút per tenant_id
3. IF User-Agent vắng mặt hoặc khớp bot patterns (bot, crawler, spider, scraper), THEN THE Link_Shortener SHALL ghi Click_Event với flag is_bot = true và không tính vào Unique_Click analytics
4. THE Link_Shortener SHALL lưu trạng thái rate limiting trong Redis key `{tenant_id}:shortener:ratelimit:{ip}` TTL 60 giây

### Requirement 5: Analytics — Thống kê Click

**User Story:** Là một Marketing Manager, tôi muốn xem báo cáo hiệu quả click và so sánh A/B variants để tối ưu chiến dịch.

#### Acceptance Criteria
1. THE Link_Shortener SHALL cung cấp API analytics per short_code: tổng click, Unique_Click, phân bổ theo country (top 10), phân bổ theo device type (Mobile/Desktop/Tablet)
2. THE Link_Shortener SHALL cung cấp API analytics per campaign_id: tổng click toàn chiến dịch, click theo từng short_code, so sánh variant A vs B
3. THE Link_Shortener SHALL áp dụng tenant isolation: mọi analytics query phải filter theo tenant_id từ JWT; query không có tenant_id hợp lệ SHALL bị reject với HTTP 403
4. THE Link_Shortener SHALL trả về kết quả analytics trong vòng 2 giây cho khoảng thời gian tối đa 90 ngày
5. IF campaign_id không tồn tại hoặc không thuộc tenant hiện tại, THEN THE Link_Shortener SHALL trả về HTTP 404


### Requirement: Zero-Trust Access Control & Permission Manifest

**User Story:** Là Tenant Admin, tôi muốn xem danh sách quyền hạn mà dịch vụ `link-shortener` hỗ trợ để thiết lập vai trò tùy chỉnh trên Dashboard và đảm bảo bảo mật Zero-Trust downstream.

#### Acceptance Criteria
1. THE LINK_SHORTENER_Service SHALL cung cấp API manifest tại `GET /api/v1/permissions/manifest` trả về danh sách tài nguyên (resources) và hành động (actions) được hỗ trợ.
2. THE LINK_SHORTENER_Service SHALL thực hiện kiểm tra chữ ký số HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET` để xác thực request được gửi trực tiếp từ API Gateway tin cậy.
3. THE LINK_SHORTENER_Service SHALL thực hiện kiểm tra quyền in-memory O(1) dựa trên HTTP Header `X-User-Permissions` truyền từ Gateway. Định dạng quyền của dịch vụ tuân theo cấu trúc `link-shortener:{resource}:{action}` hỗ trợ ký tự đại diện `*` (Super Admin), `link-shortener:*` (Toàn quyền trên service), và `link-shortener:{resource}:*` (Toàn quyền trên tài nguyên).

## Security & Access Control
- **Authentication & Authorization:** APIs của Link Shortener Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `link-shortener`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Link Shortener Service.
- **Tenant Isolation:** Dữ liệu Link Shortener **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.

---

## Service Discovery (Self-Registration)

**User Story:** Là một developer, tôi muốn service của mình tự động đăng ký và duy trì heartbeat trên Redis Registry khi khởi động để Gateway có thể định tuyến động chính xác mà không phụ thuộc vào hạ tầng.

### Acceptance Criteria
1. THE Link Shortener Service SHALL tự động phát hiện IP nội bộ của card mạng chính khi khởi động bằng cơ chế socket UDP ảo.
2. THE Link Shortener Service SHALL đăng ký địa chỉ `IP:Port` của mình vào Redis Set `registry:service:link-shortener` khi startup.
3. THE Link Shortener Service SHALL gửi tin nhắn sống (heartbeat) định kỳ mỗi 5 giây lên Redis key `registry:service:link-shortener:node:{ip}:{port}` với TTL là 15 giây.
4. THE Link Shortener Service SHALL dọn dẹp (hủy đăng ký) thông tin của mình trên Redis Set `registry:service:link-shortener` và xóa key TTL khi nhận tín hiệu shutdown (`SIGTERM`/`SIGINT`).
