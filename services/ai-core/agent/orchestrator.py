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
from core.utils import detect_session_language

logger = logging.getLogger("solavie.ai_core.agent.orchestrator")


# ─── Agent State ──────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[List[Dict[str, Any]], operator.add]
    tenant_id: str
    use_case: str
    user_permissions: List[str]
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
    standalone_query: str
    query_rewritten: bool



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
        lang = detect_session_language(messages)
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
            if lang == "vi":
                resp = "Xin lỗi, tôi đã xử lý nhiều bước nhưng chưa tìm được câu trả lời phù hợp."
            else:
                resp = "Sorry, I have processed multiple steps but could not find a suitable answer."
            return {
                "final_response": resp,
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
            if lang == "vi":
                resp = (
                    "Xin lỗi, chủ đề bạn hỏi nằm ngoài phạm vi tư vấn của tôi. "
                    "Tôi chỉ có thể hỗ trợ các vấn đề liên quan đến sản phẩm và dịch vụ của chúng tôi."
                )
            else:
                resp = (
                    "Sorry, the topic you asked about is outside my scope of assistance. "
                    "I can only support queries related to our products and services."
                )
            return {
                "final_response": resp,
                "confidence": 0.0
            }

        # ── LLM Gateway call ──
        llm_result = await self.gateway.complete(
            tenant_id=tenant_id,
            use_case=use_case,
            messages=masked_messages,
            tools=tools if tools else None,
            publish_event=False,
            conversation_id=trace_id
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

        if iteration_count == 0:
            update["standalone_query"] = llm_result.get("standalone_query", last_user_msg)
            update["query_rewritten"] = llm_result.get("query_rewritten", False)


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

                # Retry logic up to 2 times (AC 10.9 retry requirement)
                nli_retry_count = 0
                current_retry_messages = list(masked_messages)
                while nli_score < 0.80 and nli_retry_count < 2:
                    nli_retry_count += 1
                    logger.info(
                        f"NLI validation failed (score: {nli_score}). Retrying generation (attempt {nli_retry_count}/2)...",
                        extra={"tenant_id": tenant_id, "trace_id": trace_id}
                    )
                    
                    current_retry_messages.extend([
                        {"role": "assistant", "content": raw_response},
                        {"role": "user", "content": "⚠️ Your previous response contained statements not grounded in the provided context. Please generate a new response relying strictly ONLY on the provided context/tool documents. Do not add any outside information. Respond in the same language as the user's query."}
                    ])
                    
                    llm_result = await self.gateway.complete(
                        tenant_id=tenant_id,
                        use_case=use_case,
                        messages=current_retry_messages,
                        temperature=0.0,
                        tools=tools if tools else None
                    )
                    
                    p_tok = llm_result.get("prompt_tokens", 0)
                    c_tok = llm_result.get("completion_tokens", 0)
                    update["total_tokens_used"] += p_tok + c_tok
                    update["prompt_tokens"] += p_tok
                    update["completion_tokens"] += c_tok
                    update["cost_usd"] += llm_result.get("cost_usd", 0.0)
                    update["latency_ms"] += llm_result.get("latency_ms", 0)
                    
                    if llm_result.get("tool_calls"):
                        assistant_msg["content"] = llm_result.get("content")
                        assistant_msg["tool_calls"] = llm_result.get("tool_calls")
                        update["model_used"] = llm_result.get("model_used", "routed")
                        update["provider"] = llm_result.get("provider", "openai")
                        break
                        
                    raw_response = llm_result.get("content") or ""
                    nli_score = await self.guardrail.validate_nli_grounding(
                        raw_response,
                        context_docs,
                        tenant_id=tenant_id,
                        use_case=use_case
                    )
                    nli_status = "pass" if nli_score >= 0.80 else "fail"
                    assistant_msg["content"] = raw_response

                if nli_score < 0.80:
                    logger.warning(
                        "NLI grounding below threshold after retries — escalating to human agent",
                        extra={
                            "event": "nli_grounding_fail",
                            "tenant_id": tenant_id,
                            "trace_id": trace_id,
                            "nli_grounding_score": nli_score,
                            "nli_status": nli_status,
                            "agent_iterations": iteration_count
                        }
                    )
                    if lang == "vi":
                        raw_response = (
                            "Tôi không tìm thấy thông tin chính xác trong hệ thống để trả lời câu hỏi của bạn. "
                            "Đang chuyển kết nối sang nhân viên tư vấn con người hỗ trợ ngay..."
                        )
                    else:
                        raw_response = (
                            "I could not find accurate information in the system to answer your question. "
                            "Transferring you to a human support agent..."
                        )
                    assistant_msg["content"] = raw_response

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
        3. RBAC user permission check (Zero-Trust In-Memory check)
        4. Rate limit check (AC 8.4)
        5. Execute tool → return observation
        """
        tenant_id = state["tenant_id"]
        use_case = state["use_case"]
        user_permissions = state.get("user_permissions", [])
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
            request_limit_exceeded = False
            confirmation_required = False
            
            if tool_name == "web_search":
                # Max 3 web_search calls per request (AC 9.4)
                web_search_count = sum(1 for t in recent_tools if t == "web_search")
                if web_search_count >= 3:
                    request_limit_exceeded = True
                elif len(recent_tools) >= 2 and all(t == "web_search" for t in recent_tools[-2:]):
                    consecutive_limit_reached = True
            elif tool_name == "knowledge_base_search":
                if len(recent_tools) >= 3 and all(t == "knowledge_base_search" for t in recent_tools[-3:]):
                    consecutive_limit_reached = True
            elif tool_name in ["create_schedule", "hide_comment", "generate_content"]:
                # Check history to see if we already asked for confirmation and user confirmed (AC 10.1)
                confirmed = False
                asked_for_confirm = False
                for msg in reversed(state["messages"][:-1]):
                    content = msg.get("content") or ""
                    if msg.get("role") == "assistant" and ("Tôi cần bạn xác nhận" in content or "I need your confirmation" in content):
                        asked_for_confirm = True
                        break
                
                if asked_for_confirm:
                    last_user_text = next(
                        (m.get("content", "").lower().strip(" .!?") for m in reversed(state["messages"]) if m.get("role") == "user"),
                        ""
                    )
                    if last_user_text in ["có", "đồng ý", "yes", "confirm", "ok", "xác nhận", "chấp nhận", "co", "dong y", "xac nhan"]:
                        confirmed = True
                
                if not confirmed:
                    confirmation_required = True

            if request_limit_exceeded:
                observation = f"Error: Web search limit reached — maximum 3 web_search calls allowed per request."
                logger.warning(
                    "Web search request limit reached",
                    extra={
                        "event": "web_search_request_limit_reached",
                        "tenant_id": tenant_id,
                        "trace_id": trace_id,
                        "tool_name": tool_name
                    }
                )
            elif consecutive_limit_reached:
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
            elif confirmation_required:
                lang = detect_session_language(state["messages"])
                if lang == "vi":
                    observation = (
                        f"Error: Hành động '{tool_name}' yêu cầu xác nhận từ con người. "
                        f"Vui lòng thông báo cho người dùng: 'Tôi cần bạn xác nhận để thực hiện hành động: {tool_name} (Tham số: {raw_args}). Hãy trả lời \"Đồng ý\" hoặc \"Có\" để thực hiện.'"
                    )
                else:
                    observation = (
                        f"Error: Action '{tool_name}' requires human confirmation. "
                        f"Please notify the user: 'I need your confirmation to perform the action: {tool_name} (Arguments: {raw_args}). Please reply \"Yes\" or \"Confirm\" to proceed.'"
                    )
                logger.warning(
                    "Human confirmation required for destructive tool",
                    extra={
                        "event": "confirmation_required",
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

            # ── RBAC User Permission Check (Zero-Trust In-Memory check) ──
            elif not self._check_rbac_in_memory(user_permissions, tool_name, trace_id):
                observation = f"Error: User does not have permission to call '{tool_name}'."
                logger.warning(
                    "RBAC permission denied",
                    extra={
                        "event": "rbac_denied",
                        "tenant_id": tenant_id,
                        "trace_id": trace_id,
                        "tool_name": tool_name,
                        "user_permissions": user_permissions
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

    def _check_rbac_in_memory(
        self,
        user_permissions: List[str],
        tool_name: str,
        trace_id: str = "unknown"
    ) -> bool:
        """
        Zero-Trust In-Memory RBAC check using Global Permission Spec.
        """
        from api.deps import check_permission
        from tools.registry import TOOL_PERMISSIONS
        
        required_perm = TOOL_PERMISSIONS.get(tool_name)
        if not required_perm:
            return True  # No RBAC restriction for this tool
            
        perms_set = set(user_permissions)
        authorized = check_permission(perms_set, required_perm)
        
        logger.debug(
            "In-memory RBAC check completed",
            extra={
                "event": "rbac_check_in_memory",
                "trace_id": trace_id,
                "tool_name": tool_name,
                "authorized": authorized,
            }
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
        user_permissions: Optional[List[str]] = None,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Runs the full ReAct Agent loop for a given tenant and use case.

        Args:
            tenant_id:        Tenant UUID
            use_case:         Routing use case (chatbot, content_generation, etc.)
            messages:         Chat history as list of dicts
            system_prompt:    Optional system-level instruction override
            user_permissions: Permissions for Zero-Trust authorization check
            trace_id:         Optional distributed trace ID for observability
        """
        import uuid as _uuid
        if not trace_id:
            trace_id = str(_uuid.uuid4())

        # Build initial state
        initial_state: AgentState = {
            "messages": messages.copy(),
            "tenant_id": tenant_id,
            "use_case": use_case,
            "user_permissions": user_permissions or [],
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
            "provider": "unknown",
            "pii_map": {},
            "trace_id": trace_id,
            "nli_grounding_score": 1.0,
            "nli_status": "skip",
            "standalone_query": "",
            "query_rewritten": False
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
                "user_permissions": user_permissions,
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

            # Publish Conversation Event for chatbot usecase
            rag_sim = 0.0
            if use_case == "chatbot":
                original_user_query = ""
                for msg in messages:
                    if msg.get("role") == "user":
                        original_user_query = msg.get("content", "")
                        break
                
                rag_count = 0
                for msg in final_state.get("messages", []):
                    if msg.get("role") == "tool" and msg.get("name") == "knowledge_base_search":
                        content_str = msg.get("content", "")
                        if content_str:
                            try:
                                data = json.loads(content_str)
                                if isinstance(data, dict):
                                    if "max_similarity_score" in data:
                                        rag_sim = max(rag_sim, float(data["max_similarity_score"]))
                                    docs = data.get("documents", [])
                                    if isinstance(docs, list):
                                        rag_count = max(rag_count, len(docs))
                                        for doc in docs:
                                            if isinstance(doc, dict) and "similarity_score" in doc:
                                                rag_sim = max(rag_sim, float(doc["similarity_score"]))
                            except Exception:
                                if "matching documents" in content_str or "brochure" in content_str:
                                    rag_sim = max(rag_sim, 0.75)
                                    rag_count = max(rag_count, 2)

                tools_called = final_state.get("tools_called", [])
                chatbot_action = "reply"
                handoff_reason = None
                if "handoff_to_agent" in tools_called:
                    chatbot_action = "handoff"
                    for msg in final_state.get("messages", []):
                        if msg.get("role") == "tool" and msg.get("name") == "handoff_to_agent":
                            handoff_reason = msg.get("content", "")
                elif "create_lead_deal" in tools_called:
                    chatbot_action = "lead_capture"
                elif final_response and ("xác nhận" in final_response.lower() or "confirm" in final_response.lower()):
                    chatbot_action = "clarify"

                await self.gateway.publish_conversation_event(
                    tenant_id=tenant_id,
                    conversation_id=trace_id,
                    user_query=original_user_query,
                    standalone_query=final_state.get("standalone_query") or original_user_query,
                    query_rewritten=final_state.get("query_rewritten", False),
                    rag_similarity_score=rag_sim,
                    rag_docs_count=rag_count,
                    nli_grounding_score=final_state.get("nli_grounding_score", 1.0),
                    confidence_score=final_state.get("confidence", 1.0),
                    chatbot_action=chatbot_action,
                    handoff_reason=handoff_reason,
                    cache_hit=final_state.get("cache_hit", False),
                    model_used=final_state.get("model_used", "routed"),
                    latency_ms=final_state.get("latency_ms", 0)
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
                "trace_id": trace_id,
                "max_similarity_score": rag_sim
            }



        except Exception as e:
            logger.error(
                f"Agent graph execution failed: {e}",
                extra={"event": "agent_error", "tenant_id": tenant_id, "trace_id": trace_id},
                exc_info=True
            )
            raise e
