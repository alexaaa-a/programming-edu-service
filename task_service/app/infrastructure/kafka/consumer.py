import asyncio
import json
import logging
from typing import Any

from aiokafka import AIOKafkaConsumer
from aiokafka.structs import OffsetAndMetadata, TopicPartition

from task_service.app.application.dto.user import MetaUserDTO
from task_service.app.application.interfaces.db.meta_user_db import MetaUserDBInterface
from task_service.app.config import Settings


KAFKA_CONSUMER_START_DELAY_SEC = 60
_COMMIT_RETRIES = 5
_RETRY_SLEEP_SEC = 2.0


def _parse_message(value: bytes) -> dict[str, Any] | None:
    try:
        return json.loads(value.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


async def _handle_user_event_async(
    payload: dict[str, Any],
    meta_user_db: MetaUserDBInterface,
    logger: logging.Logger,
) -> bool:
    user_id = payload.get("user_id")
    if user_id is None:
        logger.warning("User event missing user_id")
        return True
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        logger.warning("User event poison user_id=%r — committing", user_id)
        return True
    direction = payload.get("direction")
    level = payload.get("level")
    meta = MetaUserDTO(
        user_id=uid,
        direction=(direction if direction is not None else ""),
        level=(level if level is not None else ""),
    )
    try:
        await meta_user_db.create_update_meta_user(meta)
    except Exception:
        logger.exception("Failed to upsert meta user_id=%s — will retry", uid)
        return False
    return True


async def _commit(consumer: AIOKafkaConsumer, msg: Any, logger: logging.Logger) -> None:
    tp = TopicPartition(msg.topic, msg.partition)
    last_error: Exception | None = None
    for attempt in range(1, _COMMIT_RETRIES + 1):
        try:
            await consumer.commit({tp: OffsetAndMetadata(msg.offset + 1, "")})
            return
        except Exception as exc:
            last_error = exc
            logger.exception(
                "Kafka commit failed attempt=%s/%s topic=%s offset=%s",
                attempt,
                _COMMIT_RETRIES,
                msg.topic,
                msg.offset,
            )
            await asyncio.sleep(_RETRY_SLEEP_SEC)
    if last_error is not None:
        raise last_error


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
        enable_auto_commit=False,
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
            while True:
                try:
                    raw = _parse_message(msg.value)
                    if not raw:
                        logger.warning("Invalid message in %s: %s", msg.topic, msg.value)
                        await _commit(consumer, msg, logger)
                        break
                    ok = await _handle_user_event_async(raw, meta_user_db, logger)
                    if not ok:
                        await asyncio.sleep(_RETRY_SLEEP_SEC)
                        continue
                    await _commit(consumer, msg, logger)
                    break
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "Unhandled user-events consumer error topic=%s offset=%s",
                        getattr(msg, "topic", "?"),
                        getattr(msg, "offset", "?"),
                    )
                    await asyncio.sleep(_RETRY_SLEEP_SEC)
    finally:
        await consumer.stop()
        logger.info("Kafka consumer stopped for %s", topics)
