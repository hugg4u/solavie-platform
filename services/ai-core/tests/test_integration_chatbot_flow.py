import pytest
import asyncio
import uuid
import json
from unittest.mock import MagicMock, patch
from gateway.router import LLMGateway
from schemas.analytics import ConversationEvent

@pytest.mark.asyncio
async def test_chatbot_flow_first_message_bypass():
    """
    Test that the first user message in a chatbot conversation bypasses Query Rewriting.
    """
    gateway = LLMGateway()
    tenant_id = "test-tenant-123"
    
    # 1 message -> bypass rewrite
    messages = [{"role": "user", "content": "Hello, how can I help?"}]
    
    # Mock routing, acompletion, publisher
    mock_route = {
        "primary_model": "gpt-4o-mini",
        "fallback_model": "gpt-4o-mini",
        "provider": "openai",
        "fallback_provider": "openai",
        "temperature": 0.7,
        "max_tokens": 500,
    }
    
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "Hello! How can I assist you today?"
    mock_resp.choices[0].message.tool_calls = None
    mock_resp.usage.prompt_tokens = 10
    mock_resp.usage.completion_tokens = 10
    mock_resp.cache_hit = False
    
    # Spy on publish method
    published_events = []
    def spy_publish(event):
        published_events.append(event)

    with patch.object(gateway, "get_routing", return_value=mock_route):
        with patch.object(gateway, "get_provider_credentials", return_value={"api_key": "mock-key"}):
            with patch("gateway.router.acompletion", return_value=mock_resp):
                with patch.object(gateway.conversation_publisher, "publish", side_effect=spy_publish):
                    with patch.object(gateway.query_rewriter, "rewrite", wraps=gateway.query_rewriter.rewrite) as spy_rewrite:
                        response = await gateway.complete(
                            tenant_id=tenant_id,
                            use_case="chatbot",
                            messages=messages,
                            publish_event=True
                        )
                        
                        # Verify rewrite was called (but it internal-bypassed and returned the same)
                        spy_rewrite.assert_called_once()
                        
                        # Verify completion response
                        assert response["content"] == "Hello! How can I assist you today?"
                        assert response["query_rewritten"] is False
                        assert response["standalone_query"] == "Hello, how can I help?"
                        
                        # Wait for async task to process publisher call
                        await asyncio.sleep(0.05)
                        
                        # Verify the event published
                        assert len(published_events) == 1
                        event = published_events[0]
                        assert isinstance(event, ConversationEvent)
                        assert event.query_rewritten is False
                        assert event.user_query == "Hello, how can I help?"
                        assert event.standalone_query == "Hello, how can I help?"
                        assert event.chatbot_action == "reply"

@pytest.mark.asyncio
async def test_chatbot_flow_multi_turn_rewrite_and_kb_score_extraction():
    """
    Test multi-turn conversation where Query Rewriting triggers and RAG similarity score
    is successfully extracted from the history messages (mocking KB Search tool output).
    """
    gateway = LLMGateway()
    tenant_id = "test-tenant-123"
    
    # Lịch sử hội thoại: 3 tin nhắn (user -> assistant -> user)
    # Lượt 1: user hỏi về sản phẩm, assistant trả lời và gọi KB tool
    # Lượt 2: user hỏi đại từ "loại đó"
    messages = [
        {"role": "user", "content": "Solavie có pin lithium không?"},
        {"role": "assistant", "content": "Dạ có ạ, Solavie cung cấp pin lithium 48V cho hệ thống solar."},
        {"role": "tool", "name": "knowledge_base_search", "content": json.dumps({
            "max_similarity_score": 0.88,
            "documents": [
                {"title": "Lithium Battery Specs", "similarity_score": 0.88},
                {"title": "FAQ", "similarity_score": 0.72}
            ]
        })},
        {"role": "user", "content": "Loại đó giá bao nhiêu?"}
    ]
    
    mock_route = {
        "primary_model": "gpt-4o-mini",
        "fallback_model": "gpt-4o-mini",
        "provider": "openai",
        "fallback_provider": "openai",
        "temperature": 0.7,
        "max_tokens": 500,
    }
    
    # Mock LLM response for rewriting: "Giá pin lithium của Solavie là bao nhiêu?"
    # Vì QueryRewriter gọi gateway.complete(use_case="summarization"), ta cần mock acompletion tương ứng
    def mock_acompletion(**kwargs):
        # Determine if it's the rewrite call or main chat completion
        prompt_messages = kwargs.get("messages", [])
        is_rewrite_call = any("tối ưu hóa câu truy vấn" in m.get("content", "") for m in prompt_messages)
        
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "Giá pin lithium của Solavie là bao nhiêu?"
        resp.choices[0].message.tool_calls = None
        resp.usage.prompt_tokens = 10
        resp.usage.completion_tokens = 10
        resp.cache_hit = False
        
        if is_rewrite_call:
            resp.choices[0].message.content = "Giá pin lithium của Solavie là bao nhiêu?"
            resp.model_used = "gpt-4o-mini"
        else:
            resp.choices[0].message.content = "Pin lithium 48V của Solavie có giá dao động từ 15 triệu đến 30 triệu tùy dung lượng ạ."
            resp.model_used = "gpt-4o-mini"
        return resp

    published_events = []
    def spy_publish(event):
        published_events.append(event)

    with patch.object(gateway, "get_routing", return_value=mock_route):
        with patch.object(gateway, "get_provider_credentials", return_value={"api_key": "mock-key"}):
            with patch("gateway.router.acompletion", side_effect=mock_acompletion):
                with patch.object(gateway.conversation_publisher, "publish", side_effect=spy_publish):
                    
                    response = await gateway.complete(
                        tenant_id=tenant_id,
                        use_case="chatbot",
                        messages=messages,
                        publish_event=True
                    )
                    
                    # Verify completion response
                    assert response["query_rewritten"] is True
                    assert response["standalone_query"] == "Giá pin lithium của Solavie là bao nhiêu?"
                    assert "15 triệu" in response["content"]
                    
                    # Wait for async task to process publisher call
                    await asyncio.sleep(0.05)
                    
                    # Verify the event published contains correct rewrite flag and KB scores
                    assert len(published_events) == 1
                    event = published_events[0]
                    assert event.query_rewritten is True
                    assert event.user_query == "Loại đó giá bao nhiêu?"
                    assert event.standalone_query == "Giá pin lithium của Solavie là bao nhiêu?"
                    assert event.rag_similarity_score == 0.88
                    assert event.rag_docs_count == 2
                    assert event.chatbot_action == "reply"

