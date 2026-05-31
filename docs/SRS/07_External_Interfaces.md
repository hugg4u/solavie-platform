# 7. GIAO DIỆN NGOẠI VI (EXTERNAL INTERFACES)

> Phần này tuân thủ cấu trúc IEEE 830-1998 Section 3.1. Mô tả chi tiết tất cả các giao diện kết nối giữa hệ thống với người dùng, các hệ thống phần mềm khác, phần cứng, và các giao thức truyền thông.

---

## 7.1. Giao diện người dùng (User Interface - UI)

Hệ thống cung cấp giao diện Dashboard Web (Responsive SPA) xây dựng trên Next.js 14 và TypeScript. Dưới đây là các yêu cầu chi tiết cho các màn hình giao diện cốt lõi:

### 7.1.1. Màn hình Hộp thư hợp nhất (Unified Inbox)
- **Bố cục (Layout):** Chia làm 3 cột từ trái qua phải:
  - **Cột 1 (Danh sách hội thoại):** Chiếm 25% chiều rộng. Hiển thị thanh tìm kiếm, bộ lọc trạng thái/kênh, danh sách các cuộc hội thoại rút gọn (tên khách hàng, avatar, tin nhắn cuối, thời gian, icon kênh nguồn Facebook/Zalo/TikTok).
  - **Cột 2 (Khung chat chính):** Chiếm 50% chiều rộng. Hiển thị tên khách hàng, nút chuyển đổi trạng thái `Auto` / `Manual` trực quan (Toggle switch màu sắc rõ ràng), lịch sử tin nhắn cuộn mượt (real-time chat flow), typing indicator, ô nhập liệu chat hỗ trợ emoji/tệp đính kèm và dropdown chọn Message Tag khi chat ngoài khung 24h.
  - **Cột 3 (Thông tin CRM rút gọn):** Chiếm 25% chiều rộng. Hiển thị thông tin cá nhân khách hàng (Số điện thoại/Email bị che nếu cấu hình bật), nút Merge Contact, lịch sử đơn hàng, ghi chú của Agent và danh sách tags gán cho khách.
- **Trải nghiệm tương tác:**
  - Hiển thị thông báo nhấp nháy dạng chấm đỏ (Badge Count) bên cạnh các cuộc hội thoại chưa đọc.
  - Hỗ trợ phím tắt chuyển nhanh giữa các hội thoại (ví dụ: `Alt + Mũi tên lên/xuống`).

### 7.1.2. Màn hình Lịch bài đăng (Calendar View)
- **Bố cục:** Hiển thị dưới dạng grid lịch tiêu chuẩn (hỗ trợ view theo Tháng, Tuần, Ngày).
- **Trải nghiệm tương tác:**
  - Mỗi bài đăng được hiển thị dưới dạng một thẻ (card) màu sắc phân loại theo trạng thái (Xanh lá: Đã đăng, Xanh dương: Đã lên lịch, Vàng: Chờ duyệt, Đỏ: Lỗi đăng).
  - Hỗ trợ thao tác kéo và thả (Drag-and-Drop) một thẻ bài đăng từ ngày này sang ngày khác để tự động thay đổi lịch đăng bài. Click vào thẻ để mở cửa sổ Preview nội dung chi tiết của từng kênh (Facebook, TikTok, Zalo).

### 7.1.3. Giao diện Cấu hình Tenant (Config Panel)
- **Bố cục:** Menu tab dọc phân chia theo các nhóm cấu hình nghiệp vụ:
  - Tab **AI & Tri thức**: Cấu hình các thông số Chatbot, System Prompt, Vector DB chunk size, Confidence Threshold.
  - Tab **Phân luồng Chat**: Cấu hình giờ làm việc, thuật toán routing, thời gian timeout tự động đóng chat.
  - Tab **Kiểm duyệt & Bảo mật**: Cài đặt phê duyệt bài đăng, danh sách từ cấm, data masking.

---

## 7.2. Giao diện phần mềm (Software Interfaces)

Hệ thống giao tiếp với các phần mềm bên ngoài thông qua các API REST (JSON over HTTPS) và gRPC (HTTP/2 ProtoBuf).

### 7.2.1. API Contracts của các REST Endpoints chính

#### 1. API Cấu hình Tenant (Tenant Config Service - Port 3006)
- **GET** `/api/v1/config`
  - *Mô tả:* Lấy toàn bộ cấu hình hiện tại của Tenant dựa trên token đăng nhập.
  - *Headers:* `Authorization: Bearer <JWT_TOKEN>`
  - *Response (200 OK):*
    ```json
    {
      "tenant_id": "tenant-solavie-99a",
      "ai_kb": {
        "chatbot_enabled": true,
        "confidence_threshold": 0.75,
        "auto_handoff_on_negative": true,
        "ai_vision_invoice_reading": true,
        "rag_relevance_threshold": 0.50
      },
      "chat_routing": {
        "working_hours": {
          "timezone": "Asia/Ho_Chi_Minh",
          "weekly": {
            "monday": {"start": "08:00", "end": "17:30"},
            "tuesday": {"start": "08:00", "end": "17:30"}
          }
        },
        "manual_to_auto_timeout_hours": 2,
        "auto_close_timeout_hours": 24
      }
    }
    ```

