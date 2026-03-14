from dishka import Provider, Scope, provide

from user_service.app.application.interfaces.kafka import UserEventProducerInterface
from user_service.app.infrastructure.kafka import UserEventProducer


class KafkaProvider(Provider):
    user_event_producer = provide(
        UserEventProducer,
        provides=UserEventProducerInterface,
        scope=Scope.APP,
    )
