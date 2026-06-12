# Business Logic — Chatbot Service

## Tổng quan vai trò (CẬP NHẬT)

Chatbot Service giờ là **thin orchestrator** — nó quản lý conversation state và delegate AI logic cho AI Core (ReAct Agent):
1. Nhận message từ Messaging (gRPC)
2. Load conversation state (checkpoint)
3. Gọi AI Core agent (use_case="chatbot") — AI Core tự handle: intent, RAG, response, confidence
4. Nhận kết quả → return cho Messaging
5. Lưu checkpoint

**AI Core (ReAct Agent) giờ handle:**
- Intent classification (via reasoning)
- RAG retrieval (via knowledge_base_search tool)
- Response generation (via LLM)
- Confidence evaluation (built into agent loop)
- Handoff decision (via handoff_to_agent tool)
- Sentiment analysis (via analyze_sentiment tool)

**Chatbot Service vẫn giữ:**
- gRPC server interface (Messaging gọi vào)
- Conversation state management (LangGraph checkpoints)
- Timeout handling (5s max → auto handoff)
- Per-tenant chatbot config (confidence threshold, enabled languages)
- Metrics collection (intent distribution, handoff rate)

> **Lưu ý kiến trúc:** Workflow chi tiết bên dưới là logic mà **AI Core ReAct Agent** thực thi khi nhận `use_case="chatbot"`. Chatbot Service chỉ orchestrate (state + timeout + forward). Phần này document để team hiểu luồng đầy đủ. Tuân theo `shared/standards.md` cho confidence scale (handoff < 0.70) và handoff triggers.

## Tối ưu đã áp dụng (Optimizations)

### Parallel Retrieval (giảm latency)
Thay vì tuần tự `classify → embed → search`, chạy SONG SONG cả 3 ngay từ đầu:

```python
# Tối ưu: 3 tasks parallel ngay khi nhận message
intent_task = asyncio.create_task(classify_intent(msg))
embed_task = asyncio.create_task(embed_query(msg))
search_task = asyncio.create_task(retrieve_knowledge(msg))  # embed internally + search

intent, _, docs = await asyncio.gather(intent_task, embed_task, search_task)
# Tiết kiệm ~50ms (search không chờ embed xong ở bước riêng)
```

Lưu ý: nếu intent = chitchat/complaint, kết quả search bị bỏ qua (chấp nhận lãng phí 1 search call để đổi lấy latency thấp cho 80% case faq/sales/support).

## LangGraph Workflow Chi Tiết

```
Message đến (gRPC từ Messaging)
│
▼
┌─────────────────────────────────────────────┐
│ PARALLEL EXECUTION (giảm 40% latency)       │
│                                             │
│  ┌─────────────────┐  ┌─────────────────┐  │
│  │ Classify Intent │  │  Embed Query    │  │
│  │ + Detect Lang   │  │  (for RAG)      │  │
│  │ ~300ms          │  │  ~100ms         │  │
│  └────────┬────────┘  └────────┬────────┘  │
│           │                     │           │
└───────────┼─────────────────────┼───────────┘
            │                     │
            ▼                     ▼
┌─────────────────────────────────────────────┐
│ ROUTE BY INTENT                             │
│                                             │
│  intent=complaint/angry → HANDOFF ngay      │
│  intent=chitchat → Generate chitchat reply  │
│  intent=faq/sales/support → RAG pipeline    │
└────────────┬────────────────────────────────┘
             │ (faq/sales/support)
             ▼
┌─────────────────────────────────┐
│ RETRIEVE KNOWLEDGE              │
│  - Call Knowledge Base REST API │
│  - Hybrid search + rerank      │
│  - Get top-5 relevant docs     │
│  ~50ms                          │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ CHECK RETRIEVAL QUALITY         │
│  - Top doc score >= 0.5?       │
│  - If NO docs relevant →       │
│    HANDOFF (can't answer)      │
└────────────┬────────────────────┘
             │ (docs found)
             ▼
┌─────────────────────────────────┐
│ GENERATE RESPONSE               │
│  - Call AI Core gRPC            │
│  - Include: system prompt +     │
│    context docs + history       │
│  - Request confidence score     │
│  ~1200ms                        │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ EVALUATE CONFIDENCE             │
│  - confidence >= 0.7 → REPLY   │
│  - confidence < 0.7 → HANDOFF  │
│  - "không biết" in response    │
│    → force HANDOFF             │
└────────────┬────────────────────┘
             │
         ┌───┴───┐
         ▼       ▼
      REPLY   HANDOFF
```

