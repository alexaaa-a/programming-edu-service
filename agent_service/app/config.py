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


class TinyDbSettings(BaseSettings):
    chat_history_path: str = "/app/agent_service/data/chat_history.json"

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_TINYDB_")


class RedisSettings(BaseSettings):
    host: str
    port: int
    db: int
    retrieve_cache_ttl_sec: int
    password: str
    checkpoint_ttl_sec: int = 86_400

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_REDIS_")


class LoggingSettings(BaseSettings):
    level: str = "INFO"


class KafkaSettings(BaseSettings):
    bootstrap_servers: str
    topic_submission_created: str
    topic_submission_reviewed: str
    submission_review_consumer_group_id: str

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_KAFKA_")


class OpenAISettings(BaseSettings):
    api_key: str
    base_url: str
    model: str
    embedding_model: str = "text-embedding-3-small"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    temperature: float = 0.1
    reasoning_effort: str = "none"
    timeout_sec: float = 90.0

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_OPENAI_")


class MemorySettings(BaseSettings):
    embedding_backend: str = "openai"
    persist_dir: str = "/app/agent_service/data/vector_store"
    max_retrieve_top_k: int = 8

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_MEMORY_")


class ChatHistorySettings(BaseSettings):
    max_messages: int = 20

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_CHAT_HISTORY_")


class SubmissionGatewaySettings(BaseSettings):
    url: str = "http://submission_service:8000"
    timeout_sec: float = 5.0

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_SUBMISSION_")


class CareerSettings(BaseSettings):
    token: str = ""

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_CAREER_")


class TokenSettings(BaseSettings):
    secret_key: str = ""
    algorithm: str = "HS256"
    allow_dev_auth: bool = False

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_TOKEN_")


class LangfuseSettings(BaseSettings):
    enabled: bool = False
    public_key: str = ""
    secret_key: str = ""
    host: str = "http://localhost:4000"
    environment: str = "local"
    debug: bool = False
    sample_rate: float = 1.0

    model_config = SettingsConfigDict(env_prefix="AGENT_SERVICE_LANGFUSE_")

    @property
    def is_enabled(self) -> bool:
        return bool(
            self.enabled
            and self.public_key.strip()
            and self.secret_key.strip()
            and self.host.strip()
        )


class Settings(BaseSettings):
    logging_settings: LoggingSettings = LoggingSettings()  # type: ignore[call-arg]
    kafka_settings: KafkaSettings = KafkaSettings()  # type: ignore[call-arg]
    openai_settings: OpenAISettings = OpenAISettings()  # type: ignore[call-arg]
    memory_settings: MemorySettings = MemorySettings()
    mongo_settings: MongoSettings = MongoSettings()  # type: ignore[call-arg]
    tinydb_settings: TinyDbSettings = TinyDbSettings()
    chat_history_settings: ChatHistorySettings = ChatHistorySettings()  # type: ignore[call-arg]
    redis_settings: RedisSettings = RedisSettings()  # type: ignore[call-arg]
    langfuse_settings: LangfuseSettings = LangfuseSettings()
    submission_gateway_settings: SubmissionGatewaySettings = SubmissionGatewaySettings()
    career_settings: CareerSettings = CareerSettings()
    token_settings: TokenSettings = TokenSettings()

    model_config = SettingsConfigDict(env_prefix="")
