import json
import logging
from typing import Any, Protocol

from aiokafka import AIOKafkaProducer

from agent_service.app.application.use_cases.review_submission import (
    ReviewSubmissionResult,
)
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
import time


class SubmissionReviewProducerProtocol(Protocol):
    async def produce_submission_reviewed(
            self,
            result: ReviewSubmissionResult,
    ) -> None: ...

    async def produce_submission_failed(
            self,
            submission_id: str,
            reason: str,
    ) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class SubmissionReviewProducer(SubmissionReviewProducerProtocol):
    def __init__(
            self,
            kafka_producer: AIOKafkaProducer,
            output_topic: str,
            logger: logging.Logger,
            metrics_recorder: MetricsRecorder,
    ) -> None:
        self._producer = kafka_producer
        self._output_topic = output_topic
        self._logger = logger
        self._started = False
        self._metrics = metrics_recorder

    async def start(self) -> None:
        if self._started:
            return
        try:
            await self._producer.start()
        except Exception as e:
            msg = str(e).lower()
            if "already" in msg and "start" in msg:
                self._logger.warning(
                    "Kafka producer already started for %s: %r",
                    self._output_topic,
                    e,
                )
                self._started = True
                return
            self._logger.exception(
                "Failed to start Kafka producer for topic=%s",
                self._output_topic,
            )
            raise
        self._started = True
        self._logger.info("Kafka producer started for %s", self._output_topic)

    async def stop(self) -> None:
        if not self._started:
            return
        await self._producer.stop()
        self._started = False
        self._logger.info("Kafka producer stopped for %s", self._output_topic)

    async def produce_submission_reviewed(
            self,
            result: ReviewSubmissionResult,
    ) -> None:
        if not self._started:
            try:
                await self.start()
            except Exception:
                self._logger.exception(
                    "Failed to start Kafka producer before sending submission.reviewed",
                )
                raise
            if not self._started:
                raise RuntimeError(
                    f"Kafka producer is not started for topic={self._output_topic}"
                )

        event: dict[str, Any] = {
            "submission_id": result.submission_id,
            "score": result.review.score,
            "feedback": result.review.feedback,
            "suggestions": result.review.suggestions,
            "criteria": [
                {
                    "id": item.id,
                    "text": item.text,
                    "passed": item.passed,
                    "note": item.note,
                }
                for item in result.review.criteria
            ],
            "challenges": [
                {
                    "text": item.text,
                    "severity": item.severity,
                }
                for item in result.review.challenges
            ],
            "agent_path": [
                {
                    "kind": item.kind,
                    "name": item.name,
                    "status": item.status,
                    "detail": item.detail,
                }
                for item in result.review.agent_path
            ],
        }
        started_at = time.perf_counter()
        self._logger.info(
            "kafka.event.producing topic=%s submission_id=%s",
            self._output_topic,
            result.submission_id,
        )
        try:
            await self._producer.send_and_wait(
                self._output_topic,
                value=json.dumps(event).encode("utf-8"),
                key=str(result.submission_id).encode("utf-8"),
            )
            self._metrics.record_duration_seconds(
                "latency_seconds",
                time.perf_counter() - started_at,
                tags={"component": "kafka", "operation": "produce", "topic": self._output_topic, "status": "success"},
            )
            self._metrics.record_duration_seconds(
                "kafka_produce_duration_seconds",
                time.perf_counter() - started_at,
                tags={"topic": self._output_topic, "status": "success"},
            )
        except Exception:
            self._metrics.increment(
                "error_count_total",
                1,
                tags={"component": "kafka", "operation": "produce", "topic": self._output_topic, "status": "error"},
            )
            self._metrics.record_duration_seconds(
                "kafka_produce_duration_seconds",
                time.perf_counter() - started_at,
                tags={"topic": self._output_topic, "status": "error"},
            )
            self._metrics.record_duration_seconds(
                "latency_seconds",
                time.perf_counter() - started_at,
                tags={"component": "kafka", "operation": "produce", "topic": self._output_topic, "status": "error"},
            )
            self._logger.exception(
                "Failed to publish submission.reviewed for submission_id=%s",
                result.submission_id,
            )
            raise

    async def produce_submission_failed(
            self,
            submission_id: str,
            reason: str,
    ) -> None:
        if not self._started:
            await self.start()
        event: dict[str, Any] = {
            "submission_id": submission_id,
            "score": None,
            "feedback": reason,
            "suggestions": [],
            "criteria": [],
            "challenges": [],
            "agent_path": [],
        }
        await self._producer.send_and_wait(
            self._output_topic,
            value=json.dumps(event).encode("utf-8"),
            key=str(submission_id).encode("utf-8"),
        )
        self._logger.warning(
            "kafka.event.produced_failed topic=%s submission_id=%s reason=%s",
            self._output_topic,
            submission_id,
            reason,
        )
