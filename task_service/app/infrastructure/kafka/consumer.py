import asyncio
import json
import logging
from typing import Any

from aiokafka import AIOKafkaConsumer

from task_service.app.application.dto.user import MetaUserDTO
from task_service.app.application.interfaces.db.meta_user_db import MetaUserDBInterface
from task_service.app.config import Settings


KAFKA_CONSUMER_START_DELAY_SEC = 60


def _parse_message(value: bytes) -> dict[str, Any] | None:
    try:
        return json.loads(value.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


async def _handle_user_event_async(
    payload: dict[str, Any],
    meta_user_db: MetaUserDBInterface,
    logger: logging.Logger,
) -> None:
    user_id = payload.get("user_id")
    if user_id is None:
        logger.warning("User event missing user_id")
        return
    direction = payload.get("direction")
    level = payload.get("level")
    meta = MetaUserDTO(
        user_id=int(user_id),
        direction=(direction if direction is not None else ""),
        level=(level if level is not None else ""),
    )
    await meta_user_db.create_update_meta_user(meta)


async def run_user_events_consumer(
    settings: Settings,
    meta_user_db: MetaUserDBInterface,
    logger: logging.Logger,
) -> None:
    logger.info("Waiting %ss for Kafka group coordinator to be ready...", KAFKA_CONSUMER_START_DELAY_SEC)
    await asyncio.sleep(KAFKA_CONSUMER_START_DELAY_SEC)
    bootstrap = settings.kafka_settings.bootstrap_servers.split(",")
    topics = [
        settings.kafka_settings.topic_user_registered,
        settings.kafka_settings.topic_user_profile_updated,
    ]
    consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers=bootstrap,
        value_deserializer=lambda v: v,
        group_id="task-service-user-events",
    )
    for attempt in range(1, 31):
        try:
            await consumer.start()
            break
        except Exception as e:
            logger.warning(
                "Kafka consumer not ready (attempt %s/30): %s",
                attempt,
                e,
            )
            await asyncio.sleep(2)
    else:
        logger.error("Kafka consumer failed to start after 30 attempts")
        return
    logger.info("Kafka consumer started for topics %s", topics)
    try:
        async for msg in consumer:
            raw = _parse_message(msg.value)
            if not raw:
                logger.warning("Invalid message in %s: %s", msg.topic, msg.value)
                continue
            await _handle_user_event_async(raw, meta_user_db, logger)
    finally:
        await consumer.stop()
        logger.info("Kafka consumer stopped for %s", topics)
