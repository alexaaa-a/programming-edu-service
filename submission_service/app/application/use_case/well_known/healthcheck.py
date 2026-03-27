from submission_service.app.application.interfaces.db.mongo_db import MongoDBInterface
from submission_service.app.application.interfaces.kafka import SubmissionEventProducerInterface


class HealthCheckUseCase:
    def __init__(
        self,
        mongo_db: MongoDBInterface,
        kafka: SubmissionEventProducerInterface,
    ) -> None:
        self.mongo_db = mongo_db
        self.kafka = kafka

    async def __call__(self) -> None:
        mongo_ok = await self.mongo_db.health()
        kafka_ok = await self.kafka.health()

        if not (mongo_ok and kafka_ok):
            raise RuntimeError("Not all databases are ready")
