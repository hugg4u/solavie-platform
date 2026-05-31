# Requirements — Knowledge Base Service

## Overview
Dịch vụ RAG pipeline — upload tài liệu, semantic chunking, embedding, hybrid search (vector + BM25), reranking. Foundation cho Chatbot và Content AI.

## Tech Stack
- **Language:** Python 3.12
- **Framework:** FastAPI
- **Database:** PostgreSQL (knowledge_db) + Qdrant (vector)
- **Embedding:** text-embedding-3-small (512 dims)
- **Reranker:** bge-reranker-v2-m3

## Requirements

### Requirement 1: Document Ingestion

**User Story:** Là admin, tôi muốn upload tài liệu để AI sử dụng.

#### Acceptance Criteria
1. THE Knowledge_Base SHALL hỗ trợ upload: PDF, DOCX, TXT, Markdown
2. WHEN document uploaded, THE Knowledge_Base SHALL parse và extract text content
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
1. THE Knowledge_Base SHALL embed chunks dùng text-embedding-3-small (512 dimensions)
2. THE Knowledge_Base SHALL lưu embeddings vào Qdrant với int8 quantization
3. THE Knowledge_Base SHALL batch embed (100 chunks/batch) cho throughput
4. THE Knowledge_Base SHALL cache embeddings trong Redis (TTL 1h)
5. Qdrant collection config: HNSW m=16, ef_construct=128

### Requirement 4: Hybrid Search

**User Story:** Là chatbot/content AI, tôi cần tìm thông tin chính xác và nhanh.

#### Acceptance Criteria
1. THE Knowledge_Base SHALL thực hiện hybrid search: dense (vector) + sparse (BM25)
2. THE Knowledge_Base SHALL merge results bằng Reciprocal Rank Fusion (RRF)
3. THE Knowledge_Base SHALL filter results theo tenant_id
4. Vector search latency SHALL < 10ms p95
5. THE Knowledge_Base SHALL trả về top-K results (configurable, default 20)

### Requirement 5: Reranking

**User Story:** Là AI system, tôi cần kết quả search được sắp xếp chính xác.

#### Acceptance Criteria
1. THE Knowledge_Base SHALL rerank top-20 results bằng cross-encoder (bge-reranker-v2-m3)
2. THE Knowledge_Base SHALL trả về top-5 sau reranking
3. RAG accuracy (relevant results) SHALL > 85%
4. Reranking SHALL hoàn thành trong < 30ms

### Requirement 6: Document Management

**User Story:** Là admin, tôi muốn quản lý tài liệu đã upload.

#### Acceptance Criteria
1. THE Knowledge_Base SHALL hỗ trợ list, view, delete documents per tenant
2. WHEN document bị xóa, THE Knowledge_Base SHALL xóa tất cả chunks và embeddings liên quan
3. THE Knowledge_Base SHALL hỗ trợ re-index document (update content)
4. THE Knowledge_Base SHALL track document versions
