from .redis import RedisProvider, RedisCacheProvider
from .mongo import MongoClientProvider, MongoDBProvider


db_provider = [
    RedisProvider(),
    RedisCacheProvider(),
    MongoClientProvider(),
    MongoDBProvider()
]
__all__ = ["db_provider"]
