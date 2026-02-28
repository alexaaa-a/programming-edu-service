from .mongo import MongoClientProvider, MongoDBProvider
from .redis import RedisProvider, RedisCacheProvider


db_provider = [
    MongoClientProvider(),
    MongoDBProvider(),
    RedisProvider(),
    RedisCacheProvider(),
]

__all__ = ["db_provider"]
