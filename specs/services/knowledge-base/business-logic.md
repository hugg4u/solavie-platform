# Business Logic — Knowledge Base Service

## Tổng quan vai trò

Knowledge Base là **kho tri thức** của hệ thống. Nó:
1. Nhận tài liệu upload → parse → chunk → embed → lưu Qdrant
2. Phục vụ search queries từ Chatbot và Content Service
3. Đảm bảo accuracy > 85% và latency < 10ms cho vector search

## Luồng xử lý chi tiết

### Luồng 1: Document Ingestion

```
User upload file (PDF/DOCX/TXT/MD)
│
▼
┌─────────────────────────────────┐
│ 1. VALIDATE FILE                │
│    - File type supported?       │
│    - Size within limit?         │
│    - Tenant quota not exceeded? │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 2. UPLOAD TO MINIO              │
│    - Path: {tenant_id}/{doc_id} │
│    - Store original file        │
│    - Save metadata to PostgreSQL│
│    - Status = 'processing'      │
└────────────┬────────────────────┘
             │
             ▼ (async background job)
┌─────────────────────────────────┐
│ 3. PARSE DOCUMENT               │
│    - PDF → PyPDF2/unstructured  │
│    - DOCX → python-docx        │
│    - TXT/MD → direct read      │
│    - Extract: text + metadata   │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 4. SEMANTIC CHUNKING            │
│    - Split into sentences       │
│    - Embed consecutive sentences│
│    - Detect semantic boundaries │
│      (cosine sim < 0.75)       │
│    - Chunk size: 256-512 tokens │
│    - Overlap: 20%              │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 5. BATCH EMBEDDING              │
│    - Batch 100 chunks at a time │
│    - Call AI Core embed API     │
│    - Model: text-embedding-3-small│
│    - Dimensions: 512            │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 6. STORE IN QDRANT              │
│    - Upsert vectors + metadata  │
│    - Collection: kb_{tenant_id} │
│    - Payload: chunk_id, doc_id, │
│      content, position          │
│    - Also store sparse vector   │
│      (BM25/SPLADE) for hybrid  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 7. UPDATE STATUS                │
│    - Document status = 'ready'  │
│    - chunk_count = N            │
│    - If any step fails →        │
│      status = 'failed' + error  │
└─────────────────────────────────┘
```

**Chi tiết Semantic Chunking:**

```python
class SemanticChunker:
    CHUNK_SIZE = 400       # tokens
    CHUNK_OVERLAP = 80     # tokens (20%)
    SIMILARITY_THRESHOLD = 0.75

    async def chunk(self, text: str, doc_type: str) -> list[Chunk]:
        """
        Chọn strategy theo doc_type:
        - faq: Mỗi cặp Q&A = 1 chunk (detect pattern "Q:" / "A:")
        - product: Chunk theo sections (headers)
        - general: Semantic chunking (cosine similarity breakpoints)
        """
        if doc_type == "faq":
            return self._chunk_faq(text)
        elif doc_type == "product":
            return self._chunk_by_sections(text)
        else:
            return await self._semantic_chunk(text)

    async def _semantic_chunk(self, text: str) -> list[Chunk]:
        """
        Algorithm:
        1. Split text thành sentences
        2. Embed mỗi sentence
        3. Tính cosine similarity giữa sentence[i] và sentence[i+1]
        4. Khi similarity < threshold → đó là boundary
        5. Group sentences thành chunks (respect max size)
        6. Add overlap (giữ 2 sentences cuối chunk trước)
        """
        sentences = self._split_sentences(text)
        if len(sentences) <= 3:
            return [Chunk(content=text, token_count=count_tokens(text))]

        # Batch embed all sentences
        embeddings = await self.embed_batch(sentences)

        chunks = []
        current_chunk = []
        current_tokens = 0

        for i in range(len(sentences)):
            current_chunk.append(sentences[i])
            current_tokens += count_tokens(sentences[i])

            # Check boundary conditions
            is_boundary = False
            if i < len(sentences) - 1:
                sim = cosine_similarity(embeddings[i], embeddings[i + 1])
                if sim < self.SIMILARITY_THRESHOLD:
                    is_boundary = True

            if is_boundary or current_tokens >= self.CHUNK_SIZE:
                chunks.append(Chunk(
                    content=" ".join(current_chunk),
                    token_count=current_tokens,
                    metadata={"start_sentence": i - len(current_chunk) + 1, "end_sentence": i}
                ))
                # Overlap: keep last 2 sentences
                current_chunk = current_chunk[-2:] if len(current_chunk) > 2 else []
                current_tokens = sum(count_tokens(s) for s in current_chunk)

        # Don't forget last chunk
        if current_chunk:
            chunks.append(Chunk(
                content=" ".join(current_chunk),
                token_count=current_tokens,
            ))

        return chunks
```

