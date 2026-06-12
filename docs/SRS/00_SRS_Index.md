# TÀI LIỆU ĐẶC TẢ YÊU CẦU PHẦN MỀM (SOFTWARE REQUIREMENTS SPECIFICATION)

## DỰ ÁN: NỀN TẢNG MARKETING ĐA KÊNH TÍCH HỢP AI
### AI-POWERED MULTI-CHANNEL MARKETING PLATFORM

---

| Thông tin | Chi tiết |
|-----------|----------|
| **Mã dự án** | MKT-PLATFORM-2026 |
| **Phiên bản** | 1.6.0 |
| **Ngày tạo** | 30/05/2026 |
| **Chuẩn áp dụng** | IEEE 830-1998 / ISO/IEC/IEEE 29148:2018 |
| **Trạng thái** | Draft |
| **Bảo mật** | Confidential |

---

## Lịch sử chỉnh sửa (Revision History)

| Phiên bản | Ngày | Tác giả | Mô tả thay đổi |
|-----------|------|---------|-----------------|
| 0.1.0 | 28/05/2026 | BA Team | Khởi tạo SRS sơ bộ (kiến trúc tổng quan) |
| 0.5.0 | 29/05/2026 | BA Team | Bổ sung nghiệp vụ chi tiết từ BRD, Config-Driven Architecture |
| 1.0.0 | 30/05/2026 | BA Team | Nâng cấp toàn diện theo chuẩn IEEE 830/29148. Bổ sung Use Cases, User Stories, NFR, Data Models, RTM |
| 1.1.0 | 30/05/2026 | BA Team | Bổ sung phân hệ DMS Service (Document Management System) quản lý tệp tin và tài liệu |
| 1.2.0 | 30/05/2026 | BA Team | Bổ sung 3 phân hệ lõi: Link Shortener (Theo dõi CTR), Media Processing (Xử lý media) và Data Retention (Dọn dẹp dữ liệu) |
| 1.3.0 | 30/05/2026 | BA Team | Bổ sung đặc tả nghiệp vụ Solar chuyên biệt: Deal Pipeline, Solar Calculator và O&M Ticketing |
| 1.4.0 | 30/05/2026 | BA Team | Tối ưu hóa lõi AI: Phân tách Stateful Chatbot/Stateless AI Core, tích hợp rào chắn an toàn (Dual-layer Guardrails), Multi-tenant MCP Gateway, tối ưu hóa token (Prompt Caching & Summarization), và Human-in-the-loop có cấu hình. |
| 1.5.0 | 30/05/2026 | BA Team | Rà soát và vá 12 lỗ hổng so với BRD (Gap Analysis Remediation): Bổ sung Consent NĐ 13/2023, Right to Erasure, Lead Scoring engine, tích hợp TikTok, CSAT survey và sửa các tham chiếu chéo lỗi trong RTM. |
| 1.6.0 | 31/05/2026 | BA Team | Nâng cấp lõi AI Core: Bổ sung định tuyến mô hình động (Dynamic Model Routing), quản lý khóa API mã hóa đối xứng AES-256, và tích hợp bộ giả lập chi phí (Cost Simulator) |
| 1.7.0 | 12/06/2026 | BA Team | **Đồng bộ hóa đặc tả RAG Quality & Query Rewriting:** Bổ sung các Use Cases, Functional Requirements và Data Models cho cơ chế Query Rewriting và Analytics Service giám sát chất lượng RAG. |

---

## Phê duyệt tài liệu (Document Approval)

| Vai trò | Họ tên | Chữ ký | Ngày |
|---------|--------|--------|------|
| Product Owner | ___________________ | _________ | ____/____/2026 |
| Technical Lead | ___________________ | _________ | ____/____/2026 |
| QA Lead | ___________________ | _________ | ____/____/2026 |
| Project Manager | ___________________ | _________ | ____/____/2026 |

---

## Mục lục tổng (Table of Contents)

### Phần 1: Giới thiệu & Tổng quan
| # | Tài liệu | Nội dung chính |
|---|----------|----------------|
| 01 | [Introduction](./01_Introduction.md) | Mục tiêu, phạm vi, thuật ngữ, tham chiếu tài liệu |
| 02 | [Overall Description](./02_Overall_Description.md) | Bối cảnh sản phẩm, phân loại người dùng, ràng buộc, giả định |

