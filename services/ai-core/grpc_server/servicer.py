import grpc
import logging
import litellm
from proto import ai_core_pb2, ai_core_pb2_grpc
from agent.orchestrator import AgentOrchestrator
from gateway.router import LLMGateway

logger = logging.getLogger("solavie.ai_core.grpc.servicer")

class AICoreServicer(ai_core_pb2_grpc.AICoreServicer):
    def __init__(self):
        self.orchestrator = AgentOrchestrator()
        self.gateway = LLMGateway()

    async def Complete(self, request, context):
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        try:
            result = await self.orchestrator.run(
                tenant_id=request.tenant_id,
                use_case=request.use_case,
                messages=messages,
                system_prompt=request.system_prompt
            )
            
            return ai_core_pb2.CompletionResponse(
                content=result.get("final_response", ""),
                model_used=result.get("model_used", "routed"),
                confidence=result.get("confidence", 1.0),
                usage=ai_core_pb2.TokenUsage(
                    prompt_tokens=result.get("total_tokens_used", 0) // 2,
                    completion_tokens=result.get("total_tokens_used", 0) // 2,
                    cost_usd=result.get("cost_usd", 0.0),
                    cache_hit=False
                )
            )
        except Exception as e:
            logger.error(f"gRPC Complete method failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ai_core_pb2.CompletionResponse()

    async def StreamComplete(self, request, context):
        """gRPC Streaming completions endpoint supporting named router and credentials."""
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        
        # Fetch dynamic route
        route = await self.gateway.get_routing(request.tenant_id, request.use_case)
        model = request.model_override or route["primary_model"]
        
        # API Keys must rely on injected tenant header or database config,
        # but in gRPC request.tenant_id is directly passed.
        # Fallback to system keys if not provided.
        creds = await self.gateway.get_provider_credentials(request.tenant_id, route["provider"])
        
        call_kwargs = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens or route["max_tokens"],
            "temperature": request.temperature if request.temperature != 0.0 else route["temperature"],
            "stream": True,
            "timeout": 15.0
        }
        if creds.get("api_key"):
            call_kwargs["api_key"] = creds["api_key"]
        if creds.get("api_base"):
            call_kwargs["api_base"] = creds["api_base"]
            
        try:
            # Call LiteLLM async stream
            response = await litellm.acompletion(**call_kwargs)
            async for chunk in response:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield ai_core_pb2.CompletionChunk(
                        text=delta,
                        is_final=False
                    )
            # Final empty chunk carrying stats
            yield ai_core_pb2.CompletionChunk(
                text="",
                is_final=True,
                usage=ai_core_pb2.TokenUsage(
                    prompt_tokens=100,
                    completion_tokens=50,
                    cost_usd=0.0001,
                    cache_hit=False
                )
            )
        except Exception as e:
            logger.error(f"gRPC StreamComplete method failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))

    async def Embed(self, request, context):
        embeddings = []
        for _ in request.texts:
            embeddings.append(ai_core_pb2.Embedding(values=[0.01] * 512))
        return ai_core_pb2.EmbedResponse(
            embeddings=embeddings,
            usage=ai_core_pb2.TokenUsage(prompt_tokens=10, cost_usd=0.00001)
        )

    async def Summarize(self, request, context):
        return ai_core_pb2.SummarizeResponse(
            summary=f"Summary of: {request.text[:100]}...",
            usage=ai_core_pb2.TokenUsage(prompt_tokens=10, cost_usd=0.00001)
        )
