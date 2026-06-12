import hashlib
import logging
import time
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class QueryRewriter:
    def __init__(self, redis_client, llm_gateway):
        self.redis_client = redis_client
        self.llm_gateway = llm_gateway

    async def rewrite(self, tenant_id: str, messages: List[Dict[str, Any]]) -> str:
        """
        Rewrites the last user query in messages to be a standalone query based on conversation history.
        Only triggers for chatbot usecase with messages count >= 2.
        """
        start_time = time.time()
        
        # 1. Condition check: bypass if messages length < 2
        if not messages or len(messages) < 2:
            return messages[-1].get("content", "") if messages else ""

        # Only process up to last 6 messages to keep context window and history brief
        recent_messages = messages[-6:]
        
        # Verify the last message is from user
        last_message = recent_messages[-1]
        if last_message.get("role") != "user":
            return last_message.get("content", "")

        original_query = last_message.get("content", "")
        if not original_query:
            return ""

        # Construct history string
        history = recent_messages[:-1]
        history_str = "\n".join([f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in history])

        # 2. Check Cache
        cache_key = self._get_cache_key(tenant_id, history_str, original_query)
        try:
            cached_query = await self._check_cache(cache_key)
            if cached_query:
                # Log hit or reuse
                latency = int((time.time() - start_time) * 1000)
                logger.info({
                    "action": "query_rewritten",
                    "tenant_id": tenant_id,
                    "message": "Query rewritten successfully (cache hit)",
                    "context": {
                        "original_query": original_query,
                        "standalone_query": cached_query,
                        "query_rewritten": True,
                        "latency_ms": latency,
                        "model_used": "redis-cache"
                    }
                })
                return cached_query
        except Exception as cache_err:
            logger.warning(f"Error checking query rewrite cache for tenant {tenant_id}: {cache_err}")

        # 3. Call LLM to rewrite
        prompt = self._build_prompt(history_str, original_query)
        
        try:
            # Call using summarization use case (cheapest settings, low temperature, short output)
            response = await self.llm_gateway.complete(
                tenant_id=tenant_id,
                use_case="summarization",
                messages=[{"role": "user", "content": prompt}]
            )
            
            standalone_query = response.get("content", "").strip()
            
            # Clean quotes if model wrapped it
            if (standalone_query.startswith('"') and standalone_query.endswith('"')) or \
               (standalone_query.startswith("'") and standalone_query.endswith("'")):
                standalone_query = standalone_query[1:-1].strip()

            model_used = response.get("model_used", "unknown")
            latency = int((time.time() - start_time) * 1000)

            # If empty or identical, mark as not rewritten
            query_rewritten = (standalone_query != original_query) and bool(standalone_query)
            final_query = standalone_query if standalone_query else original_query

            # Store to cache
            if final_query:
                try:
                    await self._store_cache(cache_key, final_query)
                except Exception as cache_err:
                    logger.warning(f"Error storing query rewrite cache: {cache_err}")

            logger.info({
                "action": "query_rewritten",
                "tenant_id": tenant_id,
                "message": "Query rewritten successfully",
                "context": {
                    "original_query": original_query,
                    "standalone_query": final_query,
                    "query_rewritten": query_rewritten,
                    "latency_ms": latency,
                    "model_used": model_used
                }
            })
            
            return final_query

        except Exception as llm_err:
            # 4. Fallback on error
            latency = int((time.time() - start_time) * 1000)
            logger.warning({
                "action": "rewrite_fallback",
                "tenant_id": tenant_id,
                "message": "Query rewrite failed, falling back to original query",
                "context": {
                    "original_query": original_query,
                    "error_message": str(llm_err),
                    "latency_ms": latency
                }
            })
            return original_query

    def _build_prompt(self, history_str: str, current_question: str) -> str:
        return f"""Bạn là một trợ lý tối ưu hóa câu truy vấn.
Dựa vào lịch sử đàm thoại bên dưới, hãy viết lại câu hỏi cuối cùng 
thành một câu HOÀN CHỈNH, TỰ CHỨA (không cần đọc lịch sử mới hiểu được).

Quy tắc:
- Giữ nguyên ngôn ngữ (tiếng Việt/Anh)
- Chỉ trả về câu hỏi viết lại, KHÔNG giải thích
- Nếu câu hỏi đã rõ ràng, trả về nguyên gốc

Lịch sử: {history_str}
Câu hỏi cuối: {current_question}
Câu hỏi viết lại:"""

    def _get_cache_key(self, tenant_id: str, history_str: str, current_question: str) -> str:
        hash_input = f"{history_str}{current_question}"
        md5_hash = hashlib.md5(hash_input.encode("utf-8")).hexdigest()
        return f"query_rewrite:{tenant_id}:{md5_hash}"

    async def _check_cache(self, key: str) -> str | None:
        val = await self.redis_client.get(key)
        return val.decode("utf-8") if val else None

    async def _store_cache(self, key: str, query: str) -> None:
        await self.redis_client.setex(key, 3600, query)
