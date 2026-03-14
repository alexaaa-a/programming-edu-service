from dishka import Provider, Scope, provide

from submission_service.app.application.interfaces.kafka import SubmissionEventProducerInterface
from submission_service.app.infrastructure.kafka import SubmissionEventProducer


class KafkaProvider(Provider):
    submission_event_producer = provide(
        SubmissionEventProducer,
        provides=SubmissionEventProducerInterface,
        scope=Scope.APP,
    )


