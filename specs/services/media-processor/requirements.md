# Requirements Document

## Introduction

Dịch vụ xử lý ảnh và video bất đồng bộ cho Solavie Marketing Platform. Nhận job từ Kafka/Redis queue, xử lý bằng Celery workers, lưu kết quả vào MinIO và publish event khi hoàn tất. Ghi đệm tạm thời ra SSD thay vì RAM để tránh OOM khi xử lý video nặng.

## Tech Stack
- **Language:** Python 3.12
- **Framework:** FastAPI
- **Workers:** Celery + Redis broker
- **Storage:** MinIO (S3-compatible)
- **Port:** 8008

## Glossary
- **Processing_Job**: Yêu cầu xử lý media, trạng thái: queued → processing → done | failed
- **Celery_Worker**: Tiến trình xử lý job bất đồng bộ
- **SSD_Buffer**: Thư mục tạm trên SSD dùng ghi đệm file trong quá trình xử lý
- **Transcode**: Chuyển đổi video sang MP4 H.264 chuẩn mạng xã hội

## Requirements

### Requirement 1: Tiếp nhận Job Xử lý Media

**User Story:** Là một Content Creator, tôi muốn upload ảnh/video và hệ thống tự động xử lý bất đồng bộ để tôi không phải chờ đợi.

#### Acceptance Criteria
1. WHEN DMS hoặc Content Service gửi yêu cầu qua Kafka topic `media.process.requested` với: file_id, tenant_id, source_path (MinIO path), media_type (image/video), processing_options, THE Media_Processor SHALL tạo Processing_Job mới với trạng thái `queued` và trả về job_id ngay lập tức
2. THE Media_Processor SHALL đưa Processing_Job vào Celery queue trong Redis với priority: image jobs cao hơn video jobs
3. THE Media_Processor SHALL cung cấp API GET /jobs/{job_id} trả về trạng thái hiện tại; áp dụng tenant isolation — chỉ trả về job thuộc tenant_id trong JWT
4. IF media_type không phải `image` hoặc `video`, THEN THE Media_Processor SHALL từ chối job và trả về lỗi media_type không được hỗ trợ
5. IF source_path không tồn tại trong MinIO, THEN THE Media_Processor SHALL chuyển job sang `failed` ngay lập tức và publish event `media.job.failed` mà không retry

### Requirement 2: Xử lý Ảnh

**User Story:** Là một Content Creator, tôi muốn ảnh upload được tự động nén và tạo thumbnail nhiều kích thước để tối ưu hiển thị.

#### Acceptance Criteria
1. WHEN Celery_Worker nhận image job, THE Media_Processor SHALL tải file ảnh gốc từ MinIO xuống SSD_Buffer trước khi xử lý
2. THE Media_Processor SHALL nén ảnh gốc sang WebP với quality=85%; nếu ảnh gốc đã là WebP, THE Media_Processor SHALL vẫn re-encode để đảm bảo chất lượng đồng nhất
3. THE Media_Processor SHALL tạo thumbnail ở 3 kích thước: small (150×150px), medium (400×400px), large (800×800px); crop center để giữ tỷ lệ vuông
4. THE Media_Processor SHALL lưu ảnh đã nén và thumbnails vào MinIO path `{tenant_id}/processed/{file_id}/` với tên: original.webp, thumb_small.webp, thumb_medium.webp, thumb_large.webp
5. IF kích thước ảnh gốc nhỏ hơn kích thước thumbnail yêu cầu, THEN THE Media_Processor SHALL bỏ qua thumbnail đó và ghi nhận trong job result mà không coi là lỗi
6. WHEN xử lý ảnh hoàn tất, THE Media_Processor SHALL xóa toàn bộ file tạm trong SSD_Buffer của job đó

### Requirement 3: Xử lý Video

**User Story:** Là một Content Creator, tôi muốn video upload được tự động transcode sang định dạng chuẩn mạng xã hội.

