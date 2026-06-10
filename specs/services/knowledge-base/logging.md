# Logging & Observability — Knowledge Base Service

## Log Format: Structured JSON
```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "info",
  "service": "knowledge-base",
  "trace_id": "abc123",
  "tenant_id": "tenant-uuid",
  "message": "Hybrid search completed",
  "context": {
    "query_length": 45,
    "dense_results": 20,
    "sparse_results": 15,
    "reranked_top_k": 5,
    "top_score": 0.89,
    "latency_ms": 8,
    "cache_hit": false
  }
}
```

## Log Levels
| Level | Khi nào | Ví dụ |
|-------|---------|-------|
| ERROR | Security shared secret configuration missing | `"GATEWAY_SIGNING_SECRET is not configured"` |
| ERROR | Qdrant unreachable, embedding API fail, document parse fail | `"Qdrant connection refused"` |
| WARN | Signature validation failure, permission denied, unauthorized access attempt | `"HMAC signature verification failed: signature mismatch"` |
| WARN | Low search scores, embedding batch partial fail, slow query | `"Search: all scores < 0.5, likely irrelevant"` |
| INFO | Document uploaded, search completed, embedding batch done | `"Document indexed: 45 chunks, 12s"` |
| DEBUG | Chunk content, embedding vectors (truncated), rerank scores | `"Rerank scores: [0.89, 0.76, 0.71, 0.65, 0.52]"` |

## Trace Spans
```
[Search Query]
├── [embed_query] — 100ms (or 1ms if cache hit)
├── [dense_search_qdrant] — 5ms
├── [sparse_search_qdrant] — 5ms
├── [rrf_merge] — 1ms
└── [rerank] — 20ms

[Document Ingestion]
├── [upload_to_minio] — 50ms
├── [parse_document] — 200-2000ms (depends on size)
├── [semantic_chunking] — 100ms
├── [batch_embed] — 500ms (per 100 chunks)
└── [store_qdrant] — 50ms
```

## Prometheus Metrics
```python
# Search metrics
kb_search_total: Counter ['tenant_id', 'search_type'] # hybrid/dense/sparse
kb_search_duration: Histogram [] # target < 10ms p95
kb_search_results_count: Histogram [] # how many results returned
kb_search_top_score: Histogram [buckets: 0.0-1.0]
kb_embedding_cache_hits: Counter []
kb_embedding_cache_misses: Counter []

# Ingestion metrics
kb_documents_ingested_total: Counter ['file_type', 'status'] # success/failed
kb_chunks_created_total: Counter []
kb_embedding_batch_duration: Histogram []
kb_ingestion_throughput: Gauge [] # docs/min

# Qdrant health
kb_qdrant_points_total: Gauge ['tenant_id'] # total vectors stored
kb_qdrant_search_latency: Histogram [] # raw qdrant latency
kb_qdrant_collection_size_bytes: Gauge []

# MCP metrics
kb_mcp_tool_executions_total: Counter ['tenant_id', 'status']
kb_mcp_security_violations_total: Counter ['tenant_id']
```


// Zero-Trust Security Metrics
knowledge_base_security_signature_failures_total: Counter [tenant_id, client_ip]
knowledge_base_security_permission_denied_total: Counter [tenant_id, required_permission]

## Health Endpoints
```
GET /health   → {"status": "ok"}
GET /ready    → {"status": "ready", "qdrant": "connected", "minio": "connected", "postgres": "connected"}
GET /metrics  → Prometheus format
```

## Alert Rules
| Alert | Condition | Severity |
|-------|-----------|----------|
| HighSignatureFailures | sum(rate(knowledge_base_security_signature_failures_total[5m])) > 5 | critical (potential spoofing attempt or key mismatch) |
| HighPermissionDenied | sum(rate(knowledge_base_security_permission_denied_total[5m])) > 10 | warning (user accessing forbidden resources) |
| QdrantDown | qdrant health check fail > 30s | critical |
| SearchSlow | search_duration p95 > 50ms | warning |
| LowSearchQuality | top_score < 0.5 for > 30% queries in 15m | warning |
| IngestionFailing | documents_ingested{status=failed} > 3 in 10m | warning |
| EmbeddingAPIDown | embedding batch errors > 0 for 5m | critical |
| KBMCPSecurityBreach | kb_mcp_security_violations_total > 0 | critical |

---

## Service Discovery Audit Logs

Khi `ServiceRegistryClient` thực hiện đăng ký hoặc hủy đăng ký trên Redis, nó phải ghi nhận log có cấu trúc JSON như sau:

### 1. Log Đăng ký Thành công (register)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "knowledge-base",
  "message": "Service node registration completed",
  "action": "register",
  "node_ip": "172.20.0.10",
  "node_port": 8004,
  "status": "success",
  "context": {
    "redis_key": "registry:service:knowledge-base"
  }
}
```

### 2. Log Hủy Đăng ký Thành công (deregister)
```json
{
  "timestamp": "2026-06-10T00:00:00.000Z",
  "level": "info",
  "service": "knowledge-base",
  "message": "Service node deregistration completed",
  "action": "deregister",
  "node_ip": "172.20.0.10",
  "node_port": 8004,
  "status": "success",
  "context": {
    "redis_key": "registry:service:knowledge-base"
  }
}
```
