import logging

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from dishka import Provider, Scope, provide

from agent_service.app.application.use_cases.review_submission import ReviewSubmissionUseCase
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.infrastructure.kafka import SubmissionReviewConsumer, SubmissionReviewProducer
from agent_service.app.config import Settings


class KafkaCommonProvider(Provider):
    @provide(scope=Scope.APP)
    def kafka_bootstrap_servers(self, settings: Settings) -> list[str]:
        return [s.strip() for s in settings.kafka_settings.bootstrap_servers.split(",") if s.strip()]


class AIOKafkaProducerProvider(Provider):
    @provide(scope=Scope.APP)
    def kafka_producer(
            self,
            kafka_bootstrap_servers: list[str],
    ) -> AIOKafkaProducer:
        return AIOKafkaProducer(
            bootstrap_servers=kafka_bootstrap_servers,
            value_serializer=lambda v: v,
        )


class AIOKafkaConsumerProvider(Provider):
    @provide(scope=Scope.APP)
    def kafka_consumer(
            self,
            settings: Settings,
            kafka_bootstrap_servers: list[str],
    ) -> AIOKafkaConsumer:
        topic = settings.kafka_settings.topic_submission_created
        group_id = settings.kafka_settings.submission_review_consumer_group_id
        return AIOKafkaConsumer(
            topic,
            bootstrap_servers=kafka_bootstrap_servers,
            value_deserializer=lambda v: v,
            group_id=group_id,
            enable_auto_commit=False,
        )


class SubmissionReviewProducerProvider(Provider):
    @provide(scope=Scope.APP)
    def submission_review_producer(
            self,
            kafka_producer: AIOKafkaProducer,
            settings: Settings,
            logger: logging.Logger,
            metrics_recorder: MetricsRecorder,
    ) -> SubmissionReviewProducer:
        return SubmissionReviewProducer(
            kafka_producer=kafka_producer,
            output_topic=settings.kafka_settings.topic_submission_reviewed,
            logger=logger,
            metrics_recorder=metrics_recorder,
        )


class SubmissionReviewConsumerProvider(Provider):
    @provide(scope=Scope.APP)
    def submission_review_consumer(
            self,
            kafka_consumer: AIOKafkaConsumer,
            submission_review_producer: SubmissionReviewProducer,
            review_submission_use_case: ReviewSubmissionUseCase,
            settings: Settings,
            logger: logging.Logger,
            metrics_recorder: MetricsRecorder,
    ) -> SubmissionReviewConsumer:
        return SubmissionReviewConsumer(
            kafka_consumer=kafka_consumer,
            submission_review_producer=submission_review_producer,
            review_submission_use_case=review_submission_use_case,
            input_topic=settings.kafka_settings.topic_submission_created,
            logger=logger,
            metrics_recorder=metrics_recorder,
        )


KafkaProviders = [
    KafkaCommonProvider(),
    AIOKafkaConsumerProvider(),
    AIOKafkaProducerProvider(),
    SubmissionReviewProducerProvider(),
    SubmissionReviewConsumerProvider(),
]
