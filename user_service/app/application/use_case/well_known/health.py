from user_service.app.application.interfaces.db.mongo_db import MongoDBInterface
from user_service.app.application.interfaces.db.cache import CacheInterface
from user_service.app.application.interfaces.kafka import UserEventProducerInterface


class HealthUseCase:
    def __init__(
            self,
            mongo_db: MongoDBInterface,
            cache: CacheInterface,
            kafka: UserEventProducerInterface,
    ) -> None:
        self.mongo_db = mongo_db
        self.cache = cache
        self.kafka = kafka

    async def __call__(self) -> None:
        mongo_ok = await self.mongo_db.health()
        cache_ok = await self.cache.health()
        kafka_ok = await self.kafka.health()

        all_ok = mongo_ok and cache_ok and kafka_ok

        if not all_ok:
            raise RuntimeError("Not all databases are healthy")
