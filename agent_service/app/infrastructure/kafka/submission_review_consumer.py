import asyncio
import json
import logging
from typing import Any, Protocol

from aiokafka import AIOKafkaConsumer

from agent_service.app.application.use_cases.review_submission import ReviewSubmissionResult
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.infrastructure.kafka.submission_review_producer import (
    SubmissionReviewProducerProtocol,
)


class ReviewSubmissionUseCaseProtocol(Protocol):
    async def __call__(
        self,
        submission_id: str,
        code: str,
        task_description: str,
    ) -> ReviewSubmissionResult: ...


class SubmissionReviewConsumer:
    def __init__(
        self,
        *,
        kafka_consumer: AIOKafkaConsumer,
        submission_review_producer: SubmissionReviewProducerProtocol,
        review_submission_use_case: ReviewSubmissionUseCaseProtocol,
        input_topic: str,
        logger: logging.Logger,
        metrics_recorder: MetricsRecorder,
    ) -> None:
        self._consumer = kafka_consumer
        self._producer = submission_review_producer
        self._use_case = review_submission_use_case
        self._input_topic = input_topic
        self._logger = logger
        self._metrics = metrics_recorder

    async def run(self) -> None:
        await self._consumer.start()
        await self._producer.start()

        try:
            async for msg in self._consumer:
                if msg.topic != self._input_topic:
                    continue

                payload = _try_parse_json(msg.value)
                if payload is None:
                    self._logger.warning(
                        "Invalid JSON message on topic=%s, value=%r",
                        msg.topic,
                        msg.value,
                    )
                    continue

                submission_id = payload.get("submission_id")
                code = payload.get("code")
                task_description = payload.get("task_description")
                if submission_id is None or code is None or task_description is None:
                    self._logger.warning(
                        "Missing fields in message on topic=%s, payload=%r",
                        msg.topic,
                        payload,
                    )
                    continue

                self._logger.info(
                    "kafka.event.received topic=%s submission_id=%s",
                    msg.topic,
                    submission_id,
                )
                msg_started_at = asyncio.get_running_loop().time()
                try:
                    result = await self._use_case(
                        submission_id=str(submission_id),
                        code=str(code),
                        task_description=str(task_description),
                    )
                except Exception:
                    self._metrics.increment(
                        "error_count_total",
                        1,
                        tags={
                            "component": "kafka",
                            "operation": "consume",
                            "topic": msg.topic,
                            "status": "error",
                        },
                    )
                    self._logger.exception(
                        "Failed to process submission_id=%s",
                        submission_id,
                    )
                    msg_finished_at = asyncio.get_running_loop().time()
                    self._metrics.record_duration_seconds(
                        "kafka_message_processing_duration_seconds",
                        msg_finished_at - msg_started_at,
                        tags={"topic": msg.topic, "status": "error"},
                    )
                    self._metrics.record_duration_seconds(
                        "latency_seconds",
                        msg_finished_at - msg_started_at,
                        tags={
                            "component": "kafka",
                            "operation": "consume",
                            "topic": msg.topic,
                            "status": "error",
                        },
                    )
                    continue

                try:
                    await self._producer.produce_submission_reviewed(result)
                except Exception:
                    self._metrics.increment(
                        "error_count_total",
                        1,
                        tags={
                            "component": "kafka",
                            "operation": "produce",
                            "topic": msg.topic,
                            "status": "error",
                        },
                    )
                    self._logger.exception(
                        "Failed to produce submission.reviewed event for submission_id=%s",
                        submission_id,
                    )
                    msg_finished_at = asyncio.get_running_loop().time()
                    self._metrics.record_duration_seconds(
                        "kafka_message_processing_duration_seconds",
                        msg_finished_at - msg_started_at,
                        tags={"topic": msg.topic, "status": "error"},
                    )
                    self._metrics.record_duration_seconds(
                        "latency_seconds",
                        msg_finished_at - msg_started_at,
                        tags={
                            "component": "kafka",
                            "operation": "produce",
                            "topic": msg.topic,
                            "status": "error",
                        },
                    )
                    continue

                msg_finished_at = asyncio.get_running_loop().time()
                self._metrics.record_duration_seconds(
                    "kafka_message_processing_duration_seconds",
                    msg_finished_at - msg_started_at,
                    tags={"topic": msg.topic, "status": "success"},
                )
                self._metrics.record_duration_seconds(
                    "latency_seconds",
                    msg_finished_at - msg_started_at,
                    tags={
                        "component": "kafka",
                        "operation": "consume",
                        "topic": msg.topic,
                        "status": "success",
                    },
                )
                self._logger.info(
                    "kafka.event.processed topic=%s submission_id=%s duration_seconds=%.3f",
                    msg.topic,
                    submission_id,
                    msg_finished_at - msg_started_at,
                )
        except asyncio.CancelledError:
            self._logger.info("SubmissionReviewConsumer cancelled")
            raise
        finally:
            await self._consumer.stop()
            await self._producer.stop()


def _try_parse_json(value: bytes) -> dict[str, Any] | None:
    try:
        return json.loads(value.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
