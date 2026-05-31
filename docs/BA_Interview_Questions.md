# BẢNG CÂU HỎI PHỎNG VẤN NGHIỆP VỤ (BA INTERVIEW QUESTIONS)
## DỰ ÁN: NỀN TẢNG MARKETING ĐA KÊNH TÍCH HỢP AI

Chào bạn, để có cơ sở xây dựng tài liệu đặc tả yêu cầu nghiệp vụ **BRD (Business Requirements Document)** chuẩn xác nhất, bạn vui lòng điền câu trả lời của mình ngay dưới mỗi câu hỏi dưới đây nhé.

---

### PHẦN 1: ĐỐI TƯỢNG SỬ DỤNG & MÔ HÌNH KINH DOANH (TENANT & USERS)

#### Câu 1.1: Khách hàng doanh nghiệp (Tenants) mục tiêu của nền tảng này là ai? Họ thường hoạt động trong lĩnh vực nào là chủ yếu?
*Ví dụ: Bán lẻ/E-commerce, Giáo dục/Đào tạo, F&B (Nhà hàng), Bất động sản, Clinic/Spa, hay đa dạng mọi ngành nghề?*
> **Trả lời:** [Điền câu trả lời của bạn tại đây]
hiện tại là tập trung vào bán hàng bán dịch vụ, hiện tại phần mềm sẽ phục vụ cho công ty Solavie bán sản phẩm và dịch vụ về năng lượng(như năng lượng mặt trời)
Được tốt nhất thì có thể là đa dạng mọi ngành nghề
Về phần này thì các ngành nghề có gì khác nhau


#### Câu 1.2: Bạn dự kiến phân chia các gói dịch vụ (Free, Standard, Enterprise) dựa trên các giới hạn kinh doanh nào?
*Ví dụ:*
- *Giới hạn theo tính năng (ví dụ: gói Free không có AI chatbot).*
- *Giới hạn theo số lượng (ví dụ: số nhân viên Agent tối đa, số tin nhắn gửi đi mỗi tháng, số trang/fanpage kết nối).*
- *Giới hạn theo ngân sách AI (ví dụ: hạn mức token sử dụng mỗi tháng).*
> **Trả lời:** [Điền câu trả lời của bạn tại đây]
Sẽ có 2 loại là mất phí và không mất phí
với không mất phí thì giới hạn tính năng
còn với mất phí thì sẽ có các gói số lượng

#### Câu 1.3: Bạn có cần thêm các vai trò người dùng (Roles) đặc thù nào khác ngoài 4 vai trò mặc định (Admin, Manager, Agent, Viewer) không?
*Ví dụ:*
- *Cộng tác viên (chỉ được xem và chat với khách hàng được gán cụ thể).*
- *Kiểm duyệt viên nội dung (chỉ có quyền duyệt bài viết AI sinh ra, không có quyền cấu hình hệ thống).*
> **Trả lời:** [Điền câu trả lời của bạn tại đây]
Về phần role thì thì phải làm rõ thêm về nghiệp vụ thực tế của công ty để có thể đưa ra các yêu cầu cụ thể hơn
cần trao đổi thêm
tự tìm hiểu xem cần những role gì rồi tôi review và trao đổi thêm về phần nghiệp vụ
về phần phân quyền t muốn xử lí phân quyền dynamic
nghĩa là sẽ không cố định các role
mà sẽ linh động việc lưu role ở DB và phân quyền dựa trên permission lưu ở DB và gắn cho từng role
Việc xử lí quyền linh động như này có lợi hại là gì thì cũng phải phân tích

---

### PHẦN 2: NGHIỆP VỤ CHAT & QUY TRÌNH CHUYỂN GIAO (CHAT & HANDOFF)

#### Câu 2.1: Thứ tự ưu tiên tích hợp các kênh mạng xã hội (Channels) như thế nào? Ngoài Facebook, Zalo, TikTok, bạn có muốn mở rộng thêm kênh nào khác trong tương lai gần không?
*Ví dụ: Ưu tiên Zalo OA và Facebook trước, TikTok sau. Tương lai cần thêm Telegram, Viber, Website Chat Widget...*
> **Trả lời:** [Điền câu trả lời của bạn tại đây]
hiện tại thì ưu tiên tích hợp Zalo OA và Facebook
trong tương lai có thể mở rộng thêm các kênh khác
cần tự nghiên cứu về cách thức tích hợp các kênh này
và các hạn chế nếu có
với Zalo thì có OA và Zalo business

