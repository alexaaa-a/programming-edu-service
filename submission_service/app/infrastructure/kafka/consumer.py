import asyncio
import json
import logging
from typing import Any

from aiokafka import AIOKafkaConsumer
from dishka import AsyncContainer

from submission_service.app.application.dto.submission import ReviewDTO
from submission_service.app.application.interfaces.db.task_cache import TaskCacheInterface
from submission_service.app.application.use_case.submissions.process_review_result import (
    ProcessReviewResultUseCase,
)
from submission_service.app.config import Settings


KAFKA_CONSUMER_START_DELAY_SEC = 60


def _parse_review_message(value: bytes) -> dict[str, Any] | None:
    try:
        return json.loads(value.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


async def run_review_completed_consumer(
    settings: Settings,
    container: AsyncContainer,
    logger: logging.Logger,
) -> None:
    logger.info("Waiting %ss for Kafka group coordinator to be ready...", KAFKA_CONSUMER_START_DELAY_SEC)
    await asyncio.sleep(KAFKA_CONSUMER_START_DELAY_SEC)
    topic = settings.kafka_settings.topic_submission_review_completed
    bootstrap = settings.kafka_settings.bootstrap_servers.split(",")
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        value_deserializer=lambda v: v,
        group_id="submission-service-review-completed",
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
    logger.info("Kafka consumer started for %s", topic)
    try:
        async for msg in consumer:
            raw = _parse_review_message(msg.value)
            if not raw:
                logger.warning("Invalid message in %s: %s", topic, msg.value)
                continue
            submission_id = raw.get("submission_id")
            if submission_id is None:
                logger.warning("Missing submission_id in message")
                continue
            score = raw.get("score")
            feedback = raw.get("feedback", "")
            suggestions = raw.get("suggestions") or []
            if score is None:
                review_dto = None
            else:
                review_dto = ReviewDTO(score=score, feedback=feedback, suggestions=suggestions)
            async with container() as request_container:
                uc = await request_container.get(ProcessReviewResultUseCase)
                await uc(submission_id, review_dto)
    finally:
        await consumer.stop()
        logger.info("Kafka consumer stopped for %s", topic)


def _parse_json(value: bytes) -> dict[str, Any] | None:
    try:
        return json.loads(value.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


async def run_task_events_consumer(
    settings: Settings,
    task_cache: TaskCacheInterface,
    logger: logging.Logger,
) -> None:
    logger.info("Waiting %ss for Kafka group coordinator to be ready...", KAFKA_CONSUMER_START_DELAY_SEC)
    await asyncio.sleep(KAFKA_CONSUMER_START_DELAY_SEC)
    bootstrap = settings.kafka_settings.bootstrap_servers.split(",")
    topics = [
        settings.kafka_settings.topic_task_created,
        settings.kafka_settings.topic_task_status_updated,
    ]
    consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers=bootstrap,
        value_deserializer=lambda v: v,
        group_id="submission-service-task-events",
    )
    for attempt in range(1, 31):
        try:
            await consumer.start()
            break
        except Exception as e:
            logger.warning(
                "Kafka task events consumer not ready (attempt %s/30): %s",
                attempt,
                e,
            )
            await asyncio.sleep(2)
    else:
        logger.error("Kafka task events consumer failed to start after 30 attempts")
        return
    logger.info("Kafka consumer started for topics %s", topics)
    try:
        async for msg in consumer:
            raw = _parse_json(msg.value)
            if not raw:
                continue
            task_id = raw.get("task_id")
            user_id = raw.get("user_id")
            status = raw.get("status")
            if task_id is None or user_id is None or status is None:
                continue
            await task_cache.upsert_task(int(task_id), int(user_id), str(status))
            logger.debug("Task cache updated task_id=%s user_id=%s status=%s", task_id, user_id, status)
    finally:
        await consumer.stop()
        logger.info("Kafka consumer stopped for %s", topics)
