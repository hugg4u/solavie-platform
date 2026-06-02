import json
import logging
from typing import TypedDict, List, Dict, Any, Annotated
import operator

from gateway.router import LLMGateway
from tools.registry import ToolPermissionManager
from tools.executor import ToolExecutor

logger = logging.getLogger(__name__)

# State structure for LangGraph
class AgentState(TypedDict):
    messages: Annotated[List[Dict[str, Any]], operator.add]
    tenant_id: str
    use_case: str
    tools_called: List[str]
    iteration_count: int
    final_response: str
    confidence: float
    total_tokens_used: int

class AgentOrchestrator:
    def __init__(self):
        self.gateway = LLMGateway()
        self.permission_manager = ToolPermissionManager()
        self.executor = ToolExecutor()

    async def run(self, tenant_id: str, use_case: str, messages: List[Dict[str, Any]], system_prompt: str | None = None) -> Dict[str, Any]:
        """Runs the ReAct loop manually or via a simple loop to avoid complex Graph compilation dependencies in tests."""
        state: AgentState = {
            "messages": list(messages),
            "tenant_id": tenant_id,
            "use_case": use_case,
            "tools_called": [],
            "iteration_count": 0,
            "final_response": "",
            "confidence": 1.0,
            "total_tokens_used": 0
        }
        
        max_iterations = 5
        
        while state["iteration_count"] < max_iterations:
            # Check total token limit
            if state["total_tokens_used"] > 10000:
                logger.warning(f"Tenant {tenant_id} exceeded maximum token limit of 10000 per session.")
                state["final_response"] = "Error: Maximum session token limit exceeded (10000 tokens)."
                break
                
            # 1. Reason: get tools for the usecase and call LLM
            tools = self.permission_manager.get_tools_for_use_case(use_case)
            
            # Format messages for LiteLLM
            llm_result = await self.gateway.complete(
                tenant_id=tenant_id,
                use_case=use_case,
                messages=state["messages"],
                system_prompt=system_prompt,
                tools=tools if tools else None
            )
            
            # Update token usage stats
            state["total_tokens_used"] += llm_result.get("prompt_tokens", 0) + llm_result.get("completion_tokens", 0)
            
            tool_calls = llm_result.get("tool_calls")
            content = llm_result.get("content")
            
            # If no tool calls, this is the final response
            if not tool_calls:
                state["final_response"] = content or ""
                break
                
            # Prepare to execute tool calls
            assistant_msg = {
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls
            }
            state["messages"].append(assistant_msg)
            
            # Execute tool calls
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                tool_id = tc.get("id")
                raw_args = tc["function"]["arguments"]
                
                # Check permission matrix
                if not self.permission_manager.is_tool_allowed(use_case, tool_name):
                    observation = f"Error: Tool '{tool_name}' is not allowed for use case '{use_case}'."
                    logger.error(f"Tenant {tenant_id} attempted unauthorized tool call: {tool_name}")
                # Check Redis rate limiting
                elif not self.permission_manager.check_rate_limit(tenant_id, tool_name):
                    observation = f"Error: Rate limit exceeded for tool '{tool_name}'."
                else:
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except Exception as e:
                        args = {"raw_args": raw_args}
                        
                    # Execute
                    observation = await self.executor.execute(tool_name, args, tenant_id)
                    state["tools_called"].append(tool_name)
                
                # Append tool observation
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": observation
                }
                state["messages"].append(tool_msg)
            
            state["iteration_count"] += 1
            
        if state["iteration_count"] >= max_iterations:
            logger.warning(f"Tenant {tenant_id} exceeded maximum iteration limit of {max_iterations}.")
            # Extract last assistant response if available
            last_content = ""
            for msg in reversed(state["messages"]):
                if msg.get("role") == "assistant" and msg.get("content"):
                    last_content = msg["content"]
                    break
            state["final_response"] = last_content or "Reached maximum iteration depth without a final response."
            
        return {
            "final_response": state["final_response"],
            "tools_called": state["tools_called"],
            "iterations": state["iteration_count"],
            "total_tokens_used": state["total_tokens_used"],
            "cost_usd": llm_result.get("cost_usd", 0.0)
        }
