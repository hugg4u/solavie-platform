# Requirements Document

## Introduction

Document Management Service (DMS) của Solavie Marketing Platform — quản lý toàn bộ vòng đời tệp tin và tài liệu: upload có kiểm tra định dạng và quét mã độc, kiểm soát quota lưu trữ per-tenant, cấu trúc thư mục ảo dạng cây, chế độ truy cập Public/Private hybrid, kiểm soát phiên bản tệp, soft delete với trash 30 ngày, resumable upload cho file lớn, và data retention tự động.

## Tech Stack
- **Language:** Node.js 20
- **Framework:** NestJS
- **Port:** 3007
- **Database:** PostgreSQL (dms_db) với Row-Level Security per tenant_id
- **Object Storage:** MinIO (S3-compatible API)
- **Queue:** Kafka (consumer + producer)
- **Cache:** Redis (config hot-reload, presigned URL cache)

## Glossary
- **DMS**: Document Management Service — service này
- **Virtual Folder**: Thư mục ảo lưu trong DB (dms_folders), không phải thư mục vật lý trên MinIO
- **Access Mode**: Chế độ truy cập: `public` (CDN URL cố định) hoặc `private` (Presigned URL TTL 15 phút)
- **Presigned URL**: URL có chữ ký thời gian do MinIO sinh ra, hết hạn sau 15 phút
- **Soft Delete**: Đánh dấu tệp/thư mục là đã xóa (deleted_at) mà không xóa vật lý ngay
- **Trash**: Vùng chứa các tệp/thư mục đã soft delete, giữ tối đa 30 ngày
- **Quota**: Hạn mức dung lượng lưu trữ tối đa của Tenant (dms_max_storage_mb)
- **Resumable Upload**: Cơ chế upload multipart cho phép tiếp tục từ điểm dừng khi mất kết nối

## Requirements

### Requirement 1: File Upload & Format Validation

**User Story:** Là một Agent hoặc Kỹ thuật viên, tôi muốn upload tệp tin lên hệ thống và được thông báo ngay nếu định dạng không hợp lệ.

#### Acceptance Criteria
1. WHEN người dùng gửi yêu cầu upload tệp, THE DMS SHALL kiểm tra MIME type và phần mở rộng; chỉ chấp nhận: PDF (.pdf), DOCX (.docx), TXT (.txt), MD (.md), JPEG (.jpg/.jpeg), PNG (.png), WebP (.webp), MP4 (.mp4), MOV (.mov)
2. IF tệp có MIME type hoặc phần mở rộng không thuộc danh sách cho phép, THEN THE DMS SHALL từ chối upload và trả về lỗi chỉ rõ định dạng không được hỗ trợ; không lưu bất kỳ dữ liệu nào
3. THE DMS SHALL giới hạn kích thước tệp: tối đa 50 MB cho tài liệu (PDF, DOCX, TXT, MD) và 100 MB cho media (ảnh, video)
4. IF kích thước tệp vượt giới hạn, THEN THE DMS SHALL từ chối upload và trả về lỗi chỉ rõ kích thước tối đa và kích thước thực tế
5. WHEN upload tệp thành công, THE DMS SHALL tạo bản ghi trong dms_files và dms_file_versions với đầy đủ metadata: file_size, mime_type, storage_path, uploaded_by, uploaded_at
6. WHEN upload tệp ảnh hoặc video thành công, THE DMS SHALL publish event `dms.file.uploaded` lên Kafka để Media_Processor nhận và xử lý bất đồng bộ
7. THE DMS SHALL xác thực tenant_id trong request khớp với JWT claims; từ chối nếu không khớp

### Requirement 2: Storage Quota Management

**User Story:** Là một Tenant Admin, tôi muốn hệ thống tự động kiểm soát dung lượng lưu trữ để không vượt quá hạn mức đã đăng ký.

#### Acceptance Criteria
1. WHEN người dùng gửi yêu cầu upload, THE DMS SHALL tính tổng dung lượng đang sử dụng của Tenant và so sánh với giới hạn dms_max_storage_mb từ Tenant Config
2. IF tổng dung lượng hiện tại + kích thước tệp mới > dms_max_storage_mb × 1,048,576 bytes, THEN THE DMS SHALL từ chối upload và trả về lỗi chỉ rõ dung lượng đã dùng, còn lại và giới hạn tối đa
3. THE DMS SHALL đọc dms_max_storage_mb từ Redis cache key `{tenant_id}:config:dms`; nếu cache miss thì truy vấn Tenant Config Service và cache lại trong 60 giây
4. THE DMS SHALL cung cấp API trả về thông tin quota: tổng đã dùng (bytes), còn lại (bytes), giới hạn tối đa (bytes), tỷ lệ sử dụng (%)
5. WHEN tổng dung lượng vượt 80% giới hạn, THE DMS SHALL publish event `dms.quota.warning` lên Kafka để Notification Service gửi cảnh báo đến Tenant Admin

### Requirement 3: Virtual Folder Tree

