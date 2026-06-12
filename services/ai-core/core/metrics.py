"""
AI-CORE Custom Prometheus Metrics (Task 12 — Guardrails Metrics)

Định nghĩa toàn bộ custom metrics theo yêu cầu spec:
  - ai_core_pii_tokens_total        : Tổng số PII tokens được mask
  - ai_core_nli_grounding_score     : Histogram điểm số NLI grounding
  - ai_core_nli_violations_total    : Counter vi phạm NLI threshold
  - ai_core_rag_similarity_score    : Histogram similarity score RAG
  - ai_core_rate_limit_violations_total : Counter vi phạm rate limit per tool
  - ai_core_guardrail_blocked_total : Counter requests bị block bởi guardrail
  - ai_core_pii_latency_seconds     : Histogram thời gian xử lý PII (target < 10ms)
  - ai_core_agent_iterations        : Histogram số vòng lặp agent per request
"""

from prometheus_client import Counter, Histogram, Gauge, REGISTRY

# ── PII Masking Metrics ──────────────────────────────────────────────────────
ai_core_pii_tokens_total = Counter(
    "ai_core_pii_tokens_total",
    "Total number of PII tokens masked in input/output",
    ["tenant_id", "pii_type"]  # pii_type: email | phone | card
)

ai_core_pii_latency_seconds = Histogram(
    "ai_core_pii_latency_seconds",
    "Latency of PII masking/restoration operation (target < 10ms = 0.01s)",
    ["operation"],  # operation: mask | restore
    buckets=[0.001, 0.005, 0.010, 0.025, 0.050, 0.100]
)

# ── NLI Grounding Validator Metrics ──────────────────────────────────────────
ai_core_nli_grounding_score = Histogram(
    "ai_core_nli_grounding_score",
    "NLI grounding score distribution for AI responses (0.0 – 1.0)",
    ["tenant_id", "use_case"],
    buckets=[0.0, 0.2, 0.4, 0.6, 0.7, 0.8, 0.9, 1.0]
)

ai_core_nli_violations_total = Counter(
    "ai_core_nli_violations_total",
    "Total number of NLI grounding score violations (score < threshold)",
    ["tenant_id", "use_case"]
)

# ── RAG Similarity Metrics ────────────────────────────────────────────────────
ai_core_rag_similarity_score = Histogram(
    "ai_core_rag_similarity_score",
    "RAG context similarity score distribution",
    ["tenant_id", "use_case"],
    buckets=[0.0, 0.3, 0.5, 0.7, 0.8, 0.9, 1.0]
)

# ── Rate Limit Metrics ────────────────────────────────────────────────────────
ai_core_rate_limit_violations_total = Counter(
    "ai_core_rate_limit_violations_total",
    "Total number of tool call rate limit violations",
    ["tenant_id", "tool_name", "tier"]
)

# ── Guardrail Block Metrics ───────────────────────────────────────────────────
ai_core_guardrail_blocked_total = Counter(
    "ai_core_guardrail_blocked_total",
    "Total number of requests blocked by content guardrails",
    ["tenant_id", "block_reason"]  # block_reason: profanity | prompt_leakage | topic | pii
)

# ── Agent Loop Metrics ────────────────────────────────────────────────────────
ai_core_agent_iterations = Histogram(
    "ai_core_agent_iterations",
    "Number of ReAct agent loop iterations per request",
    ["tenant_id", "use_case"],
    buckets=[1, 2, 3, 4, 5]
)

# ── Token Budget Metrics ──────────────────────────────────────────────────────
ai_core_token_budget_exceeded_total = Counter(
    "ai_core_token_budget_exceeded_total",
    "Total number of session token budget exceeded events",
    ["tenant_id"]
)

# ── LLM Gateway Metrics (augmented) ──────────────────────────────────────────
ai_core_llm_calls_total = Counter(
    "ai_core_llm_calls_total",
    "Total number of LLM API calls",
    ["tenant_id", "use_case", "provider", "model", "is_fallback"]
)

ai_core_llm_cost_usd_total = Counter(
    "ai_core_llm_cost_usd_total",
    "Total accumulated LLM cost in USD",
    ["tenant_id", "use_case", "provider"]
)

ai_core_llm_latency_seconds = Histogram(
    "ai_core_llm_latency_seconds",
    "LLM API call latency in seconds",
    ["tenant_id", "use_case", "provider"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

# ── Cost Alert Metrics ────────────────────────────────────────────────────────
ai_core_cost_alerts_total = Counter(
    "ai_core_cost_alerts_total",
    "Total number of cost alert threshold exceeded events (>= 80% cost limit)",
    ["tenant_id", "tier"]
)

# ── Model Deprecation Fallback Metrics ────────────────────────────────────────
ai_core_model_deprecation_fallbacks_total = Counter(
    "ai_core_model_deprecation_fallbacks_total",
    "Total number of fallback events triggered by deprecated models",
    ["tenant_id", "provider", "deprecated_model", "fallback_model"]
)

# ── Semantic Cache Metrics ────────────────────────────────────────────────────
ai_core_semantic_cache_hits_total = Counter(
    "ai_core_semantic_cache_hits_total",
    "Total number of semantic cache hits",
    []  # No labels required by spec, or we can make it simple
)

ai_core_semantic_cache_misses_total = Counter(
    "ai_core_semantic_cache_misses_total",
    "Total number of semantic cache misses",
    []
)

# ── Event Publisher Metrics ───────────────────────────────────────────────────
ai_core_publisher_failures_total = Counter(
    "ai_core_publisher_failures_total",
    "Total number of Kafka message publishing failures after retries",
    ["tenant_id", "topic"]
)