- **PUT** `/api/v1/config`
  - *Mô tả:* Cập nhật cấu hình của Tenant (Kích hoạt Hot-reload).
  - *Request Body:* JSON chứa các trường cấu hình cần sửa đổi.
  - *Response (200 OK):* `{"status": "success", "message": "Configuration updated and reloaded successfully."}`
  - *Response (400 Bad Request):* Trả về chi tiết lỗi validate nếu giá trị không hợp lệ (ví dụ: `confidence_threshold` vượt quá 0.95).

#### 2. API Quản lý CRM - Đề xuất Gộp Contact (CRM Service - Port 3003)
- **GET** `/api/v1/crm/merge-suggestions`
  - *Mô tả:* Lấy danh sách các đề xuất gộp contact trùng số điện thoại đang chờ phê duyệt.
  - *Response (200 OK):*
    ```json
    [
      {
        "suggestion_id": "sug-7721-a2bc",
        "primary_contact": {
          "contact_id": "con-fb-001",
          "name": "Nam Nguyen",
          "channel": "facebook",
          "avatar": "https://cdn.fb.com/avatar1.jpg"
        },
        "secondary_contact": {
          "contact_id": "con-zalo-002",
          "name": "Nam Nguyễn",
          "channel": "zalo",
          "avatar": "https://cdn.zalo.com/avatar2.jpg"
        },
        "match_reason": "Identical phone number: 0912345678, name similarity: 92%"
      }
    ]
    ```

- **POST** `/api/v1/crm/merge-suggestions/resolve`
  - *Mô tả:* Chấp nhận gộp hoặc bỏ qua đề xuất.
  - *Request Body:*
    ```json
    {
      "suggestion_id": "sug-7721-a2bc",
      "action": "merge" // hoặc "dismiss"
    }
    ```
  - *Response (200 OK):* `{"status": "success", "merged_contact_id": "con-fb-001"}`

#### 3. API Quản lý tài liệu và tệp tin (DMS Service - Port 3007)
- **POST** `/api/v1/dms/files/upload`
  - *Mô tả:* Upload tệp tin lên hệ thống. Tự động kiểm tra dung lượng quota và validate định dạng tệp.
  - *Headers:* `Authorization: Bearer <JWT_TOKEN>`, `Content-Type: multipart/form-data`
  - *Form Body:*
    - `file`: Tệp tin vật lý (PDF, Image, Video, v.v.)
    - `folder_id`: UUID của thư mục đích (nếu có, nếu để null sẽ lưu ở root)
  - *Response (201 Created):*
    ```json
    {
      "status": "success",
      "file_id": "file-8891-ab2c",
      "name": "danh_muc_san_pham.pdf",
      "version": 1,
      "size": 1524310,
      "mime_type": "application/pdf",
      "storage_path": "tenant-solavie-99a/dms/folder-01a/danh_muc_san_pham.pdf"
    }
    ```
  - *Response (400 Bad Request):* `{"status": "error", "message": "Dung lượng bộ nhớ đã đầy"}` hoặc `{"status": "error", "message": "Định dạng file .exe không được hỗ trợ"}`

- **GET** `/api/v1/dms/files/{file_id}/download`
  - *Mô tả:* Lấy link tải/view tệp tin. Đối với tệp Private, hệ thống tự động redirect sang MinIO Presigned URL có thời hạn 15 phút.
  - *Headers:* `Authorization: Bearer <JWT_TOKEN>` (Không yêu cầu nếu tệp nằm trong thư mục Public)
  - *Response (302 Found / Redirect):*
    - Redirect tới link trực tiếp CDN (nếu Public) hoặc URL dạng: `https://minio.tenant.com/solavie/dms/file.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=...&X-Amz-Expires=900` (nếu Private).

### 7.2.2. Định nghĩa gRPC Services nội bộ
Các dịch vụ nội bộ yêu cầu tốc độ phản hồi cao sử dụng gRPC. Ví dụ dưới đây là file định nghĩa Protocol Buffers (.proto) của luồng Chatbot:

```protobuf
syntax = "proto3";

package chatbot;

option go_package = "./pb";

service ChatbotService {
  // Gửi tin nhắn của khách hàng tới Chatbot và nhận câu trả lời dạng stream
  rpc ProcessMessageStream (ChatMessageRequest) returns (stream ChatMessageResponse);
  
  // Kiểm tra sức khỏe của dịch vụ chatbot
  rpc HealthCheck (HealthRequest) returns (HealthResponse);
}

message ChatMessageRequest {
  string tenant_id = 1;
  string conversation_id = 2;
  string message_id = 3;
  string sender_id = 4;
  string message_text = 5;
  string media_url = 6;
  string message_type = 7; // text, image, file
  int64 timestamp = 8;
}

message ChatMessageResponse {
  string token_text = 1;      // Dữ liệu text dạng streaming (token by token)
  float confidence_score = 2; // Điểm tin cậy của chatbot
  string action_directive = 3; // Lệnh điều khiển đặc biệt: "NONE", "HANDOFF", "OCR_INVOICE"
  bool is_final = 4;          // Đánh dấu kết thúc stream
}

message HealthRequest {}
message HealthResponse {
  string status = 1; // "SERVING", "NOT_SERVING"
}
```

