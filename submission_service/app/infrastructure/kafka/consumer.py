import asyncio
import json
import logging
from typing import Any, Literal

from aiokafka import AIOKafkaConsumer
from aiokafka.structs import OffsetAndMetadata, TopicPartition
from dishka import AsyncContainer

from submission_service.app.application.dto.submission import (
    ChallengeResultDTO,
    CriterionResultDTO,
    PathStepResultDTO,
    ReviewDTO,
    TaskTestsDTO,
)
from submission_service.app.application.interfaces.db.task_cache import TaskCacheInterface
from submission_service.app.application.use_case.submissions.process_review_result import (
    ProcessReviewResultUseCase,
)
from submission_service.app.config import Settings


KAFKA_CONSUMER_START_DELAY_SEC = 60
_COMMIT_RETRIES = 5
_RETRY_SLEEP_SEC = 2.0

ApplyOutcome = Literal["applied", "skipped", "error"]


def _coerce_submission_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_score(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _normalize_suggestions(raw: Any) -> list[str]:
    if not raw:
        return []
    if not isinstance(raw, list):
        return [str(raw)]
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            out.append(item)
        else:
            out.append(str(item))
    return out


def _normalize_criteria(raw: Any) -> list[CriterionResultDTO]:
    if not raw or not isinstance(raw, list):
        return []
    out: list[CriterionResultDTO] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        cid = str(item.get("id") or f"c{index}").strip() or f"c{index}"
        out.append(
            CriterionResultDTO(
                id=cid,
                text=text,
                passed=bool(item.get("passed")),
                note=str(item.get("note") or "").strip(),
                line=_as_line(item.get("line")),
            )
        )
    return out


def _normalize_challenges(raw: Any) -> list[ChallengeResultDTO]:
    if not raw or not isinstance(raw, list):
        return []
    out: list[ChallengeResultDTO] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if text:
                out.append(ChallengeResultDTO(text=text, severity="medium"))
            continue
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        severity = str(item.get("severity") or "medium").strip().lower()
        if severity not in {"low", "medium", "high"}:
            severity = "medium"
        out.append(
            ChallengeResultDTO(text=text, severity=severity, line=_as_line(item.get("line")))
        )
    return out


def _as_line(raw: Any) -> int | None:
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if 1 <= value <= 10_000 else None


def _normalize_agent_path(raw: Any) -> list[PathStepResultDTO]:
    if not raw or not isinstance(raw, list):
        return []
    out: list[PathStepResultDTO] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        out.append(
            PathStepResultDTO(
                kind=str(item.get("kind") or "step").strip() or "step",
                name=name,
                status=str(item.get("status") or "ok").strip() or "ok",
                detail=str(item.get("detail") or "").strip(),
            )
        )
    return out


def _normalize_tests(raw: Any) -> TaskTestsDTO | None:
    if not isinstance(raw, dict):
        return None
    status = str(raw.get("status") or "").strip()
    if status not in {"passed", "failed", "error", "timeout", "unavailable"}:
        return None
    names = raw.get("failed_names")
    failed_names = [str(item) for item in names][:10] if isinstance(names, list) else []
    return TaskTestsDTO(
        status=status,
        total=_as_count(raw.get("total")),
        passed=_as_count(raw.get("passed")),
        failed_names=failed_names,
        detail=str(raw.get("detail") or "")[:400],
    )


def _as_count(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _parse_review_message(value: bytes) -> dict[str, Any] | None:
    try:
        return json.loads(value.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


async def _commit_message(consumer: AIOKafkaConsumer, msg: Any, logger: logging.Logger) -> None:
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
    logger.info("Kafka consumer started for %s", topic)
    try:
        async for msg in consumer:
            try:
                committed = await _handle_review_message(msg, container, logger)
                if committed:
                    await _commit_message(consumer, msg, logger)
                else:
                    await asyncio.sleep(_RETRY_SLEEP_SEC)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Unhandled review consumer error topic=%s offset=%s",
                    getattr(msg, "topic", "?"),
                    getattr(msg, "offset", "?"),
                )
                await asyncio.sleep(_RETRY_SLEEP_SEC)
    finally:
        await consumer.stop()
        logger.info("Kafka consumer stopped for %s", topic)


async def _handle_review_message(
        msg: Any,
        container: AsyncContainer,
        logger: logging.Logger,
) -> bool:
    raw = _parse_review_message(msg.value)
    if not raw:
        logger.warning("Invalid message in review topic: %s", msg.value)
        return True
    sid = _coerce_submission_id(raw.get("submission_id"))
    if sid is None:
        logger.warning("Invalid submission_id in message: %r", raw.get("submission_id"))
        return True
    score = _coerce_score(raw.get("score"))
    feedback = str(raw.get("feedback", "") or "")
    suggestions = _normalize_suggestions(raw.get("suggestions"))
    criteria = _normalize_criteria(raw.get("criteria"))
    challenges = _normalize_challenges(raw.get("challenges"))
    agent_path = _normalize_agent_path(raw.get("agent_path"))
    if score is None:
        review_dto = None
    else:
        review_dto = ReviewDTO(
            score=score,
            feedback=feedback,
            suggestions=suggestions,
            criteria=criteria,
            challenges=challenges,
            agent_path=agent_path,
            tests=_normalize_tests(raw.get("tests")),
        )
    async with container() as request_container:
        uc = await request_container.get(ProcessReviewResultUseCase)
        outcome = await uc(sid, review_dto)
    if outcome == "error":
        logger.warning(
            "Review apply error (will retry) submission_id=%s score=%s",
            sid,
            score,
        )
        return False
    if outcome == "skipped":
        logger.info(
            "Review apply skipped (idempotent) submission_id=%s score=%s",
            sid,
            score,
        )
    return True


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
        enable_auto_commit=False,
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
            try:
                ok = await _handle_task_event(msg, task_cache, logger)
                if ok:
                    await _commit_message(consumer, msg, logger)
                else:
                    await asyncio.sleep(_RETRY_SLEEP_SEC)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Unhandled task-events consumer error topic=%s offset=%s",
                    getattr(msg, "topic", "?"),
                    getattr(msg, "offset", "?"),
                )
                await asyncio.sleep(_RETRY_SLEEP_SEC)
    finally:
        await consumer.stop()
        logger.info("Kafka consumer stopped for %s", topics)


async def _handle_task_event(
        msg: Any,
        task_cache: TaskCacheInterface,
        logger: logging.Logger,
) -> bool:
    raw = _parse_json(msg.value)
    if not raw:
        return True
    task_id = raw.get("task_id")
    user_id = raw.get("user_id")
    status = raw.get("status")
    task_description = raw.get("task_description")
    if task_id is None or user_id is None or status is None:
        return True
    status_str = str(status).strip().lower()
    try:
        tid = int(task_id)
        uid = int(user_id)
    except (TypeError, ValueError):
        logger.warning(
            "task-events poison ids task_id=%r user_id=%r — committing",
            task_id,
            user_id,
        )
        return True
    if status_str in {"cancelled", "deleted"}:
        deleted = await task_cache.delete_task(tid, uid)
        if not deleted:
            logger.warning(
                "task_cache delete failed task_id=%s user_id=%s — will retry",
                tid,
                uid,
            )
            return False
        return True
    round_limit = None
    if raw.get("round_limit") is not None:
        try:
            round_limit = int(raw["round_limit"])
        except (TypeError, ValueError):
            round_limit = None
    title = raw.get("title")
    order: int | None = None
    if raw.get("order") is not None:
        try:
            order = int(raw["order"])
        except (TypeError, ValueError):
            order = None
    upserted = await task_cache.upsert_task(
        tid,
        uid,
        status_str,
        task_description=str(task_description) if task_description is not None else None,
        round_limit=round_limit,
        title=str(title) if title is not None else None,
        order=order,
        tests=str(raw["tests"]) if raw.get("tests") is not None else None,
    )
    if not upserted:
        logger.warning(
            "task_cache upsert failed task_id=%s user_id=%s — will retry",
            tid,
            uid,
        )
        return False
    return True
