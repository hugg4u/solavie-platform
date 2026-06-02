# Task Checklist — KNOWLEDGE-BASE Service

## Overview
This document tracks the implementation checklist for **KNOWLEDGE-BASE Service** based on the system specifications.

### Technical Stack & Configuration
- **Language:** Python 3.12
- **Framework:** FastAPI
- **Database:** PostgreSQL
- **Embedding:** text-embedding-3-small
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
- [ ] AC 1.2: WHEN document uploaded, THE Knowledge_Base SHALL parse và extract text content
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

### Task 4: 4: Hybrid Search
> *User Story: Là chatbot/content AI, tôi cần tìm thông tin chính xác và nhanh.*

**Acceptance Criteria Implementation:**
- [ ] AC 4.1: THE Knowledge_Base SHALL thực hiện hybrid search: dense (vector) + sparse (BM25)
- [ ] AC 4.2: THE Knowledge_Base SHALL merge results bằng Reciprocal Rank Fusion (RRF)
- [ ] AC 4.3: THE Knowledge_Base SHALL filter results theo tenant_id
- [ ] AC 4.4: Vector search latency SHALL < 10ms p95
- [ ] AC 4.5: THE Knowledge_Base SHALL trả về top-K results (configurable, default 20)

### Task 5: 5: Reranking
> *User Story: Là AI system, tôi cần kết quả search được sắp xếp chính xác.*

**Acceptance Criteria Implementation:**
- [ ] AC 5.1: THE Knowledge_Base SHALL rerank top-20 results bằng cross-encoder (bge-reranker-v2-m3)
- [ ] AC 5.2: THE Knowledge_Base SHALL trả về top-5 sau reranking
- [ ] AC 5.3: RAG accuracy (relevant results) SHALL > 85%
- [ ] AC 5.4: Reranking SHALL hoàn thành trong < 30ms

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
- [ ] Luồng 3: Document Deletion: Verify tenant owns document
- [ ] Luồng 3: Document Deletion: Get all chunk IDs for this document
- [ ] Luồng 3: Document Deletion: Delete vectors from Qdrant (by chunk IDs)
- [ ] Luồng 3: Document Deletion: Delete chunks from PostgreSQL (CASCADE)
- [ ] Luồng 3: Document Deletion: Delete file from MinIO
- [ ] Luồng 3: Document Deletion: Delete document record
- [ ] Luồng 3: Document Deletion: Return 204 No Content
- [ ] Search Result Caching (Tối ưu): Query embedding cache (TTL 1h)
- [ ] Search Result Caching (Tối ưu): Search results cache (TTL 30min) — MỚI
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

### Task: Security Integration (MỚI)
- [ ] Xác minh các API endpoint được bảo vệ bởi Kong Gateway với required client scope là `knowledge-base`
- [ ] Kiểm tra tính cô lập dữ liệu multi-tenant thông qua header `X-Tenant-ID`