---

## 7.3. Giao diện truyền thông (Communication Interfaces)

### 7.3.1. WebSocket Realtime Events
Dashboard thiết lập kết nối WebSocket tới Gateway (Port 8000), sau đó được định tuyến tới Messaging Service. Các sự kiện chính:

| Event Name (Từ Server) | Mô tả | Payload Schema |
|------------------------|-------|----------------|
| `msg.received` | Đẩy tin nhắn mới của khách về Dashboard. | `{"tenant_id": string, "conversation_id": string, "message": {"id": string, "sender": string, "text": string, "channel": string, "timestamp": int64}}` |
| `msg.typing` | Khách hàng đang gõ tin nhắn. | `{"tenant_id": string, "conversation_id": string, "is_typing": boolean}` |
| `handoff.triggered` | Đổi trạng thái hội thoại và gán Agent. | `{"tenant_id": string, "conversation_id": string, "agent_id": string, "reason": string}` |

### 7.3.2. Cấu trúc Message trên Kafka Topics
Hệ thống sử dụng Apache Kafka làm xương sống truyền thông bất đồng bộ. Tất cả dữ liệu truyền qua Kafka **PHẢI** tuân thủ schema định nghĩa rõ ràng.

#### Ví dụ Schema của topic `channel.message.received` (Normalised Message)
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "NormalizedReceivedMessage",
  "type": "OBJECT",
  "properties": {
    "tenant_id": {"type": "STRING"},
    "channel_source": {"type": "STRING", "enum": ["facebook", "zalo", "tiktok"]},
    "channel_id": {"type": "STRING"},
    "sender_id": {"type": "STRING"},
    "message_id": {"type": "STRING"},
    "message_type": {"type": "STRING", "enum": ["text", "image", "file", "sticker"]},
    "content": {"type": "STRING"},
    "attachments": {
      "type": "ARRAY",
      "items": {
        "type": "OBJECT",
        "properties": {
          "type": {"type": "STRING"},
          "url": {"type": "STRING"}
        }
      }
    },
    "timestamp": {"type": "INTEGER"}
  },
  "required": ["tenant_id", "channel_source", "channel_id", "sender_id", "message_id", "message_type", "timestamp"]
}
```

---

## 7.4. Tích hợp Hệ thống bên thứ ba (Third-party System Interfaces)

Hệ thống kết nối và tương tác với các API nền tảng ngoại vi sau:

### 7.4.1. Facebook Graph API v18.0+
- **Mục đích:** Nhận tin nhắn/bình luận của Page qua Webhook; gửi tin nhắn trả lời qua `/me/messages` endpoint; ẩn/xóa bình luận bài viết qua `/{comment-id}` endpoint.
- **Phương thức xác thực:** App Secret để verify webhook signature; Page Access Token (được rotate định kỳ) gửi trong HTTP Header của các Outbound requests.
- **Ràng buộc:** Tuân thủ chặt chẽ chính sách giới hạn 24 giờ của Meta đối với luồng chat miễn phí.

### 7.4.2. Zalo OA Open API v3
- **Mục đích:** Lắng nghe Webhook tin nhắn gửi tới Zalo Official Account; gửi tin phản hồi qua API chat; gửi tin nhắn Broadcast hàng loạt theo danh sách followers.
- **Xác thực:** OAuth 2.0 sử dụng Access Token (hạn 25 tháng nhưng tự động rotate qua Refresh Token mỗi 30 ngày).
- **Ràng buộc:** Giới hạn hạn mức gửi tin nhắn Zalo ZNS và Broadcast theo các chính sách gói dịch vụ Zalo OA đã đăng ký.

### 7.4.3. OpenAI API & Anthropic API
- **Mục đích:** Gọi các mô hình LLM (`GPT-4o-mini`, `GPT-4o`, `Claude 3.5 Sonnet`) để phân tích ngôn ngữ tự nhiên, sinh câu trả lời chatbot, sinh bài viết marketing và phân tích hình ảnh hóa đơn (Vision).
- **Xác thực:** API Keys của Tenant hoặc API Key dùng chung của hệ thống lưu mã hóa trong Vault/Config DB.
- **Tối ưu:** Áp dụng cơ chế Prompt Caching để giảm thời gian xử lý và giảm chi phí token.

---

*← [Trước: Non-Functional Requirements](./06_NonFunctional_Requirements.md) | [Về Mục lục](./00_SRS_Index.md) | [Tiếp: Data Models →](./08_Data_Models.md)*