## Chi tiết từng Node

### Node 1: Classify Intent (parallel)

```python
async def classify_intent(state: ChatState) -> dict:
    """
    Phân loại ý định khách hàng.
    Chạy SONG SONG với embed_query để tiết kiệm thời gian.
    
    Intents:
    - faq: Hỏi thông tin (giờ mở cửa, chính sách, etc.)
    - sales: Quan tâm mua hàng (hỏi giá, so sánh, etc.)
    - support: Cần hỗ trợ kỹ thuật (lỗi, không hoạt động, etc.)
    - complaint: Phàn nàn, tức giận → HANDOFF NGAY
    - chitchat: Chào hỏi, nói chuyện phiếm
    """
    last_message = state["messages"][-1]["content"]
    
    # Gọi AI Core (model rẻ, nhanh)
    response = await ai_core_client.complete(
        tenant_id=state["tenant_id"],
        use_case="classification",
        system_prompt=INTENT_CLASSIFICATION_PROMPT,
        messages=[{"role": "user", "content": last_message}],
        max_tokens=50,
        temperature=0.0,
    )
    
    # Parse result
    result = json.loads(response.content)
    # {"intent": "faq", "language": "vi", "sentiment": "neutral"}
    
    return {
        "intent": result["intent"],
        "language": result["language"],
        "sentiment": result["sentiment"],
    }

INTENT_CLASSIFICATION_PROMPT = """Classify the customer message.
Return JSON only: {"intent": "faq|sales|support|complaint|chitchat", "language": "vi|en|...", "sentiment": "positive|neutral|negative|angry"}
Rules:
- If customer is angry, frustrated, or complaining → intent=complaint
- If asking about price, buying, ordering → intent=sales
- If greeting, small talk → intent=chitchat
- If reporting a problem, error → intent=support
- Otherwise → intent=faq"""
```

### Node 2: Embed Query (parallel)

```python
async def embed_query(state: ChatState) -> dict:
    """
    Embed câu hỏi thành vector để search Knowledge Base.
    Chạy SONG SONG với classify_intent.
    Cache embedding nếu câu hỏi giống nhau.
    """
    query = state["messages"][-1]["content"]
    
    # Check cache first
    cache_key = f"embed:{hashlib.md5(query.encode()).hexdigest()}"
    cached = await redis.get(cache_key)
    if cached:
        return {"query_embedding": json.loads(cached)}
    
    # Call AI Core embed
    response = await ai_core_client.embed(
        tenant_id=state["tenant_id"],
        texts=[query],
        dimensions=512,
    )
    
    embedding = response.embeddings[0].values
    
    # Cache for 1 hour
    await redis.setex(cache_key, 3600, json.dumps(embedding))
    
    return {"query_embedding": embedding}
```

### Node 3: Route by Intent

```python
def route_after_intent(state: ChatState) -> str:
    """
    Quyết định đi đâu tiếp theo dựa trên intent + sentiment.
    
    RULE QUAN TRỌNG:
    - complaint hoặc angry → HANDOFF NGAY, không cần RAG
    - chitchat → generate simple reply, không cần RAG
    - faq/sales/support → cần RAG để trả lời chính xác
    """
    if state["intent"] == "complaint" or state["sentiment"] == "angry":
        return "handoff"  # Không bao giờ để bot trả lời khách đang giận
    
    if state["intent"] == "chitchat":
        return "chitchat"  # Chào hỏi đơn giản, không cần knowledge
    
    return "retrieve"  # Cần tìm thông tin từ KB
```

