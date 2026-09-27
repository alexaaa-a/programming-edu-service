import json
import logging

from aiokafka import AIOKafkaProducer

from submission_service.app.config import Settings


class SubmissionEventProducer:
    def __init__(self, settings: Settings, logger: logging.Logger) -> None:
        self._settings = settings
        self._logger = logger
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.kafka_settings.bootstrap_servers.split(","),
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await self._producer.start()
        self._logger.info("Kafka submission producer started")

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
            self._logger.info("Kafka submission producer stopped")

    async def health(self) -> bool:
        probe = AIOKafkaProducer(
            bootstrap_servers=self._settings.kafka_settings.bootstrap_servers.split(","),
            value_serializer=lambda v: v,
        )
        try:
            await probe.start()
            return True
        except Exception:
            return False
        finally:
            try:
                await probe.stop()
            except Exception:
                pass

    async def produce_submission_created(
            self,
            submission_id: int,
            task_id: int,
            user_id: int,
            code: str,
            task_description: str,
            attempt: int = 1,
            previous_feedback: str | None = None,
    ) -> None:
        if not self._producer:
            raise RuntimeError("Kafka producer not started")
        payload = {
            "submission_id": submission_id,
            "task_id": task_id,
            "user_id": user_id,
            "code": code,
            "task_description": task_description,
            "attempt": attempt,
            "previous_feedback": previous_feedback,
        }
        topic = self._settings.kafka_settings.topic_submission_created
        try:
            await self._producer.send_and_wait(topic, value=payload)
        except Exception:
            self._logger.exception("Failed to produce submission.created event")
            raise
