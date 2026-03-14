from .mongo import MongoClientProvider, MongoDBProvider


db_provider = [
    MongoClientProvider(),
    MongoDBProvider()
]

__all__ = ["db_provider"]
