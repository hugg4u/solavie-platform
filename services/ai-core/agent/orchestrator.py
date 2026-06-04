"""
AI-CORE Agent Orchestrator — LangGraph ReAct Loop

Implements:
  - AC 7.1-7.5: ReAct Agent Loop (Reason → Act → Observe → Repeat)
  - AC 8.3b:    Dynamic RBAC enforcement from Keycloak Redis cache (< 50ms)
  - AC 10.1-10.5: Agent Safety Guardrails (iterations, tokens, tenant isolation)
  - AC 10.6-10.10: ContentGuardrail integration (PII, topics, NLI, moderation)
  - Task 12:    Structured logging (pii_masked_keys, nli_grounding_score, nli_status, agent_iterations)
  - Task 12:    Prometheus metrics (agent_iterations, token_budget_exceeded)
"""

import json
import logging
import time
from typing import TypedDict, List, Dict, Any, Annotated, Optional
import operator
from langgraph.graph import StateGraph, END

from gateway.router import LLMGateway
from gateway.guardrails import ContentGuardrail
from tools.registry import ToolPermissionManager
from tools.executor import ToolExecutor
from core.metrics import (
    ai_core_agent_iterations,
    ai_core_token_budget_exceeded_total,
)

logger = logging.getLogger("solavie.ai_core.agent.orchestrator")


# ─── Agent State ──────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[List[Dict[str, Any]], operator.add]
    tenant_id: str
    use_case: str
    user_role: str
    tools_called: Annotated[List[str], operator.add]
    iteration_count: int
    final_response: str
    confidence: float
    total_tokens_used: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    cache_hit: bool
    cost_usd: float
    model_used: str
    provider: str
    pii_map: Dict[str, str]
    # Task 12 tracing context
    trace_id: str
    nli_grounding_score: float
    nli_status: str


