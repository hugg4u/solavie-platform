import logging
import time
from typing import List, Dict, Any, AsyncGenerator
import litellm
from litellm import acompletion, completion_cost

from core.config import settings

logger = logging.getLogger(__name__)

# Model Routing Configuration
MODEL_ROUTING = {
    "chatbot": {
        "primary": "gpt-4o-mini",
        "fallback": "claude-3-haiku-20240307",
        "max_tokens": 300,
        "temperature": 0.3,
        "provider": "openai",
        "fallback_provider": "anthropic"
    },
    "content_generation": {
        "primary": "claude-3-5-sonnet-20241022",
        "fallback": "gpt-4o",
        "max_tokens": 1500,
        "temperature": 0.7,
        "provider": "anthropic",
        "fallback_provider": "openai"
    },
    "sentiment": {
        "primary": "gpt-4o-mini",
        "fallback": "claude-3-haiku-20240307",
        "max_tokens": 50,
        "temperature": 0.0,
        "provider": "openai",
        "fallback_provider": "anthropic"
    },
    "summarization": {
        "primary": "gpt-4o-mini",
        "fallback": "claude-3-haiku-20240307",
        "max_tokens": 200,
        "temperature": 0.2,
        "provider": "openai",
        "fallback_provider": "anthropic"
    },
    "classification": {
        "primary": "gpt-4o-mini",
        "fallback": "claude-3-haiku-20240307",
        "max_tokens": 50,
        "temperature": 0.0,
        "provider": "openai",
        "fallback_provider": "anthropic"
    }
}

class LLMGateway:
    def __init__(self):
        # Configure LiteLLM
        litellm.telemetry = False
        # Set up keys if provided in settings, otherwise look at environment
        if settings.OPENAI_API_KEY:
            litellm.api_key = settings.OPENAI_API_KEY
        if settings.ANTHROPIC_API_KEY:
            litellm.anthropic_key = settings.ANTHROPIC_API_KEY

    def _get_routing(self, use_case: str) -> Dict[str, Any]:
        return MODEL_ROUTING.get(use_case, MODEL_ROUTING["chatbot"])

    def compress_history(self, messages: List[Dict[str, Any]], keep_recent: int = 5) -> List[Dict[str, Any]]:
        """Compress old history to save tokens."""
        if len(messages) <= keep_recent:
            return messages
            
        recent = messages[-keep_recent:]
        older = messages[:-keep_recent]
        
        # Summarize or construct simple context of older messages
        summary_text = "Background summary of older messages:\n"
        for m in older:
            role = m.get("role", "user")
            content = m.get("content", "")
            summary_text += f"- {role}: {content[:100]}\n"
            
        # Return summary system prompt + recent messages
        return [{"role": "system", "content": summary_text}] + recent

    def optimize_context(self, messages: List[Dict[str, Any]], max_context_chars: int = 3200) -> List[Dict[str, Any]]:
        """Optimizes context documents within messages to avoid token blowup."""
        optimized = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "context" and len(content) > max_context_chars:
                # Truncate content keeping beginning and end
                content = content[:max_context_chars//2] + "\n...[TRUNCATED FOR TOKEN OPTIMIZATION]...\n" + content[-max_context_chars//2:]
            optimized.append({"role": role, "content": content})
        return optimized

    async def complete(
        self,
        tenant_id: str,
        use_case: str,
        messages: List[Dict[str, Any]],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        model_override: str | None = None,
        tools: List[Dict[str, Any]] | None = None
    ) -> Dict[str, Any]:
        """Sends chat completion using routing and failover with optional tool support."""
        route = self._get_routing(use_case)
        model = model_override or route["primary"]
        fallback_model = route["fallback"]
        
        # Format messages
        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)
        
        # Apply token optimization
        formatted_messages = self.compress_history(formatted_messages)
        formatted_messages = self.optimize_context(formatted_messages)
        
        # Max tokens and temperature
        max_tok = max_tokens or route["max_tokens"]
        temp = temperature if temperature is not None else route["temperature"]
        
        start_time = time.time()
        is_fallback_used = False
        
        kwargs = {
            "model": model,
            "messages": formatted_messages,
            "max_tokens": max_tok,
            "temperature": temp,
            "timeout": 10.0
        }
        if tools:
            kwargs["tools"] = tools
            
        try:
            # We wrap with a timeout of 10 seconds
            response = await acompletion(**kwargs)
            model_used = model
        except Exception as e:
            logger.warning(f"Primary model {model} failed for use case {use_case} on tenant {tenant_id}: {str(e)}. Falling back to {fallback_model}...")
            is_fallback_used = True
            
            kwargs["model"] = fallback_model
            kwargs["timeout"] = 15.0
            
            # Fallback call
            response = await acompletion(**kwargs)
            model_used = fallback_model
            
        latency = int((time.time() - start_time) * 1000)
        
        # Calculate cost
        try:
            cost = completion_cost(completion_response=response)
        except Exception:
            # Estimate cost
            cost = 0.0001
            
        prompt_tokens = response.usage.prompt_tokens if hasattr(response, "usage") else 0
        completion_tokens = response.usage.completion_tokens if hasattr(response, "usage") else 0
        
        choice_message = response.choices[0].message
        content = getattr(choice_message, "content", None)
        tool_calls = getattr(choice_message, "tool_calls", None)
        
        # Convert tool_calls to dict format if present for serializability
        tool_calls_list = []
        if tool_calls:
            for tc in tool_calls:
                tc_dict = {
                    "id": getattr(tc, "id", None),
                    "type": getattr(tc, "type", "function"),
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                tool_calls_list.append(tc_dict)
        
        return {
            "content": content,
            "tool_calls": tool_calls_list if tool_calls_list else None,
            "model_used": model_used,
            "provider": route["provider"] if not is_fallback_used else route["fallback_provider"],
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost,
            "latency_ms": latency,
            "cache_hit": response.get("cache_hit", False),
            "is_fallback": is_fallback_used
        }