@pytest.mark.asyncio
async def test_chatbot_flow_action_tagging():
    """
    Test that chatbot_action is correctly tagged (e.g., handoff, clarify, lead_capture)
    based on tool calls and response content.
    """
    gateway = LLMGateway()
    tenant_id = "test-tenant-123"
    
    mock_route = {
        "primary_model": "gpt-4o-mini",
        "fallback_model": "gpt-4o-mini",
        "provider": "openai",
        "fallback_provider": "openai",
        "temperature": 0.7,
        "max_tokens": 500,
    }
    
    # Case 1: Handoff Action (simulated by tool message containing handoff_to_agent)
    messages_handoff = [
        {"role": "user", "content": "Tôi muốn gặp nhân viên hỗ trợ ngay lập tức."},
        {"role": "tool", "name": "handoff_to_agent", "content": "Khách hàng yêu cầu hỗ trợ trực tiếp do bức xúc."}
    ]
    
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "Dạ, tôi đang chuyển bạn tới nhân viên hỗ trợ. Xin vui lòng chờ trong giây lát."
    mock_resp.choices[0].message.tool_calls = None
    mock_resp.usage.prompt_tokens = 10
    mock_resp.usage.completion_tokens = 10
    mock_resp.cache_hit = False
    
    published_events = []
    with patch.object(gateway, "get_routing", return_value=mock_route):
        with patch.object(gateway, "get_provider_credentials", return_value={"api_key": "mock-key"}):
            with patch("gateway.router.acompletion", return_value=mock_resp):
                with patch.object(gateway.conversation_publisher, "publish", side_effect=published_events.append):
                    await gateway.complete(
                        tenant_id=tenant_id,
                        use_case="chatbot",
                        messages=messages_handoff,
                        publish_event=True
                    )
                    
                    await asyncio.sleep(0.05)
                    assert len(published_events) == 1
                    assert published_events[0].chatbot_action == "handoff"
                    assert published_events[0].handoff_reason == "Khách hàng yêu cầu hỗ trợ trực tiếp do bức xúc."

    # Case 2: Lead Capture Action (simulated by tool message containing create_lead_deal)
    messages_lead = [
        {"role": "user", "content": "Tạo báo giá solar 5kW cho tôi"},
        {"role": "tool", "name": "create_lead_deal", "content": "Lead created successfully in CRM."}
    ]
    
    published_events.clear()
    with patch.object(gateway, "get_routing", return_value=mock_route):
        with patch.object(gateway, "get_provider_credentials", return_value={"api_key": "mock-key"}):
            with patch("gateway.router.acompletion", return_value=mock_resp):
                with patch.object(gateway.conversation_publisher, "publish", side_effect=published_events.append):
                    await gateway.complete(
                        tenant_id=tenant_id,
                        use_case="chatbot",
                        messages=messages_lead,
                        publish_event=True
                    )
                    
                    await asyncio.sleep(0.05)
                    assert len(published_events) == 1
                    assert published_events[0].chatbot_action == "lead_capture"

    # Case 3: Clarification Action (simulated by response containing confirmation keywords)
    messages_clarify = [
        {"role": "user", "content": "Tôi muốn hủy đơn hàng?"}
    ]
    
    mock_resp_clarify = MagicMock()
    mock_resp_clarify.choices = [MagicMock()]
    mock_resp_clarify.choices[0].message.content = "Để hủy đơn hàng, xin vui lòng xác nhận lại số điện thoại đăng ký mua hàng của bạn."
    mock_resp_clarify.choices[0].message.tool_calls = None
    mock_resp_clarify.usage.prompt_tokens = 10
    mock_resp_clarify.usage.completion_tokens = 10
    mock_resp_clarify.cache_hit = False
    
    published_events.clear()
    with patch.object(gateway, "get_routing", return_value=mock_route):
        with patch.object(gateway, "get_provider_credentials", return_value={"api_key": "mock-key"}):
            with patch("gateway.router.acompletion", return_value=mock_resp_clarify):
                with patch.object(gateway.conversation_publisher, "publish", side_effect=published_events.append):
                    await gateway.complete(
                        tenant_id=tenant_id,
                        use_case="chatbot",
                        messages=messages_clarify,
                        publish_event=True
                    )
                    
                    await asyncio.sleep(0.05)
                    assert len(published_events) == 1
                    assert published_events[0].chatbot_action == "clarify"
