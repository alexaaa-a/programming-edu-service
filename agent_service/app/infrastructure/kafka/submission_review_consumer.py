import asyncio
import json
import logging
from typing import Any, Protocol
from uuid import uuid4

from aiokafka import AIOKafkaConsumer
from aiokafka.structs import OffsetAndMetadata, TopicPartition

from agent_service.app.application.use_cases.review_submission import ReviewSubmissionResult
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.observability.tracing import reset_trace_id, set_trace_id
from agent_service.app.infrastructure.kafka.submission_review_producer import (
    SubmissionReviewProducerProtocol,
)

_RETRY_SLEEP_SEC = 2.0
_MAX_RETRIES = 15
_MAX_PRODUCE_RETRIES = 15
_COMMIT_RETRIES = 5


class ReviewSubmissionUseCaseProtocol(Protocol):
    async def __call__(
            self,
            submission_id: str,
            code: str,
            task_description: str,
            task_id: str | None = None,
            user_id: str | None = None,
            attempt: int | None = None,
            previous_feedback: str | None = None,
    ) -> ReviewSubmissionResult: ...


class SubmissionReviewConsumer:
    def __init__(
            self,
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
                while True:
                    try:
                        await self._handle_message(msg)
                        break
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        self._logger.exception(
                            "Unhandled error processing Kafka message topic=%s offset=%s",
                            getattr(msg, "topic", "?"),
                            getattr(msg, "offset", "?"),
                        )
                        await asyncio.sleep(_RETRY_SLEEP_SEC)
        except asyncio.CancelledError:
            self._logger.info("SubmissionReviewConsumer cancelled")
            raise
        finally:
            await self._consumer.stop()
            await self._producer.stop()

    async def _handle_message(self, msg: Any) -> None:
        if msg.topic != self._input_topic:
            await self._commit_message(msg)
            return

        payload = _try_parse_json(msg.value)
        if payload is None:
            self._logger.warning(
                "Invalid JSON message on topic=%s, value=%r",
                msg.topic,
                msg.value,
            )
            await self._commit_message(msg)
            return

        submission_id = payload.get("submission_id")
        code = payload.get("code")
        task_description = payload.get("task_description")
        task_id = _optional_str(payload.get("task_id"))
        user_id = _optional_str(payload.get("user_id"))
        attempt = _optional_int(payload.get("attempt"))
        previous_feedback = _optional_str(payload.get("previous_feedback"))
        if submission_id is None or code is None or task_description is None:
            self._logger.warning(
                "Missing fields in message on topic=%s, payload=%r",
                msg.topic,
                payload,
            )
            await self._commit_message(msg)
            return

        self._logger.info(
            "kafka.event.received topic=%s submission_id=%s attempt=%s",
            msg.topic,
            submission_id,
            attempt,
        )

        result: ReviewSubmissionResult | None = None
        review_failures = 0
        produce_failures = 0

        while True:
            msg_started_at = asyncio.get_running_loop().time()
            token = set_trace_id(uuid4().hex)
            try:
                if result is None:
                    result = await self._use_case(
                        submission_id=str(submission_id),
                        code=str(code),
                        task_description=str(task_description),
                        task_id=task_id,
                        user_id=user_id,
                        attempt=attempt,
                        previous_feedback=previous_feedback,
                    )
                await self._producer.produce_submission_reviewed(result)
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
                    "Failed to process submission_id=%s review_done=%s",
                    submission_id,
                    result is not None,
                )
                msg_finished_at = asyncio.get_running_loop().time()
                self._metrics.record_duration_seconds(
                    "kafka_message_processing_duration_seconds",
                    msg_finished_at - msg_started_at,
                    tags={"topic": msg.topic, "status": "error"},
                )
                if result is not None:
                    produce_failures += 1
                    if produce_failures >= _MAX_PRODUCE_RETRIES:
                        self._logger.error(
                            "Produce exhausted after successful review submission_id=%s "
                            "failures=%s — blocking partition until broker recovers",
                            submission_id,
                            produce_failures,
                        )
                        await asyncio.sleep(_RETRY_SLEEP_SEC * 5)
                        produce_failures = 0
                    await asyncio.sleep(_RETRY_SLEEP_SEC)
                    continue

                review_failures += 1
                if review_failures >= _MAX_RETRIES:
                    emitted = False
                    try:
                        await self._producer.produce_submission_failed(
                            str(submission_id),
                            reason=(
                                "agent_service: review failed after "
                                f"{review_failures} retries"
                            ),
                        )
                        emitted = True
                    except Exception:
                        self._logger.exception(
                            "Failed to emit failure event for submission_id=%s",
                            submission_id,
                        )
                    if not emitted:
                        await asyncio.sleep(_RETRY_SLEEP_SEC)
                        continue
                    await self._commit_message(msg)
                    break
                await asyncio.sleep(_RETRY_SLEEP_SEC)
                continue
            finally:
                reset_trace_id(token)

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
                "kafka.event.processed topic=%s submission_id=%s duration_seconds=%.3f produce_retries=%s",
                msg.topic,
                submission_id,
                msg_finished_at - msg_started_at,
                produce_failures,
            )
            while True:
                try:
                    await self._commit_message(msg)
                    break
                except Exception:
                    self._logger.exception(
                        "Kafka commit after produce failed submission_id=%s — "
                        "retrying commit only (result preserved)",
                        submission_id,
                    )
                    await asyncio.sleep(_RETRY_SLEEP_SEC)
            break

    async def _commit_message(self, msg: Any) -> None:
        tp = TopicPartition(msg.topic, msg.partition)
        last_error: Exception | None = None
        for attempt in range(1, _COMMIT_RETRIES + 1):
            try:
                await self._consumer.commit({tp: OffsetAndMetadata(msg.offset + 1, "")})
                return
            except Exception as exc:
                last_error = exc
                self._logger.exception(
                    "Kafka commit failed attempt=%s/%s topic=%s offset=%s",
                    attempt,
                    _COMMIT_RETRIES,
                    msg.topic,
                    msg.offset,
                )
                await asyncio.sleep(_RETRY_SLEEP_SEC)
        if last_error is not None:
            raise last_error


def _optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _try_parse_json(value: bytes) -> dict[str, Any] | None:
    try:
        return json.loads(value.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