#### Acceptance Criteria
1. IF kích thước file video vượt quá 100MB, THEN THE Media_Processor SHALL từ chối job ngay khi tiếp nhận, chuyển sang `failed` và publish event `media.job.failed` với lý do vượt giới hạn kích thước
2. WHEN Celery_Worker nhận video job, THE Media_Processor SHALL tải file video từ MinIO xuống SSD_Buffer; không load file vào RAM
3. THE Media_Processor SHALL transcode video sang: MP4 container, codec H.264 (libx264), audio AAC 128kbps, độ phân giải tối đa 1080p (giữ tỷ lệ khung hình gốc nếu nhỏ hơn 1080p)
4. THE Media_Processor SHALL tạo thumbnail video từ frame tại giây thứ 1, lưu JPEG quality=90%, kích thước 1280×720px (letterbox nếu tỷ lệ khác)
5. THE Media_Processor SHALL lưu video đã transcode và thumbnail vào MinIO path `{tenant_id}/processed/{file_id}/` với tên: video.mp4, thumb_video.jpg
6. WHEN xử lý video hoàn tất hoặc thất bại, THE Media_Processor SHALL xóa toàn bộ file tạm trong SSD_Buffer để giải phóng dung lượng

### Requirement 4: Retry và Xử lý Lỗi

**User Story:** Là một System Admin, tôi muốn hệ thống tự động thử lại khi xử lý thất bại và thông báo rõ ràng khi job không thể phục hồi.

#### Acceptance Criteria
1. IF Celery_Worker gặp lỗi trong quá trình xử lý (lỗi I/O, lỗi transcode, lỗi upload MinIO), THEN THE Media_Processor SHALL tự động retry tối đa 3 lần với exponential backoff: lần 1 sau 30s, lần 2 sau 60s, lần 3 sau 120s
2. WHEN retry bắt đầu, THE Media_Processor SHALL cập nhật trạng thái Processing_Job về `queued` kèm retry_count hiện tại
3. IF job vẫn thất bại sau lần retry thứ 3, THEN THE Media_Processor SHALL chuyển sang `failed` vĩnh viễn và publish Kafka event `media.job.failed` với: job_id, tenant_id, file_id, error_message, retry_count=3
4. THE Media_Processor SHALL xóa file tạm trong SSD_Buffer của job thất bại sau khi chuyển sang `failed`
5. IF SSD_Buffer hết dung lượng (disk usage > 90%), THEN THE Media_Processor SHALL từ chối nhận job mới, trả về lỗi không đủ dung lượng đệm, và ghi cảnh báo vào log

### Requirement 5: Progress Tracking và Event Publishing

**User Story:** Là một DMS/Content Service, tôi muốn nhận thông báo khi media processing hoàn tất để cập nhật record mà không cần polling liên tục.

#### Acceptance Criteria
1. WHEN Celery_Worker bắt đầu xử lý, THE Media_Processor SHALL cập nhật trạng thái Processing_Job sang `processing` kèm timestamp bắt đầu
2. WHEN job xử lý thành công, THE Media_Processor SHALL cập nhật sang `done` kèm: timestamp hoàn tất, output_paths (MinIO paths), file_sizes (bytes) của từng output
3. WHEN job chuyển sang `done`, THE Media_Processor SHALL publish Kafka event `media.job.completed` với: job_id, tenant_id, file_id, output_paths, media_type, completed_at
4. WHEN job chuyển sang `failed`, THE Media_Processor SHALL publish Kafka event `media.job.failed` với: job_id, tenant_id, file_id, error_message, failed_at
5. THE Media_Processor SHALL đảm bảo event được publish sau khi trạng thái đã ghi vào DB; nếu publish Kafka thất bại, THE Media_Processor SHALL retry publish tối đa 3 lần trước khi ghi vào dead-letter queue
6. THE Media_Processor SHALL expose API GET /jobs/{job_id}/status trả về trạng thái trong vòng 200ms với tenant isolation

## Security & Access Control
- **Authentication & Authorization:** APIs của Media Processor Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `media-processor`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Media Processor Service.
- **Tenant Isolation:** Dữ liệu Media Processor **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.
