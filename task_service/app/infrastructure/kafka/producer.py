import json
import logging
from typing import Any

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

    async def _send(self, topic: str, payload: dict) -> None:
        if not self._producer:
            raise RuntimeError("Kafka producer not started")
        try:
            await self._producer.send_and_wait(topic, value=payload)
        except Exception:
            self._logger.exception("Failed to produce task event")
            raise

    async def produce_task_created(
            self,
            task_id: int,
            user_id: int,
            status: str,
            task_description: str,
            title: str | None = None,
            order: int | None = None,
            tests: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "task_id": task_id,
            "user_id": user_id,
            "status": status,
            "task_description": task_description,
        }
        if title is not None:
            payload["title"] = title
        if order is not None:
            payload["order"] = order
        if tests:
            payload["tests"] = tests
        await self._send(self._settings.kafka_settings.topic_task_created, payload)

    async def produce_task_status_updated(
            self,
            task_id: int,
            user_id: int,
            status: str,
            task_description: str,
            round_limit: int | None = None,
            title: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "task_id": task_id,
            "user_id": user_id,
            "status": status,
            "task_description": task_description,
        }
        if round_limit is not None:
            payload["round_limit"] = round_limit
        if title is not None:
            payload["title"] = title
        await self._send(
            self._settings.kafka_settings.topic_task_status_updated,
            payload,
        )