#### Câu 2.2: Khi Chatbot không tự tin trả lời và cần chuyển sang cho nhân viên (Handoff), bạn muốn hệ thống phân phối cuộc chat theo cơ chế nào?
*Ví dụ:*
- *Cơ chế chia đều (Round-robin): Hệ thống tự động gán lần lượt cho các Agent đang online.*
- *Cơ chế tải tối thiểu (Least busy): Gán cho Agent có ít cửa sổ chat đang mở nhất.*
- *Cơ chế hàng đợi tự chọn (Queue & Claim): Tin nhắn đưa vào hàng đợi chung, Agent nào rảnh tự click nhận (Claim).*
- *Ưu tiên Agent cũ: Gán lại cho Agent đã từng tương tác với khách hàng đó trong vòng 7 ngày qua.*
> **Trả lời:** [Điền câu trả lời của bạn tại đây]
Cái này thì phải phân tích xem phương án nào tối ưu, bạn phải phân tích tối ưu xem mặt lợi hại của từng phương án để t biết lựa chọn chứ
#### Câu 2.3: Xử lý thế nào khi cần Handoff ngoài giờ làm việc (không có nhân viên trực)?
*Ví dụ: Thông báo khách hàng để lại thông tin liên hệ và chatbot tự đóng phiên chat, hoặc chatbot tiếp tục trả lời nhưng đưa ra cảnh báo "Tôi là trợ lý AI, thông tin có thể chưa hoàn toàn chính xác..."?*
> **Trả lời:** [Điền câu trả lời của bạn tại đây]
Cũng phải phân tích mặt lợi mặt hại
nói chung là t không muốn việc mà để AI xử lí tất cả, có thể AI chat bot trả lời không được đúng, và có những nghiệp vụ cần con người phân tích và trả lời
Nếu ngoài giờ làm việc xử lí như nào thì m cũng phải có phương án an toàn nhất tránh cho AI trả lời không đúng làm ảnh hưởng đến chất lượng dịch vụ
---

### PHẦN 3: SÁNG TẠO NỘI DUNG & ĐĂNG BÀI TỰ ĐỘNG (CONTENT & SCHEDULING)

#### Câu 3.1: Doanh nghiệp định nghĩa "giọng điệu thương hiệu" (Brand Voice) cho AI bằng cách nào?
*Ví dụ:*
- *Phương án A: Doanh nghiệp tải lên các bài viết mẫu cũ tốt nhất của họ, AI tự phân tích và học tone giọng.*
- *Phương án B: Doanh nghiệp tự chọn các cấu hình có sẵn (ví dụ: Hài hước, Trang trọng, Thân thiện, Thuyết phục) kết hợp nhập danh sách từ khóa nên dùng/tránh dùng.*
- *Phương án C: Cả hai phương án trên.*
> **Trả lời:** [Điền câu trả lời của bạn tại đây]
Cả 2 phương án


#### Câu 3.2: Quy trình phê duyệt bài viết do AI tạo ra sẽ hoạt động như thế nào?
*Ví dụ: Mọi bài viết bắt buộc phải được duyệt bởi Manager mới được chuyển sang Scheduler, hay có chế độ "Tự động đăng" (Auto-publish) đối với các bài đăng đạt điểm chất lượng AI đánh giá trên 90%?*
> **Trả lời:** [Điền câu trả lời của bạn tại đây]
Thêm vào cài đặt chế độ cho cái này cho phép quản trị viên bật tắt
Phải xem thiết kế như nào tối ưu cho việc cài đặt config hệ thống
Hệ thống phải đảm bảo linh hoạt
Các chức năng admin có thể linh hoạt config ngay ở phần cài đặt

---

### PHẦN 4: CÁC YÊU CẦU ĐẶC THÙ KHÁC (NẾU CÓ)

#### Câu 4.1: Bạn có yêu cầu gì về mặt bảo mật thông tin khách hàng trên Dashboard không?
*Ví dụ: Ẩn bớt số điện thoại/email (Data Masking) đối với Agent, chỉ Admin mới xem được đầy đủ.*
> **Trả lời:** [Điền câu trả lời của bạn tại đây]
Cái này cũng có thể cài đặt

#### Câu 4.2: Có bất kỳ quy định pháp lý hoặc tiêu chuẩn nào về dữ liệu mà hệ thống cần tuân thủ không?
*Ví dụ: Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân tại Việt Nam.*
> **Trả lời:** [Điền câu trả lời của bạn tại đây]
Phải tuân thủ pháp luật Việt Nam, tham khảo các phần mềm và cũng sẽ đề ra các điều khoản trong hệ thống