### Phần 2: Đặc tả Nghiệp vụ
| # | Tài liệu | Nội dung chính |
|---|----------|----------------|
| 03 | [Use Cases](./03_Use_Cases.md) | 38 Use Cases chi tiết với Main/Alternative/Exception Flows |
| 04 | [User Stories](./04_User_Stories.md) | 75+ User Stories với Acceptance Criteria (Given-When-Then) |

### Phần 3: Yêu cầu Kỹ thuật
| # | Tài liệu | Nội dung chính |
|---|----------|----------------|
| 05 | [Functional Requirements](./05_Functional_Requirements.md) | 145+ yêu cầu chức năng có mã định danh FR-xxx |
| 06 | [Non-Functional Requirements](./06_NonFunctional_Requirements.md) | Performance, Security, Reliability, Scalability, Usability |

### Phần 4: Giao diện & Dữ liệu
| # | Tài liệu | Nội dung chính |
|---|----------|----------------|
| 07 | [External Interfaces](./07_External_Interfaces.md) | UI Requirements, API Contracts, Communication Protocols |
| 08 | [Data Models](./08_Data_Models.md) | ERD, Database Schema, Data Dictionary, Data Flow |

### Phần 5: Kiến trúc & Tiêu chuẩn
| # | Tài liệu | Nội dung chính |
|---|----------|----------------|
| 09 | [System Architecture](./09_System_Architecture.md) | Microservices Architecture, Deployment, Communication |
| 10 | [Standards & Resilience](./10_Standards_Resilience.md) | AI Confidence Scale, Saga Pattern, Error Format, Risk Assessment |

### Phần 6: Truy vết & Phụ lục
| # | Tài liệu | Nội dung chính |
|---|----------|----------------|
| 11 | [Traceability Matrix](./11_Traceability_Matrix.md) | Ma trận truy vết: BRD → FR → UC → US → Test Case |
| 12 | [Appendices](./12_Appendices.md) | Glossary mở rộng, tài liệu tham khảo, Change Request template |


---

## Quy ước tài liệu (Document Conventions)

### Quy ước mã định danh

| Prefix | Ý nghĩa | Ví dụ |
|--------|---------|-------|
| `UC-XX` | Use Case | UC-01: Đăng nhập hệ thống |
| `US-XXX` | User Story | US-001: Agent đăng nhập Dashboard |
| `FR-MODULE-XXX` | Functional Requirement | FR-MSG-001: Hiển thị Unified Inbox |
| `NFR-XXX` | Non-Functional Requirement | NFR-001: API response time < 200ms |
| `IF-XXX` | Interface Requirement | IF-001: Facebook Graph API v18+ |
| `DM-XXX` | Data Model | DM-001: Bảng conversations |
| `TC-XXX` | Test Case | TC-MSG-001: Kiểm tra lọc inbox theo kênh |

### Quy ước mức độ ưu tiên (MoSCoW)

| Ký hiệu | Mức độ | Mô tả |
|----------|--------|-------|
| 🔴 **Must Have** | Bắt buộc | Hệ thống không thể vận hành nếu thiếu yêu cầu này |
| 🟡 **Should Have** | Nên có | Quan trọng nhưng hệ thống vẫn hoạt động được nếu thiếu |
| 🟢 **Could Have** | Có thể có | Cải thiện trải nghiệm nhưng không ảnh hưởng nghiệp vụ cốt lõi |
| ⚪ **Won't Have** | Không làm (lần này) | Xác định rõ những gì KHÔNG nằm trong phạm vi phiên bản này |

### Quy ước từ khóa yêu cầu (RFC 2119)

| Từ khóa | Ý nghĩa |
|---------|---------|
| **PHẢI** (SHALL/MUST) | Yêu cầu bắt buộc tuyệt đối |
| **NÊN** (SHOULD) | Khuyến nghị mạnh, có thể bỏ qua với lý do chính đáng |
| **CÓ THỂ** (MAY) | Tùy chọn, không bắt buộc |
| **KHÔNG ĐƯỢC** (SHALL NOT) | Cấm tuyệt đối |

---

## Tài liệu liên quan

| Tài liệu | Đường dẫn | Mô tả |
|-----------|-----------|-------|
| Business Requirements Document (BRD) | [BRD.md](../BRD.md) | Yêu cầu nghiệp vụ, quy trình kinh doanh, config schema |
| BA Interview Notes | [BA_Interview_Questions.md](../BA_Interview_Questions.md) | Ghi chép phỏng vấn nghiệp vụ với stakeholders |
| SRS Legacy (v0.5) | [SRS.md](../SRS.md) | Phiên bản SRS sơ bộ (tham khảo) |
