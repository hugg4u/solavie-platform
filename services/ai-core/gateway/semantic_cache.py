import hashlib
import logging
import struct
from datetime import datetime, timezone
from fastembed import TextEmbedding
import redis.asyncio as aioredis
from redis.commands.search.field import TextField, TagField, VectorField
try:
    from redis.commands.search.index_definition import IndexDefinition, IndexType
except ModuleNotFoundError:
    from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from core.config import settings

logger = logging.getLogger(__name__)

class SemanticCacheManager:
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SemanticCacheManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.redis_client = aioredis.from_url(settings.REDIS_STACK_URL, decode_responses=False)
        # Note: decode_responses must be False because vector field contains raw binary bytes (float32)
        # that will fail to decode to UTF-8.
        
        logger.info("Initializing FastEmbed TextEmbedding (sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)...")
        self.embedding_model = TextEmbedding("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        self._initialized = True

    async def create_index(self):
        """Creates the RediSearch HNSW vector index if it does not exist."""
        try:
            await self.redis_client.ft("idx:semantic_cache").info()
            logger.info("Semantic cache index 'idx:semantic_cache' already exists.")
        except Exception:
            logger.info("Semantic cache index 'idx:semantic_cache' not found. Creating a new one...")
            schema = [
                TagField("tenant_id"),
                TagField("use_case"),
                TextField("question"),
                TextField("response"),
                VectorField(
                    "vector",
                    "HNSW",
                    {
                        "TYPE": "FLOAT32",
                        "DIM": 384,
                        "DISTANCE_METRIC": "COSINE",
                    }
                )
            ]
            definition = IndexDefinition(prefix=["semantic_cache:"], index_type=IndexType.HASH)
            try:
                await self.redis_client.ft("idx:semantic_cache").create_index(fields=schema, definition=definition)
                logger.info("Successfully created semantic cache index 'idx:semantic_cache'.")
            except Exception as ex:
                logger.error(f"Failed to create semantic cache index: {ex}")

    def _embed(self, text: str) -> list[float]:
        """Generates a 384-dimensional embedding vector locally."""
        query_text = f"query: {text}"
        embeddings = list(self.embedding_model.embed([query_text]))
        return list(embeddings[0])

    async def lookup(self, tenant_id: str, use_case: str, question: str) -> tuple[str | None, float]:
        """
        Looks up semantic cache for a similar question in the given tenant and use case.
        Returns (response, similarity) if similarity >= threshold, else (None, 0.0).
        """
        try:
            vector = self._embed(question)
            vector_bytes = struct.pack(f"{len(vector)}f", *vector)

            # Escape hyphens to avoid search query syntax errors
            tenant_id_escaped = tenant_id.replace("-", "\\-")
            use_case_escaped = use_case.replace("-", "\\-")

            query_str = f"(@tenant_id:{{{tenant_id_escaped}}} @use_case:{{{use_case_escaped}}})=>[KNN 1 @vector $query_vec AS vector_score]"
            q = Query(query_str)\
                .sort_by("vector_score")\
                .paging(0, 1)\
                .return_fields("question", "response", "vector_score")\
                .dialect(2)

            res = await self.redis_client.ft("idx:semantic_cache").search(q, query_params={"query_vec": vector_bytes})

            if res.docs:
                doc = res.docs[0]
                distance = float(doc.vector_score)
                similarity = 1.0 - distance

                if similarity >= settings.SEMANTIC_CACHE_THRESHOLD:
                    response_str = doc.response
                    if isinstance(response_str, bytes):
                        response_str = response_str.decode('utf-8')
                    
                    # Structured JSON log for Cache Hit
                    logger.info(
                        "Semantic cache hit",
                        extra={
                            "action": "cache_hit",
                            "tenant_id": tenant_id,
                            "context": {
                                "use_case": use_case,
                                "similarity_score": similarity,
                                "question": question
                            }
                        }
                    )
                    return response_str, similarity
                else:
                    logger.info(
                        "Semantic cache miss (below threshold)",
                        extra={
                            "action": "cache_miss",
                            "tenant_id": tenant_id,
                            "context": {
                                "use_case": use_case,
                                "similarity_score": similarity,
                                "question": question
                            }
                        }
                    )
            else:
                logger.info(
                    "Semantic cache miss (no matches)",
                    extra={
                        "action": "cache_miss",
                        "tenant_id": tenant_id,
                        "context": {
                            "use_case": use_case,
                            "question": question
                        }
                    }
                )
        except Exception as e:
            logger.error(
                "Error during semantic cache lookup",
                extra={
                    "action": "cache_error",
                    "tenant_id": tenant_id,
                    "context": {"error": str(e)}
                },
                exc_info=True
            )

        return None, 0.0

    async def write_async(self, tenant_id: str, use_case: str, question: str, response: str):
        """Asynchronously writes the question, response, and its embedding vector to cache."""
        try:
            vector = self._embed(question)
            vector_bytes = struct.pack(f"{len(vector)}f", *vector)
            hash_val = hashlib.md5(question.encode('utf-8')).hexdigest()
            key = f"semantic_cache:{tenant_id}:{hash_val}"

            mapping = {
                "tenant_id": tenant_id,
                "use_case": use_case,
                "question": question,
                "response": response,
                "vector": vector_bytes,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await self.redis_client.hset(key, mapping=mapping)
            await self.redis_client.expire(key, settings.SEMANTIC_CACHE_TTL)
            
            logger.info(
                "Successfully cached response in semantic cache",
                extra={
                    "action": "cache_write",
                    "tenant_id": tenant_id,
                    "context": {
                        "key": key,
                        "use_case": use_case
                    }
                }
            )
        except Exception as e:
            logger.error(
                "Failed to write response to semantic cache",
                extra={
                    "action": "cache_write_error",
                    "tenant_id": tenant_id,
                    "context": {"error": str(e)}
                },
                exc_info=True
            )
