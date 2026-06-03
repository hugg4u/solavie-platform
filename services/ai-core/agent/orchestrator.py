import json
import logging
from typing import TypedDict, List, Dict, Any, Annotated
import operator
from langgraph.graph import StateGraph, END

from gateway.router import LLMGateway
from tools.registry import ToolPermissionManager
from tools.executor import ToolExecutor

logger = logging.getLogger(__name__)

# State structure for the Agent
class AgentState(TypedDict):
    messages: Annotated[List[Dict[str, Any]], operator.add]
    tenant_id: str
    use_case: str
    tools_called: Annotated[List[str], operator.add]
    iteration_count: int
    final_response: str
    confidence: float
    total_tokens_used: int
    cost_usd: float
    model_used: str
    provider: str


class AgentOrchestrator:
    def __init__(self):
        self.gateway = LLMGateway()
        self.permission_manager = ToolPermissionManager()
        self.executor = ToolExecutor()
        self.graph = self._build_graph()

    def _build_graph(self):
        """Builds the LangGraph StateGraph representing the ReAct Loop."""
        workflow = StateGraph(AgentState)
        
        # Add Nodes
        workflow.add_node("reason", self._reason_node)
        workflow.add_node("execute_tools", self._execute_tools_node)
        
        # Set Entry Point
        workflow.set_entry_point("reason")
        
        # Add Conditional Edge from reason
        workflow.add_conditional_edges(
            "reason",
            self._should_continue_edge,
            {
                "execute_tools": "execute_tools",
                "end": END
            }
        )
        
        # Add Normal Edge from execute_tools back to reason
        workflow.add_edge("execute_tools", "reason")
        
        return workflow.compile()

    async def _reason_node(self, state: AgentState) -> Dict[str, Any]:
        """Reason Node: Calls the LLM to decide whether to call tools or finish."""
        tenant_id = state["tenant_id"]
        use_case = state["use_case"]
        messages = state["messages"]
        iteration_count = state["iteration_count"]
        
        # Check iteration safety limits
        if iteration_count >= 5:
            logger.warning(f"Tenant {tenant_id} hit maximum iteration limit of 5.")
            return {
                "final_response": "Reached maximum iteration depth without a final response.",
                "confidence": 0.0
            }
            
        # Get active tools permitted for this usecase
        tools = self.permission_manager.get_tools_for_use_case(use_case)
        
        # Run Unified LLM API Gateway Call
        llm_result = await self.gateway.complete(
            tenant_id=tenant_id,
            use_case=use_case,
            messages=messages,
            tools=tools if tools else None
        )
        
        tokens_added = llm_result.get("prompt_tokens", 0) + llm_result.get("completion_tokens", 0)
        cost_added = llm_result.get("cost_usd", 0.0)
        
        assistant_msg = {
            "role": "assistant",
            "content": llm_result.get("content"),
            "tool_calls": llm_result.get("tool_calls")
        }
        
        # Determine output state update
        update = {
            "messages": [assistant_msg],
            "total_tokens_used": state["total_tokens_used"] + tokens_added,
            "cost_usd": state["cost_usd"] + cost_added,
            "model_used": llm_result.get("model_used", "routed"),
            "provider": llm_result.get("provider", "openai")
        }
        
        tool_calls = llm_result.get("tool_calls")
        if not tool_calls:
            update["final_response"] = llm_result.get("content") or ""
            update["confidence"] = 1.0 if not llm_result.get("is_fallback") else 0.7
            
        return update

    async def _execute_tools_node(self, state: AgentState) -> Dict[str, Any]:
        """Execute Tools Node: Runs tool calls selected by LLM and returns observations."""
        tenant_id = state["tenant_id"]
        use_case = state["use_case"]
        last_message = state["messages"][-1]
        tool_calls = last_message.get("tool_calls") or []
        
        tool_messages = []
        new_tools_called = []
        
        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            tool_id = tc.get("id")
            raw_args = tc["function"]["arguments"]
            
            # Anti-loop guardrail check
            # Cấm gọi liên tiếp quá 2 lần web_search hoặc 3 lần knowledge_base_search
            consecutive_limit_reached = False
            recent_tools = state["tools_called"] + new_tools_called
            if tool_name == "web_search":
                if len(recent_tools) >= 2 and all(t == "web_search" for t in recent_tools[-2:]):
                    consecutive_limit_reached = True
            elif tool_name == "knowledge_base_search":
                if len(recent_tools) >= 3 and all(t == "knowledge_base_search" for t in recent_tools[-3:]):
                    consecutive_limit_reached = True
            
            if consecutive_limit_reached:
                observation = f"Error: Too many consecutive calls to tool '{tool_name}' (anti-loop protection)."
                logger.warning(f"Tenant {tenant_id} anti-loop triggered for tool: {tool_name}")
                
            # Permission check
            elif not self.permission_manager.is_tool_allowed(use_case, tool_name):
                observation = f"Error: Tool '{tool_name}' is not allowed for use case '{use_case}'."
                logger.error(f"Tenant {tenant_id} attempted unauthorized tool: {tool_name}")
                
            # Redis Rate Limit check
            elif not await self.permission_manager.check_rate_limit(tenant_id, tool_name):
                observation = f"Error: Rate limit exceeded for tool '{tool_name}'."
                
            else:
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {"raw_args": raw_args}
                
                # Execute tool
                observation = await self.executor.execute(tool_name, args, tenant_id)
                new_tools_called.append(tool_name)
            
            tool_msg = {
                "role": "tool",
                "tool_call_id": tool_id,
                "name": tool_name,
                "content": observation
            }
            tool_messages.append(tool_msg)
            
        return {
            "messages": tool_messages,
            "tools_called": new_tools_called,
            "iteration_count": state["iteration_count"] + 1
        }

    def _should_continue_edge(self, state: AgentState) -> str:
        """Determines if the agent graph loop should proceed to tool execution or terminate."""
        # Check total token limit guardrail
        if state["total_tokens_used"] > 10000:
            logger.warning(f"Tenant {state['tenant_id']} exceeded maximum token limit of 10000.")
            return "end"
            
        last_message = state["messages"][-1]
        tool_calls = last_message.get("tool_calls")
        
        if tool_calls and state["iteration_count"] < 5:
            return "execute_tools"
        return "end"

    async def run(
        self,
        tenant_id: str,
        use_case: str,
        messages: List[Dict[str, Any]],
        system_prompt: str | None = None
    ) -> Dict[str, Any]:
        """Runs the ReAct Agent platform graph loop for the given tenant and use case."""
        # Initialize state
        initial_state: AgentState = {
            "messages": messages.copy(),
            "tenant_id": tenant_id,
            "use_case": use_case,
            "tools_called": [],
            "iteration_count": 0,
            "final_response": "",
            "confidence": 1.0,
            "total_tokens_used": 0,
            "cost_usd": 0.0,
            "model_used": "routed",
            "provider": "openai"
        }
        
        # Inject system prompt if present
        if system_prompt:
            initial_state["messages"].insert(0, {"role": "system", "content": system_prompt})
            
        try:
            # Execute StateGraph
            final_state = await self.graph.ainvoke(initial_state)
            
            # Extract final response from State
            final_response = final_state.get("final_response", "")
            if not final_response:
                # Fallback to extract last assistant message if final_response was not populated
                for msg in reversed(final_state.get("messages", [])):
                    if msg.get("role") == "assistant" and msg.get("content"):
                        final_response = msg["content"]
                        break
            
            return {
                "final_response": final_response,
                "tools_called": final_state.get("tools_called", []),
                "iterations": final_state.get("iteration_count", 0),
                "total_tokens_used": final_state.get("total_tokens_used", 0),
                "cost_usd": final_state.get("cost_usd", 0.0),
                "confidence": final_state.get("confidence", 1.0),
                "model_used": final_state.get("model_used", "routed"),
                "provider": final_state.get("provider", "openai")
            }
        except Exception as e:
            logger.error(f"Error running Agent Graph loop: {e}")
            raise e
