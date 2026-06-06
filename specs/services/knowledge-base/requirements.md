# Requirements — Knowledge Base Service

## Overview
Dịch vụ RAG pipeline — upload tài liệu, semantic chunking, embedding, hybrid search (vector + BM25), reranking. Foundation cho Chatbot và Content AI.

### Tech Stack
- **Language:** Python 3.12
- **Framework:** FastAPI
- **Task Queue:** Celery / ARQ (Redis-backed asynchronous worker queue)
- **Database:** PostgreSQL (knowledge_db) + Qdrant (vector)
- **Embedding:** text-embedding-3-small (512 dims) + FastEmbed local embedding fallback (multilingual-e5-small)
- **Sparse Generator:** FastEmbed (local SPLADE/BM25 generation)
- **Reranker:** bge-reranker-v2-m3
- **Cache & Broker:** Redis (Tách biệt logic database: DB 0 cho Caching, DB 1 cho Celery/ARQ broker)

## Requirements

### Requirement 1: Document Ingestion

**User Story:** Là admin, tôi muốn upload tài liệu để AI sử dụng.

#### Acceptance Criteria
1. THE Knowledge_Base SHALL hỗ trợ upload: PDF, DOCX, TXT, Markdown
2. WHEN document uploaded, THE Knowledge_Base SHALL đẩy tác vụ (task) vào Celery/ARQ worker queue để parse và extract text content bất đồng bộ (async), tránh nghẽn CPU của API thread.
3. THE Knowledge_Base SHALL lưu file gốc vào MinIO
4. THE Knowledge_Base SHALL track processing status: processing → ready / failed
5. THE Knowledge_Base SHALL xử lý embedding throughput >= 1000 docs/phút

### Requirement 2: Semantic Chunking

**User Story:** Là AI system, tôi cần documents được chia thành chunks có ngữ nghĩa.

#### Acceptance Criteria
1. THE Knowledge_Base SHALL chunk documents theo semantic boundaries (không cắt giữa câu)
2. Chunk size: 256-512 tokens, overlap: 10-20%
3. THE Knowledge_Base SHALL hỗ trợ chunking strategies theo doc type (FAQ → Q&A pairs, Product → sections)
4. THE Knowledge_Base SHALL lưu metadata per chunk (position, document_id, doc_type)

### Requirement 3: Embedding & Storage

**User Story:** Là hệ thống, tôi cần chunks được embed và lưu vào vector DB.

#### Acceptance Criteria
1. THE Knowledge_Base SHALL sinh song song 2 vector embeddings cho mỗi chunk (Dual-Vector Indexing): vector chính dùng OpenAI text-embedding-3-small (512 dimensions) và vector dự phòng dùng local FastEmbed multilingual-e5-small (384 dimensions) để đảm bảo tính sẵn sàng cao.
2. THE Knowledge_Base SHALL lưu cả hai embeddings (openai và local_fastembed) vào Qdrant với int8 quantization
3. THE Knowledge_Base SHALL batch embed (100 chunks/batch) cho throughput
4. THE Knowledge_Base SHALL cache embeddings trong Redis (TTL 1h)
5. Qdrant collection config: HNSW m=16, ef_construct=128
6. THE Knowledge_Base SHALL sinh sparse vectors cục bộ sử dụng FastEmbed trước khi upsert vào Qdrant.

### Requirement 4: Hybrid Search

**User Story:** Là chatbot/content AI, tôi cần tìm thông tin chính xác và nhanh.

#### Acceptance Criteria
1. THE Knowledge_Base SHALL thực hiện hybrid search: dense (vector) + sparse (BM25)
2. THE Knowledge_Base SHALL merge results bằng Reciprocal Rank Fusion (RRF)
3. THE Knowledge_Base SHALL filter results theo tenant_id
4. Vector search latency SHALL < 10ms p95
5. THE Knowledge_Base SHALL trả về top-K results (configurable, default 20)
6. THE Knowledge_Base SHALL cache kết quả tìm kiếm trên Redis và áp dụng cơ chế Cache Versioning (tăng số version khi có thay đổi tài liệu) để vô hiệu hóa cache cũ mà không gây block Redis bằng lệnh SCAN.
7. THE Knowledge_Base SHALL tự động chuyển đổi sang Local Embedding Fallback (sử dụng FastEmbed cục bộ để sinh vector 384 chiều) và thực hiện truy vấn trên trường vector `local_fastembed` của Qdrant nếu API OpenAI chính bị lỗi hoặc timeout.

### Requirement 5: Reranking

**User Story:** Là AI system, tôi cần kết quả search được sắp xếp chính xác.

