import json
import logging

from aiokafka import AIOKafkaProducer

from task_service.app.config import Settings


class TaskEventProducer:
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
        self._logger.info("Kafka task event producer started")

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
            self._logger.info("Kafka task event producer stopped")

    async def _send(self, topic: str, payload: dict) -> None:
        if not self._producer:
            self._logger.warning("Kafka producer not started, skipping event")
            return
        try:
            await self._producer.send_and_wait(topic, value=payload)
        except Exception:
            self._logger.exception("Failed to produce task event")

    async def produce_task_created(
        self,
        *,
        task_id: int,
        user_id: int,
        status: str,
    ) -> None:
        await self._send(
            self._settings.kafka_settings.topic_task_created,
            {"task_id": task_id, "user_id": user_id, "status": status},
        )

    async def produce_task_status_updated(
        self,
        *,
        task_id: int,
        user_id: int,
        status: str,
    ) -> None:
        await self._send(
            self._settings.kafka_settings.topic_task_status_updated,
            {"task_id": task_id, "user_id": user_id, "status": status},
        )
