from __future__ import annotations

from aiokafka import AIOKafkaProducer
import redis.asyncio as redis
from pathlib import Path

from agent_service.app.application.interfaces import HealthDependenciesChecker


class DependenciesHealthChecker(HealthDependenciesChecker):
    def __init__(
        self,
        *,
        chat_history_db_path: str,
        redis_client: redis.Redis,
        kafka_bootstrap_servers: list[str],
    ) -> None:
        self._chat_history_db_path = chat_history_db_path
        self._redis_client = redis_client
        self._kafka_bootstrap_servers = kafka_bootstrap_servers

    async def check_chat_history_db(self) -> bool:
        try:
            path = Path(self._chat_history_db_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.touch()
            _ = path.stat()
            return True
        except Exception:
            return False

    async def check_redis(self) -> bool:
        try:
            return bool(await self._redis_client.ping())
        except Exception:
            return False

    async def check_kafka(self) -> bool:
        producer = AIOKafkaProducer(
            bootstrap_servers=self._kafka_bootstrap_servers,
            value_serializer=lambda v: v,
        )
        try:
            await producer.start()
            return True
        except Exception:
            return False
        finally:
            try:
                await producer.stop()
            except Exception:
                pass

