from dishka import Provider, Scope, provide

from task_service.app.application.interfaces.kafka import TaskEventProducerInterface
from task_service.app.infrastructure.kafka import TaskEventProducer


class KafkaProvider(Provider):
    task_event_producer = provide(
        TaskEventProducer,
        provides=TaskEventProducerInterface,
        scope=Scope.APP,
    )