### Node 4: Retrieve Knowledge

```python
async def retrieve_knowledge(state: ChatState) -> dict:
    """
    Gọi Knowledge Base service để tìm thông tin relevant.
    
    Flow:
    1. Call KB hybrid search API
    2. KB thực hiện: vector search + BM25 + rerank
    3. Trả về top-5 documents kèm max_similarity_score của cả đợt search.
    4. Kiểm tra quality: nếu max_similarity_score < 0.5 → không có info → handoff
    """
    response = await http_client.post(
        f"{KB_URL}/api/v1/search",
        json={
            "query": state["messages"][-1]["content"],
            "tenant_id": state["tenant_id"],
            "top_k": 5,
        }
    )
    
    data = response.json()
    results = data.get("results", [])
    max_similarity_score = data.get("max_similarity_score", 0.0)
    
    # Quality check: nếu không tìm được gì relevant hoặc max_similarity_score < 0.50
    if not results or max_similarity_score < 0.50:
        return {
            "context_docs": [],
            "retrieval_quality": "no_relevant_docs",
            "max_similarity_score": max_similarity_score,
            "handoff_reason": "rag_no_docs_found"
        }
    
    return {
        "context_docs": results,
        "retrieval_quality": "good",
        "max_similarity_score": max_similarity_score
    }
```

### Node 5: Generate Response

```python
async def generate_response(state: ChatState) -> dict:
    """
    Gọi AI Core để generate response dựa trên context.
    
    QUAN TRỌNG:
    - Chỉ trả lời dựa trên context (không hallucinate)
    - Yêu cầu LLM trả về confidence score
    - Nếu context không đủ → LLM phải nói "không biết" → confidence thấp
    """
    # Nếu không có docs relevant → handoff ngay
    if state["retrieval_quality"] == "no_relevant_docs":
        return {
            "response": "",
            "confidence": 0.0,
            "action": "handoff",
        }
    
    # Build context from retrieved docs
    context = "\n---\n".join([
        doc["content"][:500]  # Truncate mỗi doc 500 chars
        for doc in state["context_docs"][:3]  # Top 3 only
    ])
    
    # Get compressed history
    history = state["messages"][-10:]  # Last 10 messages
    
    # Call AI Core via gRPC
    response = await ai_core_client.complete(
        tenant_id=state["tenant_id"],
        use_case="chatbot",
        system_prompt=CHATBOT_SYSTEM_PROMPT,
        messages=[
            {"role": "system", "content": f"Context:\n{context}"},
            *history,
        ],
        max_tokens=300,
        temperature=0.3,
    )
    
    # Parse structured response
    parsed = json.loads(response.content)
    # {"text": "Sản phẩm A giá 500k ạ.", "confidence": 0.85}
    
    return {
        "response": parsed["text"],
        "confidence": parsed["confidence"],
    }

CHATBOT_SYSTEM_PROMPT = """You are a customer service assistant.
Language: {language}

CRITICAL RULES:
1. Answer ONLY based on the provided Context
2. If the Context does not contain the answer, respond with:
   {{"text": "", "confidence": 0.0}}
3. NEVER make up information
4. Be concise (2-3 sentences max)
5. Match the customer's language

Return JSON: {{"text": "your answer", "confidence": 0.0-1.0}}
- confidence 0.9-1.0: Answer is directly in context
- confidence 0.7-0.8: Answer is implied by context
- confidence 0.0-0.6: Not sure / not in context"""
```

### Node 6: Evaluate Confidence & Decide Action