**User Story:** Là một Tenant Admin, tôi muốn tạo cấu trúc thư mục ảo dạng cây để phân loại tài liệu theo dự án, khách hàng hoặc loại nội dung.

#### Acceptance Criteria
1. THE DMS SHALL cho phép tạo thư mục ảo với: name (tối đa 255 ký tự), parent_folder_id (null = thư mục gốc), access_mode (public/private), tenant_id
2. THE DMS SHALL hỗ trợ cấu trúc cây đệ quy không giới hạn độ sâu qua self-referencing parent_folder_id
3. THE DMS SHALL cho phép di chuyển thư mục sang thư mục cha khác; khi di chuyển, tất cả thư mục con và tệp bên trong phải được di chuyển theo
4. IF thư mục đích là thư mục con của thư mục nguồn (tạo vòng lặp đệ quy), THEN THE DMS SHALL từ chối thao tác và trả về lỗi
5. THE DMS SHALL cho phép đổi tên thư mục; tên phải duy nhất trong cùng thư mục cha và cùng tenant_id
6. THE DMS SHALL cung cấp API trả về toàn bộ cây thư mục của Tenant dạng JSON lồng nhau, bao gồm số lượng tệp trực tiếp trong mỗi thư mục

### Requirement 4: Access Mode — Public & Private Hybrid

**User Story:** Là một Content Creator, tôi muốn kiểm soát quyền truy cập: ảnh bài viết cần URL cố định, tài liệu nội bộ cần link có thời hạn.

#### Acceptance Criteria
1. THE DMS SHALL hỗ trợ hai chế độ truy cập cho thư mục: `public` và `private`; tệp tin kế thừa access_mode từ thư mục chứa nó
2. WHEN tệp thuộc thư mục public, THE DMS SHALL trả về MinIO URL cố định không cần JWT token
3. WHEN tệp thuộc thư mục private, THE DMS SHALL sinh Presigned URL với TTL chính xác 900 giây (15 phút)
4. IF request truy cập tệp private không có JWT Bearer token hợp lệ, THEN THE DMS SHALL từ chối và trả về lỗi xác thực
5. IF JWT hợp lệ nhưng tenant_id không khớp với tenant_id của tệp, THEN THE DMS SHALL từ chối và trả về lỗi phân quyền
6. THE DMS SHALL cho phép thay đổi access_mode của thư mục; khi thay đổi, tất cả tệp trong thư mục phải được cập nhật access_mode ngay lập tức

### Requirement 5: File Version Control

**User Story:** Là một Agent, tôi muốn hệ thống tự động lưu lịch sử phiên bản khi upload tệp trùng tên để có thể khôi phục phiên bản cũ.

#### Acceptance Criteria
1. WHEN người dùng upload tệp có cùng tên vào cùng thư mục trong cùng tenant, THE DMS SHALL tự động tạo phiên bản mới: tăng current_version lên 1, tạo bản ghi mới trong dms_file_versions
2. THE DMS SHALL lưu tối đa N phiên bản cho mỗi tệp, với N = dms_max_file_versions từ Tenant Config (mặc định 5, phạm vi 1-20)
3. WHEN số phiên bản đạt N sau khi tạo phiên bản mới, THE DMS SHALL tự động xóa phiên bản cũ nhất: xóa bản ghi dms_file_versions và xóa tệp vật lý trên MinIO
4. THE DMS SHALL cung cấp API trả về danh sách tất cả phiên bản của một tệp: version number, file_size, mime_type, uploaded_by, uploaded_at
5. THE DMS SHALL cho phép tải xuống bất kỳ phiên bản cụ thể nào bằng cách chỉ định version number
6. THE DMS SHALL cho phép khôi phục (restore) phiên bản cũ thành phiên bản hiện tại: tạo bản ghi mới sao chép từ phiên bản được chọn với version = current_version + 1

### Requirement 6: Soft Delete & Trash Management

**User Story:** Là một Agent, tôi muốn xóa tệp mà không mất dữ liệu ngay lập tức để có thể khôi phục nếu xóa nhầm trong vòng 30 ngày.

#### Acceptance Criteria
1. WHEN người dùng xóa tệp hoặc thư mục, THE DMS SHALL thực hiện soft delete: ghi timestamp vào deleted_at trong DB; không xóa bản ghi DB và không xóa tệp vật lý trên MinIO ngay
2. WHEN người dùng xóa thư mục, THE DMS SHALL soft delete đệ quy tất cả thư mục con và tệp bên trong cùng một transaction
3. THE DMS SHALL cung cấp API liệt kê tất cả tệp và thư mục trong trash của Tenant, sắp xếp theo deleted_at giảm dần, phân trang tối đa 100 items/page
4. THE DMS SHALL cho phép khôi phục tệp hoặc thư mục từ trash: xóa giá trị deleted_at; nếu thư mục cha đã bị xóa, tệp được khôi phục về thư mục gốc
5. THE DMS SHALL chạy background job mỗi ngày lúc 03:00 AM (UTC+7) để xóa vĩnh viễn tất cả tệp và thư mục có deleted_at < (thời điểm hiện tại - 30 ngày): xóa bản ghi DB và xóa tệp vật lý trên MinIO
6. THE DMS SHALL cung cấp API cho phép permanent delete ngay lập tức từ trash mà không cần chờ 30 ngày; yêu cầu xác nhận rõ ràng trong request body

