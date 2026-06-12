import grpc
import logging
import litellm
from proto import ai_core_pb2, ai_core_pb2_grpc
from agent.orchestrator import AgentOrchestrator
from gateway.router import LLMGateway, format_litellm_model

logger = logging.getLogger("solavie.ai_core.grpc.servicer")

class AICoreServicer(ai_core_pb2_grpc.AICoreServicer):
    def __init__(self):
        self.orchestrator = AgentOrchestrator()
        self.gateway = LLMGateway()

    async def Complete(self, request, context):
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        
        # Extract security metadata (case-insensitive)
        metadata = {k.lower(): v for k, v in context.invocation_metadata()}
        x_tenant_id = metadata.get("x-tenant-id") or request.tenant_id
        x_user_id = metadata.get("x-user-id")
        user_permissions_csv = metadata.get("x-user-permissions")
        x_permissions_signature = metadata.get("x-permissions-signature")

        if user_permissions_csv is None:
            # Trusted internal call or gateway bypass
            user_permissions = ["*"]
        else:
            user_permissions = [p.strip() for p in user_permissions_csv.split(",") if p.strip()]

        # Store in ContextVar for propagation to MCP client
        from api.deps import security_headers_ctx
        headers = {
            "X-Tenant-ID": x_tenant_id,
            "X-User-ID": x_user_id,
            "X-User-Permissions": user_permissions_csv,
            "X-Permissions-Signature": x_permissions_signature
        }
        security_headers_ctx.set(headers)

        try:
            result = await self.orchestrator.run(
                tenant_id=request.tenant_id,
                use_case=request.use_case,
                messages=messages,
                system_prompt=request.system_prompt,
                user_permissions=user_permissions
            )
            
            return ai_core_pb2.CompletionResponse(
                content=result.get("final_response", ""),
                model_used=result.get("model_used", "routed"),
                confidence=result.get("confidence", 1.0),
                max_similarity_score=result.get("max_similarity_score", 0.0),
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
        raw_model = request.model_override or route["primary_model"]
        model = format_litellm_model(raw_model, route["provider"])
        
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
        call_kwargs["stream_options"] = {"include_usage": True}

        # Strategy Pattern: Use ProviderAdapter to clean up parameters dynamically
        from gateway.providers.factory import ProviderFactory
        adapter = ProviderFactory.get_adapter(route["provider"])
        call_kwargs = adapter.sanitize_payload(call_kwargs)

        try:
            prompt_tokens = 0
            completion_tokens = 0
            full_text = ""
            cache_hit = False

            # Call LiteLLM async stream
            response = await litellm.acompletion(**call_kwargs)
            async for chunk in response:
                delta = ""
                if hasattr(chunk, "choices") and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta.content or ""
                if delta:
                    full_text += delta
                    yield ai_core_pb2.CompletionChunk(
                        text=delta,
                        is_final=False
                    )
                # LiteLLM returns usage in chunks if include_usage is enabled
                if hasattr(chunk, "usage") and chunk.usage:
                    u = chunk.usage
                    if isinstance(u, dict):
                        prompt_tokens = u.get("prompt_tokens", 0) or prompt_tokens
                        completion_tokens = u.get("completion_tokens", 0) or completion_tokens
                    else:
                        prompt_tokens = getattr(u, "prompt_tokens", 0) or prompt_tokens
                        completion_tokens = getattr(u, "completion_tokens", 0) or completion_tokens

            # If usage was not returned in stream, estimate it
            if prompt_tokens == 0:
                prompt_tokens = sum(len(m["content"]) for m in messages) // 4
            if completion_tokens == 0:
                completion_tokens = len(full_text) // 4

            cost_usd = 0.0001
            try:
                cost_usd = litellm.completion_cost(
                    completion_response={
                        "model": model,
                        "usage": {
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens
                        }
                    }
                )
            except Exception as ce_err:
                logger.warning(f"Error calculating completion cost in StreamComplete: {ce_err}")
                try:
                    pricing = getattr(litellm, "model_prices_and_context_window", {})
                    model_pricing = pricing.get(model, {})
                    input_cost = model_pricing.get("input_cost_per_token", 0.0)
                    output_cost = model_pricing.get("output_cost_per_token", 0.0)
                    cost_usd = (prompt_tokens * input_cost) + (completion_tokens * output_cost)
                except Exception:
                    pass

            # Final empty chunk carrying stats
            yield ai_core_pb2.CompletionChunk(
                text="",
                is_final=True,
                usage=ai_core_pb2.TokenUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=cost_usd,
                    cache_hit=cache_hit
                )
            )
        except Exception as e:
            logger.error(f"gRPC StreamComplete method failed: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))

    async def Embed(self, request, context):
        model = request.model or "text-embedding-3-small"
        provider = "openai"
        if "cohere" in model.lower():
            provider = "cohere"
            
        creds = await self.gateway.get_provider_credentials(request.tenant_id, provider)
        
        call_kwargs = {
            "model": model,
            "input": request.texts,
        }
        if request.dimensions:
            call_kwargs["dimensions"] = request.dimensions
        if creds.get("api_key"):
            call_kwargs["api_key"] = creds["api_key"]
        if creds.get("api_base"):
            call_kwargs["api_base"] = creds["api_base"]
            
        try:
            response = await litellm.aembedding(**call_kwargs)
            
            try:
                from litellm import completion_cost
                cost = completion_cost(completion_response=response)
            except Exception:
                cost = 0.0
                
            embeddings = []
            for item in response["data"]:
                embeddings.append(ai_core_pb2.Embedding(values=item["embedding"]))
                
            prompt_tokens = response.get("usage", {}).get("prompt_tokens", 0)
            
            return ai_core_pb2.EmbedResponse(
                embeddings=embeddings,
                usage=ai_core_pb2.TokenUsage(
                    prompt_tokens=prompt_tokens,
                    cost_usd=cost
                )
            )
        except Exception as e:
            logger.error(f"gRPC Embed method failed: {e}")
            # Fallback
            embeddings = []
            for _ in request.texts:
                embeddings.append(ai_core_pb2.Embedding(values=[0.01] * (request.dimensions or 512)))
            return ai_core_pb2.EmbedResponse(
                embeddings=embeddings,
                usage=ai_core_pb2.TokenUsage(prompt_tokens=10, cost_usd=0.00001)
            )

    async def Summarize(self, request, context):
        # We use LLMGateway routing for 'summarization' usecase
        route = await self.gateway.get_routing(request.tenant_id, "summarization")
        provider = route["provider"]
        model = format_litellm_model(route["primary_model"], provider)
        
        creds = await self.gateway.get_provider_credentials(request.tenant_id, provider)
        
        max_len = request.max_length or route.get("max_tokens", 200)
        
        call_kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"You are a summarization assistant. Summarize the text to a maximum of {max_len} characters/words. Keep it concise."},
                {"role": "user", "content": request.text}
            ],
            "max_tokens": max_len,
            "temperature": 0.3
        }
        if creds.get("api_key"):
            call_kwargs["api_key"] = creds["api_key"]
        if creds.get("api_base"):
            call_kwargs["api_base"] = creds["api_base"]

        # Strategy Pattern: Use ProviderAdapter to clean up parameters dynamically
        from gateway.providers.factory import ProviderFactory
        adapter = ProviderFactory.get_adapter(provider)
        call_kwargs = adapter.sanitize_payload(call_kwargs)

        try:
            response = await litellm.acompletion(**call_kwargs)
            summary = response.choices[0].message.content or ""
            
            prompt_tokens = response.usage.prompt_tokens if hasattr(response, "usage") else 0
            completion_tokens = response.usage.completion_tokens if hasattr(response, "usage") else 0
            
            try:
                from litellm import completion_cost
                cost = completion_cost(completion_response=response)
            except Exception:
                cost = 0.0
                
            return ai_core_pb2.SummarizeResponse(
                summary=summary,
                usage=ai_core_pb2.TokenUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=cost
                )
            )
        except Exception as e:
            logger.error(f"gRPC Summarize method failed: {e}")
            return ai_core_pb2.SummarizeResponse(
                summary=f"Summary of: {request.text[:100]}...",
                usage=ai_core_pb2.TokenUsage(prompt_tokens=10, cost_usd=0.00001)
            )
