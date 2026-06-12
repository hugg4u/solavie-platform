import asyncio
import logging
import json
from aiokafka import AIOKafkaProducer
from schemas.analytics import ConversationEvent
from core.metrics import ai_core_publisher_failures_total

logger = logging.getLogger(__name__)

class ConversationEventPublisher:
    def __init__(self, kafka_brokers: str):
        self.kafka_brokers = kafka_brokers
        self.producer = None
        self._started = False

    async def start(self) -> None:
        """Starts the Kafka producer connection."""
        if self._started:
            return
        
        try:
            logger.info(f"Starting ConversationEventPublisher on brokers: {self.kafka_brokers}")
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.kafka_brokers,
                key_serializer=lambda k: k.encode("utf-8") if isinstance(k, str) else k,
                value_serializer=lambda v: json.dumps(v).encode("utf-8") if isinstance(v, dict) else v
            )
            await self.producer.start()
            self._started = True
            logger.info("ConversationEventPublisher started successfully.")
        except Exception as e:
            logger.error({
                "action": "publisher_startup_failed",
                "message": f"Failed to start ConversationEventPublisher: {e}",
                "context": {
                    "brokers": self.kafka_brokers
                }
            })
            # Do not raise exception here to ensure application resilience if Kafka is down
            self.producer = None

    async def stop(self) -> None:
        """Stops the Kafka producer connection gracefully."""
        if not self._started or not self.producer:
            return
        
        try:
            logger.info("Stopping ConversationEventPublisher producer...")
            await self.producer.stop()
            self.producer = None
            self._started = False
            logger.info("ConversationEventPublisher stopped successfully.")
        except Exception as e:
            logger.error({
                "action": "publisher_shutdown_failed",
                "message": f"Failed to stop ConversationEventPublisher: {e}"
            })

    def publish(self, event: ConversationEvent) -> None:
        """
        Publishes the conversation completion event in a non-blocking fire-and-forget manner.
        """
        # Run send task in background without blocking response path
        asyncio.create_task(self._send_with_retry(event))

    async def _send_with_retry(self, event: ConversationEvent) -> None:
        topic = "chatbot.conversation.completed"
        
        if not self._started or not self.producer:
            # Try to lazy init if not started
            logger.warning("Producer not started, attempting lazy initialization...")
            await self.start()
            if not self.producer:
                # Log DLQ failure immediately
                self._handle_dlq(event, Exception("Kafka producer is not initialized/started"))
                return

        payload = event.model_dump()
        # Convert datetime and UUID to string serializable values
        payload["event_id"] = str(payload["event_id"])
        payload["timestamp"] = payload["timestamp"].isoformat()

        # Retry config: 3 attempts with exponential backoff (1s, 2s, 4s)
        backoffs = [1.0, 2.0, 4.0]
        last_error = None

        for attempt, delay in enumerate(backoffs, 1):
            try:
                # Key is tenant_id, ensuring messages for the same tenant end up in the same partition
                await self.producer.send_and_wait(
                    topic=topic,
                    key=event.tenant_id,
                    value=payload
                )
                
                logger.info({
                    "action": "conversation_event_published",
                    "tenant_id": event.tenant_id,
                    "message": "Conversation completed event published successfully to Kafka",
                    "context": {
                        "event_id": str(event.event_id),
                        "conversation_id": event.conversation_id,
                        "topic": topic,
                        "attempt": attempt
                    }
                })
                return  # Success, exit loop
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Attempt {attempt} to publish conversation event failed for tenant {event.tenant_id}: {e}. "
                    f"Retrying in {delay}s..."
                )
                if attempt < len(backoffs):
                    await asyncio.sleep(delay)

        # If all retries failed, log DLQ warning and raise metrics
        self._handle_dlq(event, last_error)

    def _handle_dlq(self, event: ConversationEvent, error: Exception) -> None:
        topic = "chatbot.conversation.completed"
        # 1. Log DLQ
        logger.error({
            "action": "publisher_failed_dlq",
            "tenant_id": event.tenant_id,
            "message": "Failed to publish event to Kafka after all retries",
            "context": {
                "event_id": str(event.event_id),
                "conversation_id": event.conversation_id,
                "topic": topic,
                "error_message": str(error)
            }
        })
        # 2. Increment metrics
        try:
            ai_core_publisher_failures_total.labels(
                tenant_id=event.tenant_id,
                topic=topic
            ).inc()
        except Exception as metric_err:
            logger.warning(f"Failed to increment publisher failure metric: {metric_err}")
