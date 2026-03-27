from pydantic_core import MultiHostUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class MongoSettings(BaseSettings):
    host: str
    port: int
    username: str
    password: str
    name: str
    ssl: bool = False
    server_selection_timeout_ms: int = 5000

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_MONGO_")

    @property
    def connection_string(self) -> MultiHostUrl:
        return MultiHostUrl.build(
            scheme="mongodb",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
        )


class RedisSettings(BaseSettings):
    host: str
    port: int
    db: int
    retrieve_cache_ttl_sec: int
    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_REDIS_")


class LoggingSettings(BaseSettings):
    level: str = "INFO"


class KafkaSettings(BaseSettings):
    bootstrap_servers: str
    topic_submission_created: str
    topic_submission_reviewed: str
    submission_review_consumer_group_id: str

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_KAFKA_")


class OpenRouterSettings(BaseSettings):
    api_key: str
    base_url: str
    model: str
    temperature: float = 0.1
    timeout_sec: int = 60
    retry_count: int = 0
    retry_backoff_sec: float = 1.0

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_OPENROUTER_")


class ChatHistorySettings(BaseSettings):
    max_messages: int = 20

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_CHAT_HISTORY_")


class Settings(BaseSettings):
    logging_settings: LoggingSettings = LoggingSettings()  # type: ignore[call-arg]
    kafka_settings: KafkaSettings = KafkaSettings()  # type: ignore[call-arg]
    openrouter_settings: OpenRouterSettings = OpenRouterSettings()  # type: ignore[call-arg]
    mongo_settings: MongoSettings = MongoSettings()  # type: ignore[call-arg]
    chat_history_settings: ChatHistorySettings = ChatHistorySettings()  # type: ignore[call-arg]
    redis_settings: RedisSettings = RedisSettings()  # type: ignore[call-arg]

    model_config = SettingsConfigDict(env_prefix="")