#### Acceptance Criteria
1. THE Knowledge_Base SHALL rerank top-20 results bằng cross-encoder (bge-reranker-v2-m3)
2. THE Knowledge_Base SHALL trả về top-5 sau reranking
3. RAG accuracy (relevant results) SHALL > 85%
4. Reranking SHALL hoàn thành trong < 30ms
5. THE Knowledge_Base SHALL hỗ trợ tuỳ chọn bỏ qua Reranking (Bypass Rerank) cho các câu hỏi đơn giản/lặp lại khi điểm số tương đồng cosine lớn nhất của kết quả Dense Search (trên thang đo [0,1]) đạt vượt trội (> 0.92) để tiết kiệm tài nguyên CPU.
6. THE Knowledge_Base SHALL loại bỏ trùng lặp (deduplicate) các chunks kết quả theo `parent_chunk_id` trước khi truy vấn PostgreSQL để lấy nội dung Parent Chunk đầy đủ gửi cho LLM, tránh dư thừa và hao phí cửa sổ ngữ cảnh.

### Requirement 6: Document Management

**User Story:** Là admin, tôi muốn quản lý tài liệu đã upload.

#### Acceptance Criteria
1. THE Knowledge_Base SHALL hỗ trợ list, view, delete documents per tenant
2. WHEN document bị xóa, THE Knowledge_Base SHALL xóa tất cả chunks và embeddings liên quan
3. THE Knowledge_Base SHALL hỗ trợ re-index document (update content)
4. THE Knowledge_Base SHALL track document versions


### Requirement: Zero-Trust Access Control & Permission Manifest

**User Story:** Là Tenant Admin, tôi muốn xem danh sách quyền hạn mà dịch vụ `knowledge-base` hỗ trợ để thiết lập vai trò tùy chỉnh trên Dashboard và đảm bảo bảo mật Zero-Trust downstream.

#### Acceptance Criteria
1. THE KNOWLEDGE_BASE_Service SHALL cung cấp API manifest tại `GET /api/v1/permissions/manifest` trả về danh sách tài nguyên (resources) và hành động (actions) được hỗ trợ.
2. THE KNOWLEDGE_BASE_Service SHALL thực hiện kiểm tra chữ ký số HMAC-SHA256 trên HTTP Header `X-Permissions-Signature` bằng `GATEWAY_SIGNING_SECRET` để xác thực request được gửi trực tiếp từ API Gateway tin cậy.
3. THE KNOWLEDGE_BASE_Service SHALL thực hiện kiểm tra quyền in-memory O(1) dựa trên HTTP Header `X-User-Permissions` truyền từ Gateway. Định dạng quyền của dịch vụ tuân theo cấu trúc `knowledge-base:{resource}:{action}` hỗ trợ ký tự đại diện `*` (Super Admin), `knowledge-base:*` (Toàn quyền trên service), và `knowledge-base:{resource}:*` (Toàn quyền trên tài nguyên).

## Security & Access Control
- **Authentication & Authorization:** APIs của Knowledge Base Service **PHẢI** được bảo vệ ở tầng Gateway (Kong) thông qua xác thực OIDC JWT.
- **Client Scope Required:** Mọi request hợp lệ chuyển tiếp đến service này **PHẢI** mang OAuth2 client scope là `knowledge-base`. Nếu thiếu scope, Gateway sẽ chặn và trả về `403 Forbidden` trước khi chuyển tiếp đến Knowledge Base Service.
- **Tenant Isolation:** Dữ liệu Knowledge Base **PHẢI** được phân tách và truy vấn dựa trên giá trị header `X-Tenant-ID` do Gateway inject.

### Requirement 7: Custom MCP Server Integration

**User Story:** Là một nhà phát triển hệ thống, tôi muốn Knowledge Base Service cung cấp giao diện Model Context Protocol (MCP) Server để AI Core có thể thực hiện tìm kiếm tri thức ngữ nghĩa một cách động và bảo mật qua SSE.

#### Acceptance Criteria
1. THE Knowledge_Base SHALL expose a custom MCP Server module over SSE (Server-Sent Events) transport mounted at `/api/v1/kb/mcp`.
2. THE Knowledge_Base SHALL declare the `knowledge_base_search(query: str, top_k: int)` tool schema.
3. THE Knowledge_Base SHALL validate the JWT bearer token in incoming SSE requests.
4. THE Knowledge_Base SHALL extract `tenant_id` from the HTTP header `X-Tenant-ID` (or custom JWT claim) and strictly restrict search queries to that tenant's document chunks.
5. THE Knowledge_Base SHALL return standard JSON-RPC 2.0 responses formatted as MCP tool response text.

