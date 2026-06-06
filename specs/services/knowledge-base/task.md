# Task Checklist — KNOWLEDGE-BASE Service

## Overview
This document tracks the implementation checklist for **KNOWLEDGE-BASE Service** based on the system specifications.

### Technical Stack & Configuration
- **Language:** Python 3.12
- **Framework:** FastAPI
- **Task Queue:** Celery / ARQ (Redis broker)
- **Database:** PostgreSQL + Qdrant
- **Embedding:** text-embedding-3-small
- **Sparse Gen:** FastEmbed (local BM25/SPLADE)
- **Reranker:** bge-reranker-v2-m3

### Reference Specifications
- [Requirements](file:///specs/solavie-system/services/knowledge-base/requirements.md)
- [Design](file:///specs/solavie-system/services/knowledge-base/design.md)
- [Logging](file:///specs/solavie-system/services/knowledge-base/logging.md)
- [Business Logic](file:///specs/solavie-system/services/knowledge-base/business-logic.md)

---

## Tasks Checklist

### Task 1: 1: Document Ingestion
> *User Story: Là admin, tôi muốn upload tài liệu để AI sử dụng.*

**Acceptance Criteria Implementation:**
- [ ] AC 1.1: THE Knowledge_Base SHALL hỗ trợ upload: PDF, DOCX, TXT, Markdown
- [ ] AC 1.2: WHEN document uploaded, THE Knowledge_Base SHALL đẩy tác vụ (task) vào Celery/ARQ worker queue để parse và extract text content bất đồng bộ (async), tránh nghẽn CPU của API thread.
- [ ] AC 1.3: THE Knowledge_Base SHALL lưu file gốc vào MinIO
- [ ] AC 1.4: THE Knowledge_Base SHALL track processing status: processing → ready / failed
- [ ] AC 1.5: THE Knowledge_Base SHALL xử lý embedding throughput >= 1000 docs/phút

### Task 2: 2: Semantic Chunking
> *User Story: Là AI system, tôi cần documents được chia thành chunks có ngữ nghĩa.*

**Acceptance Criteria Implementation:**
- [ ] AC 2.1: THE Knowledge_Base SHALL chunk documents theo semantic boundaries (không cắt giữa câu)
- [ ] AC 2.2: Chunk size: 256-512 tokens, overlap: 10-20%
- [ ] AC 2.3: THE Knowledge_Base SHALL hỗ trợ chunking strategies theo doc type (FAQ → Q&A pairs, Product → sections)
- [ ] AC 2.4: THE Knowledge_Base SHALL lưu metadata per chunk (position, document_id, doc_type)

### Task 3: 3: Embedding & Storage
> *User Story: Là hệ thống, tôi cần chunks được embed và lưu vào vector DB.*

**Acceptance Criteria Implementation:**
- [ ] AC 3.1: THE Knowledge_Base SHALL embed chunks dùng text-embedding-3-small (512 dimensions)
- [ ] AC 3.2: THE Knowledge_Base SHALL lưu embeddings vào Qdrant với int8 quantization
- [ ] AC 3.3: THE Knowledge_Base SHALL batch embed (100 chunks/batch) cho throughput
- [ ] AC 3.4: THE Knowledge_Base SHALL cache embeddings trong Redis (TTL 1h)
- [ ] AC 3.5: Qdrant collection config: HNSW m=16, ef_construct=128
- [ ] AC 3.6: THE Knowledge_Base SHALL sinh sparse vectors cục bộ sử dụng FastEmbed trước khi upsert vào Qdrant.

### Task 4: 4: Hybrid Search
> *User Story: Là chatbot/content AI, tôi cần tìm thông tin chính xác và nhanh.*

**Acceptance Criteria Implementation:**
- [ ] AC 4.1: THE Knowledge_Base SHALL thực hiện hybrid search: dense (vector) + sparse (BM25)
- [ ] AC 4.2: THE Knowledge_Base SHALL merge results bằng Reciprocal Rank Fusion (RRF)
- [ ] AC 4.3: THE Knowledge_Base SHALL filter results theo tenant_id
- [ ] AC 4.4: Vector search latency SHALL < 10ms p95
- [ ] AC 4.5: THE Knowledge_Base SHALL trả về top-K results (configurable, default 20)
- [ ] AC 4.6: THE Knowledge_Base SHALL cache kết quả tìm kiếm trên Redis và áp dụng cơ chế Cache Versioning (tăng số version khi có thay đổi tài liệu) để vô hiệu hóa cache cũ mà không gây block Redis bằng lệnh SCAN.
- [ ] AC 4.7: THE Knowledge_Base SHALL tự động chuyển sang Local Embedding Fallback (sử dụng FastEmbed) nếu OpenAI embedding API gặp sự cố.

### Task 5: 5: Reranking
> *User Story: Là AI system, tôi cần kết quả search được sắp xếp chính xác.*

**Acceptance Criteria Implementation:**
- [ ] AC 5.1: THE Knowledge_Base SHALL rerank top-20 results bằng cross-encoder (bge-reranker-v2-m3)
- [ ] AC 5.2: THE Knowledge_Base SHALL trả về top-5 sau reranking
- [ ] AC 5.3: RAG accuracy (relevant results) SHALL > 85%
- [ ] AC 5.4: Reranking SHALL hoàn thành trong < 30ms
- [ ] AC 5.5: THE Knowledge_Base SHALL hỗ trợ tuỳ chọn bỏ qua Reranking (Bypass Rerank) cho các câu hỏi đơn giản/lặp lại có độ tương đồng thô ban đầu vượt trội (> 0.92) để tiết kiệm tài nguyên CPU.

### Task 6: 6: Document Management
> *User Story: Là admin, tôi muốn quản lý tài liệu đã upload.*

**Acceptance Criteria Implementation:**
- [ ] AC 6.1: THE Knowledge_Base SHALL hỗ trợ list, view, delete documents per tenant
- [ ] AC 6.2: WHEN document bị xóa, THE Knowledge_Base SHALL xóa tất cả chunks và embeddings liên quan
- [ ] AC 6.3: THE Knowledge_Base SHALL hỗ trợ re-index document (update content)
- [ ] AC 6.4: THE Knowledge_Base SHALL track document versions

### Task 7: Implement Business Logic Rules
**Business Validations:**
- [ ] Tổng quan vai trò: Nhận tài liệu upload → parse → chunk → embed → lưu Qdrant
- [ ] Tổng quan vai trò: Phục vụ search queries từ Chatbot và Content Service
- [ ] Tổng quan vai trò: Đảm bảo accuracy > 85% và latency < 10ms cho vector search
- [ ] Luồng Ingestion (Celery/ARQ Worker): Đăng ký tasks cho worker xử lý bất đồng bộ
- [ ] Luồng Ingestion (FastEmbed): Sinh sparse vectors cục bộ bằng FastEmbed BM25/SPLADE
- [ ] Luồng Ingestion (Parent-Child Index): Lưu trữ child chunks trong Qdrant và parent chunks trong PostgreSQL, ánh xạ ID tương ứng.
- [ ] Luồng 1: Document Ingestion: faq: Mỗi cặp Q&A = 1 chunk (detect pattern "Q:" / "A:")
- [ ] Luồng 1: Document Ingestion: product: Chunk theo sections (headers)
- [ ] Luồng 1: Document Ingestion: general: Semantic chunking (cosine similarity breakpoints)
- [ ] Luồng 1: Document Ingestion: Split text thành sentences
- [ ] Luồng 1: Document Ingestion: Embed mỗi sentence
- [ ] Luồng 1: Document Ingestion: Tính cosine similarity giữa sentence[i] và sentence[i+1]
- [ ] Luồng 1: Document Ingestion: Khi similarity < threshold → đó là boundary
- [ ] Luồng 1: Document Ingestion: Group sentences thành chunks (respect max size)
- [ ] Luồng 1: Document Ingestion: Add overlap (giữ 2 sentences cuối chunk trước)
- [ ] Luồng 2: Hybrid Search: Doc A: rank 1 in dense, rank 3 in sparse
- [ ] Luồng 2: Hybrid Search: Doc B: rank 5 in dense, rank 1 in sparse
- [ ] Luồng 2: Hybrid Search: Doc A wins (higher combined score)
- [ ] Luồng 2: Hybrid Search: Bi-encoder (embedding) nhanh nhưng approximate
- [ ] Luồng 2: Hybrid Search: Cross-encoder chính xác hơn nhưng chậm (O(n) per query)
- [ ] Luồng 2: Hybrid Search: Trick: dùng bi-encoder lấy top-20, rồi cross-encoder rerank top-20
- [ ] Luồng 2: Hybrid Search (Parent-Child Retriever): So khớp trên child chunks nhưng trả về nội dung của parent chunk tương ứng.
- [ ] Luồng 3: Document Deletion: Verify tenant owns document
- [ ] Luồng 3: Document Deletion: Get all chunk IDs for this document
- [ ] Luồng 3: Document Deletion: Delete vectors from Qdrant (by chunk IDs)
- [ ] Luồng 3: Document Deletion: Delete chunks from PostgreSQL (CASCADE)
- [ ] Luồng 3: Document Deletion: Delete file from MinIO
- [ ] Luồng 3: Document Deletion: Delete document record
- [ ] Luồng 3: Document Deletion: Return 204 No Content
- [ ] Search Result Caching (Tối ưu - Cache Versioning): Query embedding cache (TTL 1h)
- [ ] Search Result Caching (Tối ưu - Cache Versioning): Search results cache (TTL 30min) kết hợp versioning key `{tenant_id}:kb_version`
- [ ] Search Result Caching (Tối ưu - Cache Versioning): Invalidate cache bằng cách tăng số phiên bản (INCR `{tenant_id}:kb_version`) khi tài liệu thay đổi.
- [ ] Qdrant Collection Management: Option A: 1 collection per tenant (simple, good isolation)
- [ ] Qdrant Collection Management: Option B: 1 shared collection + metadata filter (efficient)
- [ ] Qdrant Collection Management: Ít collections = ít overhead
- [ ] Qdrant Collection Management: Filter by tenant_id trong metadata
- [ ] Qdrant Collection Management: Qdrant handles filtering efficiently

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

### Task: Security Integration & Dynamic RBAC (MỚI)
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `knowledge-base`.
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`.
- [ ] Triển khai HMAC Signature Verification Guard/Interceptor sử dụng `GATEWAY_SIGNING_SECRET` để xác thực request từ Gateway.
- [ ] Triển khai cơ chế so khớp quyền hạn Dynamic RBAC in-memory O(1) hỗ trợ wildcard (`*`, `knowledge-base:*`, `knowledge-base:{resource}:*`).
- [ ] Thực hiện tích hợp Endpoint `/api/v1/permissions/manifest` trả về danh sách tài nguyên và quyền hạn của service.
- [ ] Bổ sung các test cases kiểm tra Signature Verification và Access Control Denied.

### Task 8: Custom MCP Server Integration (MỚI)
- [ ] Thiết lập SSE transport endpoints `/api/v1/kb/mcp` và `/api/v1/kb/mcp/messages` bằng `mcp` Python SDK (hoặc FastAPI MCP wrapper).
- [ ] Đăng ký tool schema `knowledge_base_search(query: str, top_k: int)`.
- [ ] Triển khai middleware xác thực JWT và so khớp chéo `tenant_id` từ arguments của tool call với JWT payload/header.
- [ ] Thực thi ghi nhận Prometheus metrics: `kb_mcp_tool_executions_total` và `kb_mcp_security_violations_total`.
- [ ] Viết unit tests kiểm chứng bảo mật chéo tenant và chặn truy cập trái phép.