### Luồng 2: Hybrid Search

```
Search query đến (từ Chatbot hoặc Content)
│
▼
┌─────────────────────────────────┐
│ 1. EMBED QUERY                  │
│    - Check Redis cache first    │
│    - If miss → call AI Core     │
│    - Cache result (TTL 1h)      │
│    ~1ms (cache) / ~100ms (miss) │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────┐
│ 2. PARALLEL SEARCH                          │
│                                             │
│  ┌─────────────────┐  ┌─────────────────┐  │
│  │ Dense Search    │  │ Sparse Search   │  │
│  │ (Vector/Cosine) │  │ (BM25)          │  │
│  │ top-20          │  │ top-20          │  │
│  │ ~5ms            │  │ ~5ms            │  │
│  └────────┬────────┘  └────────┬────────┘  │
│           │                     │           │
└───────────┼─────────────────────┼───────────┘
            │                     │
            ▼                     ▼
┌─────────────────────────────────┐
│ 3. RECIPROCAL RANK FUSION (RRF) │
│    - Merge dense + sparse       │
│    - Score = Σ 1/(k + rank)     │
│    - k = 60 (standard)          │
│    - Deduplicate by chunk_id    │
│    ~1ms                          │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 4. RERANK (Cross-Encoder)       │
│    - Take top-20 from RRF       │
│    - Score each (query, doc)    │
│    - Model: bge-reranker-v2-m3  │
│    - Return top-5               │
│    ~20ms                         │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 5. RETURN RESULTS               │
│    - Top-5 with scores          │
│    - Include: content, doc_id,  │
│      chunk_id, score            │
└─────────────────────────────────┘
```

**Chi tiết RRF:**

```python
def reciprocal_rank_fusion(
    dense_results: list[SearchResult],
    sparse_results: list[SearchResult],
    k: int = 60
) -> list[SearchResult]:
    """
    RRF merges 2 ranked lists into 1.
    
    Formula: score(doc) = Σ 1 / (k + rank_in_list)
    
    Ví dụ:
    - Doc A: rank 1 in dense, rank 3 in sparse
      → score = 1/(60+1) + 1/(60+3) = 0.0164 + 0.0159 = 0.0323
    - Doc B: rank 5 in dense, rank 1 in sparse
      → score = 1/(60+5) + 1/(60+1) = 0.0154 + 0.0164 = 0.0318
    - Doc A wins (higher combined score)
    
    Tại sao k=60: Research shows k=60 balances well between
    giving too much weight to top results vs too little.
    """
    scores = {}
    
    for rank, result in enumerate(dense_results):
        doc_id = result.chunk_id
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
        # Store the actual result for later
        if doc_id not in result_map:
            result_map[doc_id] = result
    
    for rank, result in enumerate(sparse_results):
        doc_id = result.chunk_id
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
        if doc_id not in result_map:
            result_map[doc_id] = result
    
    # Sort by combined score
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    
    return [result_map[doc_id] for doc_id in sorted_ids]
```

**Chi tiết Reranking:**