class AgentOrchestrator:
    """
    LangGraph ReAct Agent Orchestrator.

    Graph flow:
    ┌─────────────┐     tool_calls?    ┌────────────────┐
    │  reason     │ ──── yes ────────► │  execute_tools │
    │  (LLM call) │ ◄─── loop ─────── │  (MCP calls)   │
    └──────┬──────┘                    └────────────────┘
           │ no tool_calls / safety limit
           ▼
          END
    """

    def __init__(self):
        self.gateway = LLMGateway()
        self.guardrail = ContentGuardrail()
        self.permission_manager = ToolPermissionManager()
        self.executor = ToolExecutor()
        self.graph = self._build_graph()

    def _build_graph(self):
        """Builds the LangGraph StateGraph representing the ReAct Loop."""
        workflow = StateGraph(AgentState)

        workflow.add_node("reason", self._reason_node)
        workflow.add_node("execute_tools", self._execute_tools_node)

        workflow.set_entry_point("reason")

        workflow.add_conditional_edges(
            "reason",
            self._should_continue_edge,
            {
                "execute_tools": "execute_tools",
                "end": END
            }
        )

        workflow.add_edge("execute_tools", "reason")

        return workflow.compile()

    async def _reason_node(self, state: AgentState) -> Dict[str, Any]:
        """
        Reason Node:
        1. Apply Input Guardrail (PII masking, topic check)
        2. Call LLM via Gateway
        3. On final response: NLI grounding check + Output Moderation + PII restore
        """
        tenant_id = state["tenant_id"]
        use_case = state["use_case"]
        messages = state["messages"]
        iteration_count = state["iteration_count"]
        trace_id = state.get("trace_id", "unknown")

        # ── Safety: Max iteration limit (AC 7.2) ──
        if iteration_count >= 5:
            logger.warning(
                "Max iteration limit reached",
                extra={
                    "event": "max_iterations_reached",
                    "tenant_id": tenant_id,
                    "trace_id": trace_id,
                    "iteration_count": iteration_count
                }
            )
            return {
                "final_response": "Xin lỗi, tôi đã xử lý nhiều bước nhưng chưa tìm được câu trả lời phù hợp.",
                "confidence": 0.0
            }

        # ── Get permitted tools for this use case ──
        tools = self.permission_manager.get_tools_for_use_case(use_case)

        # ── Input Guardrail: PII Masking (AC 10.7) ──
        pii_map = state["pii_map"]
        masked_messages = await self.guardrail.process_input(
            messages, pii_map, tenant_id=tenant_id
        )

        # ── Input Guardrail: Topic check on last user message (AC 10.6) ──
        last_user_msg = next(
            (m.get("content", "") for m in reversed(masked_messages) if m.get("role") == "user"),
            ""
        )
        if not self.guardrail.check_topic_guardrail(last_user_msg, tenant_id=tenant_id):
            logger.info(
                "Request blocked by topic guardrail",
                extra={"event": "topic_blocked", "tenant_id": tenant_id, "trace_id": trace_id}
            )
            return {
                "final_response": (
                    "Xin lỗi, chủ đề bạn hỏi nằm ngoài phạm vi tư vấn của tôi. "
                    "Tôi chỉ có thể hỗ trợ các vấn đề liên quan đến sản phẩm và dịch vụ của chúng tôi."
                ),
                "confidence": 0.0
            }

        # ── LLM Gateway call ──
        llm_result = await self.gateway.complete(
            tenant_id=tenant_id,
            use_case=use_case,
            messages=masked_messages,
            tools=tools if tools else None
        )

        prompt_tokens_added = llm_result.get("prompt_tokens", 0)
        completion_tokens_added = llm_result.get("completion_tokens", 0)
        tokens_added = prompt_tokens_added + completion_tokens_added
        cost_added = llm_result.get("cost_usd", 0.0)
        latency_added = llm_result.get("latency_ms", 0)
        cache_hit_val = llm_result.get("cache_hit", False)

        assistant_msg = {
            "role": "assistant",
            "content": llm_result.get("content"),
            "tool_calls": llm_result.get("tool_calls")
        }

        update = {
            "messages": [assistant_msg],
            "total_tokens_used": state["total_tokens_used"] + tokens_added,
            "prompt_tokens": state.get("prompt_tokens", 0) + prompt_tokens_added,
            "completion_tokens": state.get("completion_tokens", 0) + completion_tokens_added,
            "latency_ms": state.get("latency_ms", 0) + latency_added,
            "cache_hit": cache_hit_val,
            "cost_usd": state["cost_usd"] + cost_added,
            "model_used": llm_result.get("model_used", "routed"),
            "provider": llm_result.get("provider", "openai")
        }

        # ── If no tool calls: finalize response ──
        tool_calls = llm_result.get("tool_calls")
        if not tool_calls:
            raw_response = llm_result.get("content") or ""

            # NLI Grounding Validator (AC 10.9) — for chatbot use case
            nli_score = 1.0
            nli_status = "skip"

            if use_case == "chatbot":
                context_docs = [
                    m.get("content", "")
                    for m in messages
                    if m.get("role") in ["tool", "context"] and m.get("content")
                ]

                nli_score = await self.guardrail.validate_nli_grounding(
                    raw_response,
                    context_docs,
                    tenant_id=tenant_id,
                    use_case=use_case
                )
                nli_status = "pass" if nli_score >= 0.80 else "fail"

                if nli_score < 0.80:
                    logger.warning(
                        "NLI grounding below threshold — escalating to human agent",
                        extra={
                            "event": "nli_grounding_fail",
                            "tenant_id": tenant_id,
                            "trace_id": trace_id,
                            "nli_grounding_score": nli_score,
                            "nli_status": nli_status,
                            "agent_iterations": iteration_count
                        }
                    )
                    raw_response = (
                        "Tôi không tìm thấy thông tin chính xác trong hệ thống để trả lời câu hỏi của bạn. "
                        "Đang chuyển kết nối sang nhân viên tư vấn con người hỗ trợ ngay..."
                    )

            # Output Moderation + PII Restore (AC 10.10 + AC 10.7)
            final_response = await self.guardrail.process_output(
                raw_response,
                pii_map,
                tenant_id=tenant_id
            )

            # Task 12: Structured log for final response
            logger.info(
                "Agent final response generated",
                extra={
                    "event": "agent_final_response",
                    "tenant_id": tenant_id,
                    "trace_id": trace_id,
                    "use_case": use_case,
                    "pii_masked_keys": list(pii_map.keys()),
                    "nli_grounding_score": round(nli_score, 4),
                    "nli_status": nli_status,
                    "agent_iterations": iteration_count,
                    "total_tokens_used": state["total_tokens_used"] + tokens_added,
                    "cost_usd": round(state["cost_usd"] + cost_added, 6),
                    "model_used": llm_result.get("model_used", "routed"),
                    "is_fallback": llm_result.get("is_fallback", False)
                }
            )

            update["final_response"] = final_response
            update["confidence"] = 1.0 if not llm_result.get("is_fallback") else 0.7
            update["nli_grounding_score"] = nli_score
            update["nli_status"] = nli_status

        return update

    async def _execute_tools_node(self, state: AgentState) -> Dict[str, Any]:
        """
        Execute Tools Node:
        1. Anti-loop check (AC 10.2)
        2. Use-case permission check (AC 8.3)
        3. RBAC user permission check (AC 8.3b) — Keycloak Redis cache < 50ms
        4. Rate limit check (AC 8.4)
        5. Execute tool → return observation
        """
        tenant_id = state["tenant_id"]
        use_case = state["use_case"]
        user_role = state.get("user_role", "visitor")
        trace_id = state.get("trace_id", "unknown")
        last_message = state["messages"][-1]
        tool_calls = last_message.get("tool_calls") or []

        tool_messages = []
        new_tools_called = []

        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            tool_id = tc.get("id")
            raw_args = tc["function"]["arguments"]

            # ── Anti-loop guardrail (AC 10.2) ──
            recent_tools = state["tools_called"] + new_tools_called
            consecutive_limit_reached = False
            if tool_name == "web_search":
                if len(recent_tools) >= 2 and all(t == "web_search" for t in recent_tools[-2:]):
                    consecutive_limit_reached = True
            elif tool_name == "knowledge_base_search":
                if len(recent_tools) >= 3 and all(t == "knowledge_base_search" for t in recent_tools[-3:]):
                    consecutive_limit_reached = True

            if consecutive_limit_reached:
                observation = f"Error: Anti-loop protection triggered — too many consecutive calls to '{tool_name}'."
                logger.warning(
                    "Anti-loop triggered",
                    extra={
                        "event": "anti_loop_triggered",
                        "tenant_id": tenant_id,
                        "trace_id": trace_id,
                        "tool_name": tool_name
                    }
                )

            # ── Use-case permission check (AC 8.3) ──
            elif not self.permission_manager.is_tool_allowed(use_case, tool_name):
                observation = f"Error: Tool '{tool_name}' is not authorized for use case '{use_case}'."
                logger.error(
                    "Unauthorized tool call blocked",
                    extra={
                        "event": "tool_unauthorized",
                        "tenant_id": tenant_id,
                        "trace_id": trace_id,
                        "tool_name": tool_name,
                        "use_case": use_case
                    }
                )

            # ── RBAC User Permission Check (AC 8.3b) — Keycloak Redis < 50ms ──
            elif not await self._check_rbac(tenant_id, user_role, tool_name, trace_id):
                observation = f"Error: User role '{user_role}' does not have permission to call '{tool_name}'."
                logger.warning(
                    "RBAC permission denied",
                    extra={
                        "event": "rbac_denied",
                        "tenant_id": tenant_id,
                        "trace_id": trace_id,
                        "tool_name": tool_name,
                        "user_role": user_role
                    }
                )

            # ── Rate limit check (AC 8.4) ──
            elif not await self.permission_manager.check_rate_limit(tenant_id, tool_name):
                observation = f"Error: Rate limit exceeded for tool '{tool_name}'. Please try again later."
                logger.warning(
                    "Tool rate limit exceeded",
                    extra={
                        "event": "rate_limit_exceeded",
                        "tenant_id": tenant_id,
                        "trace_id": trace_id,
                        "tool_name": tool_name
                    }
                )

            else:
                # ── Execute tool ──
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {"raw_args": raw_args}

                logger.info(
                    "Executing tool call",
                    extra={
                        "event": "tool_execute",
                        "tenant_id": tenant_id,
                        "trace_id": trace_id,
                        "tool_name": tool_name,
                        "args_preview": str(args)[:100]
                    }
                )

                observation = await self.executor.execute(tool_name, args, tenant_id)
                new_tools_called.append(tool_name)

            tool_messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "name": tool_name,
                "content": str(observation) if observation else "No result"
            })

        return {
            "messages": tool_messages,
            "tools_called": new_tools_called,
            "iteration_count": state["iteration_count"] + 1
        }

    async def _check_rbac(
        self,
        tenant_id: str,
        user_role: str,
        tool_name: str,
        trace_id: str = "unknown"
    ) -> bool:
        """
        AC 8.3b: Dynamic RBAC check from Keycloak Redis cache.
        Key: {tenant_id}:permissions:{user_role}
        Target latency: < 50ms
        """
        t0 = time.perf_counter()
        authorized = await self.permission_manager.is_user_authorized(
            tenant_id, user_role, tool_name
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        logger.debug(
            "RBAC check completed",
            extra={
                "event": "rbac_check",
                "tenant_id": tenant_id,
                "trace_id": trace_id,
                "tool_name": tool_name,
                "user_role": user_role,
                "authorized": authorized,
                "latency_ms": round(elapsed_ms, 2)
            }
        )

        if elapsed_ms > 50:
            logger.warning(
                f"RBAC check exceeded 50ms target: {elapsed_ms:.2f}ms",
                extra={"event": "rbac_latency_exceeded", "tenant_id": tenant_id}
            )

        return authorized

    def _should_continue_edge(self, state: AgentState) -> str:
        """Determines whether to proceed to tool execution or terminate the ReAct loop."""
        # Token budget safety limit (AC 10.4)
        if state["total_tokens_used"] > 10000:
            logger.warning(
                "Session token budget exceeded",
                extra={
                    "event": "token_budget_exceeded",
                    "tenant_id": state["tenant_id"],
                    "total_tokens_used": state["total_tokens_used"]
                }
            )
            ai_core_token_budget_exceeded_total.labels(
                tenant_id=state["tenant_id"]
            ).inc()
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
        system_prompt: Optional[str] = None,
        user_role: str = "visitor",
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Runs the full ReAct Agent loop for a given tenant and use case.

        Args:
            tenant_id:     Tenant UUID
            use_case:      Routing use case (chatbot, content_generation, etc.)
            messages:      Chat history as list of dicts
            system_prompt: Optional system-level instruction override
            user_role:     Keycloak user role for RBAC (AC 8.3b)
            trace_id:      Optional distributed trace ID for observability
        """
        import uuid as _uuid
        if not trace_id:
            trace_id = str(_uuid.uuid4())

        # Build initial state
        initial_state: AgentState = {
            "messages": messages.copy(),
            "tenant_id": tenant_id,
            "use_case": use_case,
            "user_role": user_role,
            "tools_called": [],
            "iteration_count": 0,
            "final_response": "",
            "confidence": 1.0,
            "total_tokens_used": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_ms": 0,
            "cache_hit": False,
            "cost_usd": 0.0,
            "model_used": "routed",
            "provider": "openai",
            "pii_map": {},
            "trace_id": trace_id,
            "nli_grounding_score": 1.0,
            "nli_status": "skip"
        }

        # Inject system prompt
        if system_prompt:
            initial_state["messages"].insert(0, {"role": "system", "content": system_prompt})

        logger.info(
            "Agent session started",
            extra={
                "event": "agent_start",
                "tenant_id": tenant_id,
                "trace_id": trace_id,
                "use_case": use_case,
                "user_role": user_role,
                "message_count": len(messages)
            }
        )

        try:
            final_state = await self.graph.ainvoke(initial_state)

            # Extract final response
            final_response = final_state.get("final_response", "")
            if not final_response:
                for msg in reversed(final_state.get("messages", [])):
                    if msg.get("role") == "assistant" and msg.get("content"):
                        final_response = msg["content"]
                        break

            total_iterations = final_state.get("iteration_count", 0)

            # Emit agent iterations Prometheus metric (Task 12)
            ai_core_agent_iterations.labels(
                tenant_id=tenant_id,
                use_case=use_case
            ).observe(total_iterations)

            logger.info(
                "Agent session completed",
                extra={
                    "event": "agent_complete",
                    "tenant_id": tenant_id,
                    "trace_id": trace_id,
                    "use_case": use_case,
                    "agent_iterations": total_iterations,
                    "pii_masked_keys": list(final_state.get("pii_map", {}).keys()),
                    "nli_grounding_score": final_state.get("nli_grounding_score", 1.0),
                    "nli_status": final_state.get("nli_status", "skip"),
                    "total_tokens_used": final_state.get("total_tokens_used", 0),
                    "cost_usd": round(final_state.get("cost_usd", 0.0), 6),
                    "model_used": final_state.get("model_used", "routed"),
                    "tools_called": final_state.get("tools_called", [])
                }
            )

            return {
                "final_response": final_response,
                "tools_called": final_state.get("tools_called", []),
                "iterations": total_iterations,
                "total_tokens_used": final_state.get("total_tokens_used", 0),
                "prompt_tokens": final_state.get("prompt_tokens", 0),
                "completion_tokens": final_state.get("completion_tokens", 0),
                "latency_ms": final_state.get("latency_ms", 0),
                "cache_hit": final_state.get("cache_hit", False),
                "cost_usd": final_state.get("cost_usd", 0.0),
                "confidence": final_state.get("confidence", 1.0),
                "model_used": final_state.get("model_used", "routed"),
                "provider": final_state.get("provider", "openai"),
                "nli_grounding_score": final_state.get("nli_grounding_score", 1.0),
                "nli_status": final_state.get("nli_status", "skip"),
                "trace_id": trace_id
            }

        except Exception as e:
            logger.error(
                f"Agent graph execution failed: {e}",
                extra={"event": "agent_error", "tenant_id": tenant_id, "trace_id": trace_id},
                exc_info=True
            )
            raise e
