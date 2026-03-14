import json
import logging

from aiokafka import AIOKafkaProducer

from user_service.app.config import Settings


class UserEventProducer:
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
        self._logger.info("Kafka user event producer started")

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
            self._logger.info("Kafka user event producer stopped")

    async def _send_async(self, topic: str, payload: dict) -> None:
        if not self._producer:
            self._logger.warning("Kafka producer not started, skipping event")
            return
        try:
            await self._producer.send_and_wait(topic, value=payload)
        except Exception:
            self._logger.exception("Failed to produce user event")

    async def produce_user_registered(
        self,
        *,
        user_id: int,
        direction: str | None = None,
        level: str | None = None,
    ) -> None:
        payload = {
            "user_id": user_id,
            "direction": direction,
            "level": level,
        }
        topic = self._settings.kafka_settings.topic_user_registered
        await self._send_async(topic, payload)

    async def produce_user_profile_updated(
        self,
        *,
        user_id: int,
        direction: str | None = None,
        level: str | None = None,
    ) -> None:
        payload = {
            "user_id": user_id,
            "direction": direction,
            "level": level,
        }
        topic = self._settings.kafka_settings.topic_user_profile_updated
        await self._send_async(topic, payload)
