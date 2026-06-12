# Business-logic — Media-processor Service


---

## Lifespan Registry Logic & Health API Flow (Tối ưu hóa)
*   **Startup Flow:**
    1. Khởi tạo ứng dụng và kết nối cơ sở dữ liệu.
    2. Gọi hàm lấy IP động -> Định danh node `{ip}:{port}`.
    3. Gửi lệnh `SADD` và `SETEX` lên Redis Registry. Nếu kết nối Redis bị lỗi, log Warning và tiếp tục chạy ứng dụng (Fail-safe), không được crash tiến trình chính.
    4. Bắt đầu Interval Heartbeat mỗi 5 giây.
*   **Shutdown Flow (Graceful):**
    1. Nhận tín hiệu `SIGTERM` hoặc `SIGINT`.
    2. Dừng Interval Heartbeat.
    3. Gửi lệnh `SREM` và `DEL` lên Redis Registry.
    4. Giải phóng các kết nối Database, Redis và exit.