```python
def evaluate_and_decide(state: ChatState) -> dict:
    """
    Quyết định cuối cùng: reply hay handoff.
    
    NGUYÊN TẮC VÀNG: Thà handoff nhầm còn hơn trả lời sai.
    Sai 1 câu = mất khách. Handoff = khách vẫn được hỗ trợ.
    """
    confidence = state["confidence"]
    response = state["response"]
    
    # Check if handoff was already triggered in previous node (e.g. no docs found)
    if state.get("handoff_reason") == "rag_no_docs_found":
        return {"action": "handoff", "handoff_reason": "rag_no_docs_found"}
        
    # Force handoff conditions
    if confidence < 0.7:
        return {"action": "handoff", "handoff_reason": "confidence_low"}
    
    if not response or len(response.strip()) < 5:
        return {"action": "handoff", "handoff_reason": "empty_response"}
    
    # Check for "I don't know" patterns
    dont_know_patterns = [
        "tôi không biết", "không có thông tin", "i don't know",
        "i'm not sure", "không rõ", "chưa có thông tin",
    ]
    if any(p in response.lower() for p in dont_know_patterns):
        return {"action": "handoff", "handoff_reason": "confidence_low"}
        
    # Check for NLI grounding validation status (if applicable)
    if state.get("grounding_score") is not None and state["grounding_score"] < 0.80:
        return {"action": "handoff", "handoff_reason": "nli_grounding_violation"}
    
    # All checks passed → reply
    return {"action": "reply", "handoff_reason": None}
```

### Node 7: Chitchat Response

```python
async def generate_chitchat(state: ChatState) -> dict:
    """
    Trả lời chitchat đơn giản (chào hỏi, cảm ơn, etc.)
    Không cần RAG, dùng model rẻ nhất.
    """
    response = await ai_core_client.complete(
        tenant_id=state["tenant_id"],
        use_case="chatbot",
        system_prompt="You are a friendly assistant. Respond briefly to greetings and small talk. Language: " + state["language"],
        messages=state["messages"][-3:],  # Only last 3 messages
        max_tokens=100,
        temperature=0.5,
    )
    
    return {
        "response": response.content,
        "confidence": 0.95,  # Chitchat always high confidence
        "action": "reply",
    }
```

---

## Conversation State (LangGraph Checkpoint)

```python
class ChatState(TypedDict):
    # Input
    tenant_id: str
    conversation_id: str
    messages: Annotated[list, operator.add]  # Append-only
    
    # Processing
    intent: str                    # faq/sales/support/complaint/chitchat
    language: str                  # vi/en/...
    sentiment: str                 # positive/neutral/negative/angry
    query_embedding: list[float]   # 512-dim vector
    context_docs: list[dict]       # RAG results
    retrieval_quality: str         # good/no_relevant_docs
    
    # Output
    response: str                  # Generated text
    confidence: float              # 0.0 - 1.0
    action: str                    # reply/handoff/clarify
```

**Checkpoint persistence:**
- Mỗi conversation có 1 checkpoint trong PostgreSQL
- Khi khách reply tiếp → load checkpoint → resume graph
- Cho phép multi-turn conversation với context

---

## Timeout & Fallback

```python
async def process_with_timeout(state: ChatState) -> ChatResponse:
    """
    Toàn bộ pipeline phải hoàn thành trong 5s.
    Nếu timeout → handoff ngay.
    """
    try:
        result = await asyncio.wait_for(
            self.graph.ainvoke(state),
            timeout=5.0
        )
        return result
    except asyncio.TimeoutError:
        # Timeout → handoff
        return ChatResponse(
            response_text="",
            confidence_score=0.0,
            action=Action.HANDOFF,
            intent="timeout",
            sentiment="unknown",
            max_similarity_score=0.0,
            handoff_reason="timeout",
        )
    except Exception as e:
        # Any error → handoff (safe fallback)
        logger.error(f"Chatbot error: {e}")
        return ChatResponse(
            response_text="",
            confidence_score=0.0,
            action=Action.HANDOFF,
            intent="error",
            sentiment="unknown",
            max_similarity_score=0.0,
            handoff_reason="error",
        )
```

---

## Performance Budget (< 2000ms total)