```python
class Reranker:
    def __init__(self):
        # Load cross-encoder model (local, no API call)
        self.model = CrossEncoder("BAAI/bge-reranker-v2-m3")
    
    async def rerank(
        self, query: str, documents: list[str], top_k: int = 5
    ) -> list[RerankResult]:
        """
        Cross-encoder scores (query, document) pairs.
        
        Tại sao cần rerank:
        - Bi-encoder (embedding) nhanh nhưng approximate
        - Cross-encoder chính xác hơn nhưng chậm (O(n) per query)
        - Trick: dùng bi-encoder lấy top-20, rồi cross-encoder rerank top-20
        
        Performance: 20 documents × ~1ms each = ~20ms total
        """
        pairs = [(query, doc) for doc in documents]
        scores = self.model.predict(pairs)
        
        # Sort by score, return top-k
        ranked = sorted(
            zip(scores, documents, range(len(documents))),
            key=lambda x: x[0],
            reverse=True
        )
        
        return [
            RerankResult(content=doc, score=score, original_rank=idx)
            for score, doc, idx in ranked[:top_k]
        ]
```

### Luồng 3: Document Deletion

```
DELETE /api/v1/documents/:id
│
▼
1. Verify tenant owns document
2. Get all chunk IDs for this document
3. Delete vectors from Qdrant (by chunk IDs)
4. Delete chunks from PostgreSQL (CASCADE)
5. Delete file from MinIO
6. Delete document record
7. Return 204 No Content
```

---

## Search Result Caching (Tối ưu)

Ngoài việc cache query embedding (TTL 1h), cache luôn **search results** để tránh search lặp lại cho câu hỏi phổ biến.

```python
async def search_with_cache(query: str, tenant_id: str, top_k: int = 5):
    """
    2-layer cache:
    1. Query embedding cache (TTL 1h)
    2. Search results cache (TTL 30min) — MỚI

    Tại sao: nhiều khách hỏi cùng câu ("giá bao nhiêu?", "ship không?").
    Cache results giảm 50-70% lượng search thực tế.
    """
    cache_key = f"{tenant_id}:kb_search:{hashlib.md5(f'{query}:{top_k}'.encode()).hexdigest()}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)  # Cache hit: ~1ms thay vì ~30ms

    results = await hybrid_search(query, tenant_id, top_k)

    # Cache 30min. Invalidate khi document của tenant thay đổi.
    await redis.setex(cache_key, 1800, json.dumps(results))
    return results
```

**Cache invalidation:** Khi document upload/delete/reindex → xóa toàn bộ key `{tenant_id}:kb_search:*` của tenant đó (dùng Redis SCAN + DEL, hoặc cache version bump).

## Qdrant Collection Management

```python
class QdrantManager:
    async def ensure_collection(self, tenant_id: str):
        """
        Mỗi tenant có thể dùng:
        - Option A: 1 collection per tenant (simple, good isolation)
        - Option B: 1 shared collection + metadata filter (efficient)
        
        Chọn Option B cho hệ thống này:
        - Ít collections = ít overhead
        - Filter by tenant_id trong metadata
        - Qdrant handles filtering efficiently
        """
        collection_name = "knowledge_base"  # Shared
        
        if not await self.client.collection_exists(collection_name):
            await self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=512,
                    distance=Distance.COSINE,
                    on_disk=False,
                ),
                sparse_vectors_config={"bm25": SparseVectorParams()},
                hnsw_config=HnswConfigDiff(m=16, ef_construct=128),
                quantization_config=ScalarQuantization(
                    scalar=ScalarQuantizationConfig(
                        type=ScalarType.INT8,
                        quantile=0.99,
                        always_ram=True,
                    )
                ),
            )

    async def search(self, tenant_id: str, query_vector: list, top_k: int = 20):
        """Search with tenant isolation via filter."""
        return await self.client.search(
            collection_name="knowledge_base",
            query_vector=query_vector,
            query_filter=Filter(
                must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
            ),
            limit=top_k,
        )
```

---

## Error Handling

| Scenario | Xử lý |
|----------|--------|
| File parse fail (corrupted PDF) | Status='failed', error message, notify user |
| Embedding API fail mid-batch | Retry failed chunks, partial success OK |
| Qdrant unreachable | Retry 3x, if fail → status='failed', alert |
| Search: Qdrant timeout | Return empty results, log error |
| Search: no results found | Return empty list (caller decides handoff) |
| Document too large (> 50MB) | Reject at upload, return 413 |
| Tenant quota exceeded | Reject, return 429 with quota info |
