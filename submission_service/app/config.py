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

    model_config = SettingsConfigDict(env_prefix="SUBMISSION_SERVICE_MONGO_")

    @property
    def connection_string(self) -> MultiHostUrl:
        return MultiHostUrl.build(
            scheme="mongodb",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port
        )


class TokenSettings(BaseSettings):
    secret_key: str
    algorithm: str

    model_config = SettingsConfigDict(env_prefix="SUBMISSION_SERVICE_TOKEN_")


class LoggingSettings(BaseSettings):
    level: str = "INFO"


class KafkaSettings(BaseSettings):
    bootstrap_servers: str
    topic_submission_created: str
    topic_submission_review_completed: str
    topic_task_created: str
    topic_task_status_updated: str

    model_config = SettingsConfigDict(env_prefix="SUBMISSION_SERVICE_KAFKA_")


class ReviewLoopSettings(BaseSettings):
    max_rounds: int = 2

    model_config = SettingsConfigDict(env_prefix="SUBMISSION_SERVICE_REVIEW_")


class InternalSettings(BaseSettings):
    token: str = ""

    model_config = SettingsConfigDict(env_prefix="SUBMISSION_SERVICE_INTERNAL_")


class JevSettings(BaseSettings):
    enabled: bool = True
    api_key: str = ""
    base_url: str = "https://openrouter.ai/api"
    model: str = "typesafe/jev-1.13"
    timeout_sec: float = 4.0
    min_confidence: float = 0.6
    failure_threshold: int = 3
    cooldown_sec: float = 60.0

    model_config = SettingsConfigDict(env_prefix="SUBMISSION_SERVICE_JEV_")

    @property
    def is_enabled(self) -> bool:
        return bool(self.enabled and self.api_key.strip() and self.model.strip())


class Settings(BaseSettings):
    mongo_settings: MongoSettings = MongoSettings()  # type: ignore[call-arg]
    token_settings: TokenSettings = TokenSettings()  # type: ignore[call-arg]
    logging_settings: LoggingSettings = LoggingSettings()
    kafka_settings: KafkaSettings = KafkaSettings()  # type: ignore[call-arg]
    review_loop_settings: ReviewLoopSettings = ReviewLoopSettings()
    jev_settings: JevSettings = JevSettings()
    internal_settings: InternalSettings = InternalSettings()
