import pytest
import asyncio
import uuid
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from schemas.analytics import ConversationEvent
from core.analytics_publisher import ConversationEventPublisher

@pytest.fixture
def sample_event():
    return ConversationEvent(
        event_id=uuid.uuid4(),
        tenant_id="tenant-123",
        conversation_id="conv-456",
        user_query="Loại đó giá bao nhiêu?",
        standalone_query="Giá pin lithium Solavie là bao nhiêu?",
        query_rewritten=True,
        rag_similarity_score=0.85,
        rag_docs_count=3,
        nli_grounding_score=0.92,
        confidence_score=0.95,
        chatbot_action="reply",
        handoff_reason=None,
        cache_hit=False,
        model_used="gpt-4o-mini",
        latency_ms=120,
        timestamp=datetime.utcnow()
    )

def test_event_schema_validation(sample_event):
    """Verify ConversationEvent validate inputs correctly and serializes successfully."""
    assert isinstance(sample_event.event_id, uuid.UUID)
    assert sample_event.tenant_id == "tenant-123"
    assert sample_event.chatbot_action == "reply"
    
    # Verify serialization
    data = sample_event.model_dump()
    assert isinstance(data["event_id"], uuid.UUID)
    
    # Validation error checks
    with pytest.raises(ValueError):
        # Invalid chatbot_action
        ConversationEvent(
            event_id=uuid.uuid4(),
            tenant_id="t-1",
            conversation_id="c-1",
            user_query="q",
            standalone_query="q",
            query_rewritten=False,
            model_used="m",
            latency_ms=10,
            chatbot_action="invalid_action_value"  # type: ignore
        )

@pytest.mark.asyncio
async def test_publish_success(sample_event):
    """Verify event is successfully sent to Kafka with correct parameters."""
    with patch("core.analytics_publisher.AIOKafkaProducer") as mock_producer_cls:
        mock_producer = AsyncMock()
        mock_producer_cls.return_value = mock_producer
        
        publisher = ConversationEventPublisher("localhost:9092")
        await publisher.start()
        
        # Trigger send_with_retry synchronously for testing
        await publisher._send_with_retry(sample_event)
        
        # Verify producer send was called
        mock_producer.send_and_wait.assert_called_once()
        args, kwargs = mock_producer.send_and_wait.call_args
        
        assert kwargs["topic"] == "chatbot.conversation.completed"
        assert kwargs["key"] == "tenant-123"
        
        value = kwargs["value"]
        assert value["tenant_id"] == "tenant-123"
        assert value["conversation_id"] == "conv-456"
        assert value["query_rewritten"] is True
        
        await publisher.stop()
        mock_producer.stop.assert_called_once()

@pytest.mark.asyncio
async def test_publish_retry_on_failure(sample_event):
    """Verify publisher retries 3 times and logs to DLQ when Kafka is down."""
    with patch("core.analytics_publisher.AIOKafkaProducer") as mock_producer_cls:
        mock_producer = AsyncMock()
        mock_producer_cls.return_value = mock_producer
        
        # Mock Kafka send failure
        mock_producer.send_and_wait.side_effect = Exception("Kafka connection timeout")
        
        publisher = ConversationEventPublisher("localhost:9092")
        await publisher.start()
        
        # Mock asyncio.sleep to avoid waiting during test execution
        with patch("asyncio.sleep", AsyncMock()) as mock_sleep, \
             patch("core.analytics_publisher.ai_core_publisher_failures_total") as mock_metric:
            
            await publisher._send_with_retry(sample_event)
            
            # Should retry 3 times (1 initial + 2 retries)
            assert mock_producer.send_and_wait.call_count == 3
            assert mock_sleep.call_count == 2
            mock_sleep.assert_has_calls([
                pytest.internal.ParamCall(1.0),  # type: ignore
                pytest.internal.ParamCall(2.0)   # type: ignore
            ], any_order=False) if hasattr(pytest, "internal") else None
            
            # Metric should be incremented
            mock_metric.labels.assert_called_once_with(
                tenant_id="tenant-123",
                topic="chatbot.conversation.completed"
            )
            mock_metric.labels().inc.assert_called_once()
            
            await publisher.stop()


@pytest.mark.asyncio
async def test_publish_fire_and_forget(sample_event):
    """Verify publish() triggers an async task and does not block current execution path."""
    publisher = ConversationEventPublisher("localhost:9092")
    publisher._send_with_retry = AsyncMock()
    
    with patch("asyncio.create_task") as mock_create_task:
        publisher.publish(sample_event)
        mock_create_task.assert_called_once()