| Step | Budget | Actual | Notes |
|------|--------|--------|-------|
| gRPC receive | 10ms | ~5ms | Protobuf deserialization |
| Classify intent | 300ms | ~250ms | GPT-4o-mini, cached prompt |
| Embed query | 100ms | ~80ms | text-embedding-3-small (parallel with classify) |
| **Parallel total** | **300ms** | **~250ms** | Max of classify/embed |
| KB search | 50ms | ~40ms | Hybrid + rerank |
| Generate response | 1200ms | ~1000ms | GPT-4o-mini, optimized context |
| Evaluate + decide | 5ms | ~2ms | Local logic |
| gRPC respond | 10ms | ~5ms | Protobuf serialization |
| **Total** | **1575ms** | **~1300ms** | Well under 2s |


## Zero-Trust Security & Dynamic RBAC Logic

Dịch vụ thực hiện cơ chế xác thực Zero-Trust và phân quyền động (Dynamic RBAC) dựa trên HMAC Signed Headers được truyền từ API Gateway:

### 1. Quy trình xác thực chữ ký (HMAC Verification Flow)
- Dịch vụ trích xuất các headers từ request:
  - `X-Tenant-ID`: ID của Tenant.
  - `X-User-ID`: ID của User.
  - `X-User-Permissions`: Chuỗi CSV chứa danh sách quyền của người dùng (ví dụ: `chatbot:{resource}:{action}`).
  - `X-Permissions-Signature`: Chữ ký HMAC-SHA256 dạng hex.
- Dịch vụ tính toán signature dự kiến bằng khóa bí mật `GATEWAY_SIGNING_SECRET`:
  `expected_sig = HMAC_SHA256(GATEWAY_SIGNING_SECRET, X-Tenant-ID + ":" + X-User-ID + ":" + X-User-Permissions)`
- So sánh chữ ký nhận được với `expected_sig` sử dụng hàm so sánh an toàn chống Side-channel attack (ví dụ: so sánh độ dài không đổi/safe compare). Nếu không khớp, từ chối request với mã lỗi `403 Forbidden` và tăng counter metric lỗi bảo mật.

### 2. So khớp quyền hạn In-Memory O(1)
- Sau khi chữ ký được xác thực, dịch vụ chuyển chuỗi `X-User-Permissions` thành một cấu trúc Set để tìm kiếm với độ phức tạp $O(1)$.
- Đối với mỗi API endpoint yêu cầu quyền hạn `chatbot:{resource}:{action}`, dịch vụ kiểm tra quyền trong Set:
  - Nếu Set chứa `*` (Super Admin), cho phép truy cập.
  - Nếu Set chứa `chatbot:*` (Toàn quyền trên dịch vụ), cho phép truy cập.
  - Nếu Set chứa `chatbot:{resource}:*` (Toàn quyền trên tài nguyên), cho phép truy cập.
  - Nếu Set chứa chính xác `chatbot:{resource}:{action}`, cho phép truy cập.
  - Ngược lại, từ chối truy cập và trả về mã lỗi `403 Forbidden` kèm log lỗi chi tiết.

---

## Business Logic — Service Self-Registration

### 1. Logic Đăng ký (Startup Hook)
* BƯỚC 1: Gọi hàm `_get_internal_ip()` sử dụng socket UDP giả lập kết nối tới `8.8.8.8:80` để lấy IP nội bộ của container.
* BƯỚC 2: Định nghĩa chuỗi node dạng `{ip}:{port}`.
* BƯỚC 3: Thực hiện pipeline ghi vào Redis:
  * `SADD registry:service:chatbot "{ip}:{port}"`
  * `SETEX registry:service:chatbot:node:{ip}:{port} 15 "alive"`
* BƯỚC 4: Bắt đầu chạy vòng lặp heartbeat (mỗi 5 giây) để gửi lại gói tin `SETEX` và `SADD` để làm mới TTL.

### 2. Logic Hủy đăng ký (Shutdown Hook)
* BƯỚC 1: Dừng vòng lặp heartbeat.
* BƯỚC 2: Thực hiện pipeline dọn dẹp Redis:
  * `SREM registry:service:chatbot "{ip}:{port}"`
  * `DEL registry:service:chatbot:node:{ip}:{port}"`


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
