import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from gateway.router import LLMGateway, MODEL_ROUTING
from tools.registry import ToolPermissionManager
from tools.executor import ToolExecutor
from agent.orchestrator import AgentOrchestrator

# --- Router Tests ---
@pytest.mark.asyncio
async def test_history_compression():
    gateway = LLMGateway()
    messages = [
        {"role": "user", "content": "hello 1"},
        {"role": "assistant", "content": "hi 1"},
        {"role": "user", "content": "hello 2"},
        {"role": "assistant", "content": "hi 2"},
        {"role": "user", "content": "hello 3"},
        {"role": "assistant", "content": "hi 3"},
        {"role": "user", "content": "hello 4"}
    ]
    
    # We keep recent 5 messages
    compressed = gateway.compress_history(messages, keep_recent=5)
    assert len(compressed) == 6  # 1 summary message + 5 recent messages
    assert compressed[0]["role"] == "system"
    assert "Background summary" in compressed[0]["content"]
    assert compressed[1]["content"] == "hello 2"

@pytest.mark.asyncio
async def test_context_optimization():
    gateway = LLMGateway()
    long_content = "a" * 5000
    messages = [
        {"role": "context", "content": long_content},
        {"role": "user", "content": "hi"}
    ]
    optimized = gateway.optimize_context(messages, max_context_chars=1000)
    assert len(optimized) == 2
    assert "[TRUNCATED FOR TOKEN OPTIMIZATION]" in optimized[0]["content"]
    assert len(optimized[0]["content"]) < 2000

# --- Permission Manager Tests ---
def test_tool_permissions():
    pm = ToolPermissionManager()
    
    # Chatbot allowed tools
    chatbot_tools = pm.get_tools_for_use_case("chatbot")
    tool_names = [t["function"]["name"] for t in chatbot_tools]
    assert "knowledge_base_search" in tool_names
    assert "send_message" in tool_names
    assert "web_search" not in tool_names
    
    # Verification matrix
    assert pm.is_tool_allowed("chatbot", "knowledge_base_search") is True
    assert pm.is_tool_allowed("chatbot", "web_search") is False
    
    # Content generation allowed tools
    content_tools = pm.get_tools_for_use_case("content_generation")
    content_names = [t["function"]["name"] for t in content_tools]
    assert "web_search" in content_names

# --- Tool Executor Tests ---
@pytest.mark.asyncio
async def test_tool_executor_tavily_mock():
    executor = ToolExecutor()
    # Mocking external HTTP request to Tavily search and patching API key to non-empty
    from core.config import settings
    with patch.object(settings, 'TAVILY_API_KEY', 'test-key'):
        with patch.object(executor.client, 'post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "answer": "Test answer about solar panels",
                "results": []
            }
            mock_post.return_value = mock_response
            
            result = await executor._execute_web_search("solar panels")
            assert "Test answer" in result

# --- ReAct Orchestrator Tests ---
@pytest.mark.asyncio
async def test_react_agent_loop_limit():
    orchestrator = AgentOrchestrator()
    
    # Mock LLM gateway to always return a tool call to simulate infinite loop
    mock_tool_call = {
        "id": "call-123",
        "type": "function",
        "function": {
            "name": "knowledge_base_search",
            "arguments": '{"query": "infinite loop test"}'
        }
    }
    
    mock_complete = AsyncMock(return_value={
        "content": "Thinking...",
        "tool_calls": [mock_tool_call],
        "model_used": "gpt-4o-mini",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "cost_usd": 0.0001
    })
    
    with patch.object(orchestrator.gateway, 'complete', mock_complete):
        # Patch registry to always allow tool call and mock executor
        with patch.object(orchestrator.permission_manager, 'is_tool_allowed', return_value=True):
            with patch.object(orchestrator.executor, 'execute', return_value="Here is knowledge base info"):
                # Run the agent
                result = await orchestrator.run(
                    tenant_id="test-tenant",
                    use_case="chatbot",
                    messages=[{"role": "user", "content": "infinite loop check"}]
                )
                
                # Verify loop protection: iterations must be limited to 5
                assert result["iterations"] == 5
                assert len(result["tools_called"]) == 5