### Requirement 7: Resumable Upload

**User Story:** Là một Kỹ thuật viên upload ảnh/video khảo sát từ điện thoại với kết nối không ổn định, tôi muốn upload lớn không bị mất khi mạng bị ngắt.

#### Acceptance Criteria
1. THE DMS SHALL áp dụng resumable upload (MinIO S3 Multipart API) cho tất cả tệp có kích thước > 10 MB
2. WHEN bắt đầu resumable upload, THE DMS SHALL khởi tạo upload session và trả về upload_id duy nhất; upload_id có hiệu lực trong 24 giờ
3. THE DMS SHALL chia tệp thành các phần (parts) kích thước 5 MB đến 100 MB; client gửi từng phần kèm part_number và upload_id
4. WHEN nhận được một phần upload, THE DMS SHALL xác nhận tính toàn vẹn bằng MD5 checksum; từ chối phần có checksum không khớp và yêu cầu gửi lại
5. THE DMS SHALL cung cấp API trả về danh sách các phần đã upload thành công cho một upload_id
6. WHEN tất cả phần đã upload và client gửi yêu cầu hoàn tất, THE DMS SHALL ghép các phần lại trên MinIO, sau đó thực hiện kiểm tra định dạng, quota và malware scan
7. IF upload_id hết hạn hoặc client hủy, THEN THE DMS SHALL xóa tất cả phần đã upload tạm thời trên MinIO và xóa upload session khỏi DB

### Requirement 8: Malware Scanning

**User Story:** Là một Tenant Admin, tôi muốn mọi tệp tin được quét mã độc trước khi lưu vào kho để bảo vệ hệ thống.

#### Acceptance Criteria
1. THE DMS SHALL quét mã độc cho mọi tệp tin trước khi lưu vĩnh viễn vào MinIO; quét được thực hiện sau khi kiểm tra định dạng và quota thành công
2. WHEN quét hoàn tất và tệp sạch, THE DMS SHALL tiến hành lưu tệp vào MinIO và tạo bản ghi metadata trong DB
3. IF quét phát hiện mã độc, THEN THE DMS SHALL từ chối lưu tệp, xóa tệp tạm thời, trả về lỗi chỉ rõ tệp bị từ chối do phát hiện mã độc; không tiết lộ chi tiết kỹ thuật về loại mã độc
4. IF dịch vụ quét không phản hồi trong vòng 30 giây, THEN THE DMS SHALL từ chối upload, xóa tệp tạm thời và trả về lỗi dịch vụ kiểm tra bảo mật tạm thời không khả dụng
5. THE DMS SHALL log tất cả kết quả quét vào audit log: tenant_id, file_name, file_size, scan_result, timestamp
6. WHEN phát hiện mã độc, THE DMS SHALL publish event `dms.file.malware_detected` lên Kafka để Notification Service gửi cảnh báo đến Tenant Admin trong vòng 60 giây

### Requirement 9: Cross-Service Integration

**User Story:** Là một hệ thống, tôi muốn DMS tích hợp chặt chẽ với CRM, Knowledge Base, Content Service và Media Processor để các luồng nghiệp vụ hoạt động liền mạch.

#### Acceptance Criteria
1. THE DMS SHALL cung cấp REST API cho CRM_Service để upload ảnh khảo sát mái vào thư mục chỉ định bởi crm_surveys.media_folder_id; trả về file_id và storage_path
2. THE DMS SHALL cung cấp REST API cho CRM_Service để lưu Proposal PDF dạng Private và trả về dms_file_id để CRM lưu vào crm_proposals.dms_file_id
3. THE DMS SHALL cung cấp REST API cho Knowledge_Base Service để upload tài liệu huấn luyện chatbot (PDF, DOCX, TXT, MD tối đa 50 MB); trả về storage_path để Knowledge_Base xử lý chunking
4. THE DMS SHALL cung cấp REST API cho Content_Service để upload ảnh/video bài viết marketing vào thư mục public; trả về public URL cố định
5. WHEN tệp ảnh hoặc video được upload thành công, THE DMS SHALL publish event `dms.file.uploaded` lên Kafka với: file_id, tenant_id, storage_path, mime_type, file_size để Media_Processor consume và xử lý
6. THE DMS SHALL xác thực service-to-service calls qua JWT Client Credentials token; từ chối request không có token hợp lệ hoặc không có quyền dms:write

## Security & Access Control
- **Authentication & Authorization:** APIs của Dms Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `dms`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Dms Service.
- **Tenant Isolation:** Dữ liệu Dms **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.
