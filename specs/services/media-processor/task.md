# Task Checklist — MEDIA-PROCESSOR Service

## Overview
This document tracks the implementation checklist for **MEDIA-PROCESSOR Service** based on the system specifications.

### Technical Stack & Configuration
- **Language:** Python 3.12
- **Framework:** FastAPI
- **Workers:** Celery + Redis broker
- **Storage:** MinIO
- **Port:** 8008

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/media-processor/requirements.md)
- [Design](file:///specs/solavie-system/services/media-processor/design.md)

---

## Tasks Checklist

### Task 1: 1: Tiếp nhận Job Xử lý Media
> *User Story: Là một Content Creator, tôi muốn upload ảnh/video và hệ thống tự động xử lý bất đồng bộ để tôi không phải chờ đợi.*

**Acceptance Criteria Implementation:**
- [ ] AC 1.1: WHEN DMS hoặc Content Service gửi yêu cầu qua Kafka topic `media.process.requested` với: file_id, tenant_id, source_path (MinIO path), media_type (image/video), processing_options, THE Media_Processor SHALL tạo Processing_Job mới với trạng thái `queued` và trả về job_id ngay lập tức
- [ ] AC 1.2: THE Media_Processor SHALL đưa Processing_Job vào Celery queue trong Redis với priority: image jobs cao hơn video jobs
- [ ] AC 1.3: THE Media_Processor SHALL cung cấp API GET /jobs/{job_id} trả về trạng thái hiện tại; áp dụng tenant isolation — chỉ trả về job thuộc tenant_id trong JWT
- [ ] AC 1.4: IF media_type không phải `image` hoặc `video`, THEN THE Media_Processor SHALL từ chối job và trả về lỗi media_type không được hỗ trợ
- [ ] AC 1.5: IF source_path không tồn tại trong MinIO, THEN THE Media_Processor SHALL chuyển job sang `failed` ngay lập tức và publish event `media.job.failed` mà không retry

### Task 2: 2: Xử lý Ảnh
> *User Story: Là một Content Creator, tôi muốn ảnh upload được tự động nén và tạo thumbnail nhiều kích thước để tối ưu hiển thị.*

**Acceptance Criteria Implementation:**
- [ ] AC 2.1: WHEN Celery_Worker nhận image job, THE Media_Processor SHALL tải file ảnh gốc từ MinIO xuống SSD_Buffer trước khi xử lý
- [ ] AC 2.2: THE Media_Processor SHALL nén ảnh gốc sang WebP với quality=85%; nếu ảnh gốc đã là WebP, THE Media_Processor SHALL vẫn re-encode để đảm bảo chất lượng đồng nhất
- [ ] AC 2.3: THE Media_Processor SHALL tạo thumbnail ở 3 kích thước: small (150×150px), medium (400×400px), large (800×800px); crop center để giữ tỷ lệ vuông
- [ ] AC 2.4: THE Media_Processor SHALL lưu ảnh đã nén và thumbnails vào MinIO path `{tenant_id}/processed/{file_id}/` với tên: original.webp, thumb_small.webp, thumb_medium.webp, thumb_large.webp
- [ ] AC 2.5: IF kích thước ảnh gốc nhỏ hơn kích thước thumbnail yêu cầu, THEN THE Media_Processor SHALL bỏ qua thumbnail đó và ghi nhận trong job result mà không coi là lỗi
- [ ] AC 2.6: WHEN xử lý ảnh hoàn tất, THE Media_Processor SHALL xóa toàn bộ file tạm trong SSD_Buffer của job đó

### Task 3: 3: Xử lý Video
> *User Story: Là một Content Creator, tôi muốn video upload được tự động transcode sang định dạng chuẩn mạng xã hội.*

**Acceptance Criteria Implementation:**
- [ ] AC 3.1: IF kích thước file video vượt quá 100MB, THEN THE Media_Processor SHALL từ chối job ngay khi tiếp nhận, chuyển sang `failed` và publish event `media.job.failed` với lý do vượt giới hạn kích thước
- [ ] AC 3.2: WHEN Celery_Worker nhận video job, THE Media_Processor SHALL tải file video từ MinIO xuống SSD_Buffer; không load file vào RAM
- [ ] AC 3.3: THE Media_Processor SHALL transcode video sang: MP4 container, codec H.264 (libx264), audio AAC 128kbps, độ phân giải tối đa 1080p (giữ tỷ lệ khung hình gốc nếu nhỏ hơn 1080p)
- [ ] AC 3.4: THE Media_Processor SHALL tạo thumbnail video từ frame tại giây thứ 1, lưu JPEG quality=90%, kích thước 1280×720px (letterbox nếu tỷ lệ khác)
- [ ] AC 3.5: THE Media_Processor SHALL lưu video đã transcode và thumbnail vào MinIO path `{tenant_id}/processed/{file_id}/` với tên: video.mp4, thumb_video.jpg
- [ ] AC 3.6: WHEN xử lý video hoàn tất hoặc thất bại, THE Media_Processor SHALL xóa toàn bộ file tạm trong SSD_Buffer để giải phóng dung lượng

### Task 4: 4: Retry và Xử lý Lỗi
> *User Story: Là một System Admin, tôi muốn hệ thống tự động thử lại khi xử lý thất bại và thông báo rõ ràng khi job không thể phục hồi.*

**Acceptance Criteria Implementation:**
- [ ] AC 4.1: IF Celery_Worker gặp lỗi trong quá trình xử lý (lỗi I/O, lỗi transcode, lỗi upload MinIO), THEN THE Media_Processor SHALL tự động retry tối đa 3 lần với exponential backoff: lần 1 sau 30s, lần 2 sau 60s, lần 3 sau 120s
- [ ] AC 4.2: WHEN retry bắt đầu, THE Media_Processor SHALL cập nhật trạng thái Processing_Job về `queued` kèm retry_count hiện tại
- [ ] AC 4.3: IF job vẫn thất bại sau lần retry thứ 3, THEN THE Media_Processor SHALL chuyển sang `failed` vĩnh viễn và publish Kafka event `media.job.failed` với: job_id, tenant_id, file_id, error_message, retry_count=3
- [ ] AC 4.4: THE Media_Processor SHALL xóa file tạm trong SSD_Buffer của job thất bại sau khi chuyển sang `failed`
- [ ] AC 4.5: IF SSD_Buffer hết dung lượng (disk usage > 90%), THEN THE Media_Processor SHALL từ chối nhận job mới, trả về lỗi không đủ dung lượng đệm, và ghi cảnh báo vào log

### Task 5: 5: Progress Tracking và Event Publishing
> *User Story: Là một DMS/Content Service, tôi muốn nhận thông báo khi media processing hoàn tất để cập nhật record mà không cần polling liên tục.*

**Acceptance Criteria Implementation:**
- [ ] AC 5.1: WHEN Celery_Worker bắt đầu xử lý, THE Media_Processor SHALL cập nhật trạng thái Processing_Job sang `processing` kèm timestamp bắt đầu
- [ ] AC 5.2: WHEN job xử lý thành công, THE Media_Processor SHALL cập nhật sang `done` kèm: timestamp hoàn tất, output_paths (MinIO paths), file_sizes (bytes) của từng output
- [ ] AC 5.3: WHEN job chuyển sang `done`, THE Media_Processor SHALL publish Kafka event `media.job.completed` với: job_id, tenant_id, file_id, output_paths, media_type, completed_at
- [ ] AC 5.4: WHEN job chuyển sang `failed`, THE Media_Processor SHALL publish Kafka event `media.job.failed` với: job_id, tenant_id, file_id, error_message, failed_at
- [ ] AC 5.5: THE Media_Processor SHALL đảm bảo event được publish sau khi trạng thái đã ghi vào DB; nếu publish Kafka thất bại, THE Media_Processor SHALL retry publish tối đa 3 lần trước khi ghi vào dead-letter queue
- [ ] AC 5.6: THE Media_Processor SHALL expose API GET /jobs/{job_id}/status trả về trạng thái trong vòng 200ms với tenant isolation

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
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `media-processor`
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`
