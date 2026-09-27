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

    model_config = SettingsConfigDict(env_prefix="TASK_SERVICE_MONGO_")

    @property
    def connection_string(self) -> MultiHostUrl:
        return MultiHostUrl.build(
            scheme="mongodb",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port
        )


class RedisSettings(BaseSettings):
    host: str
    port: int
    db: int
    cache_ttl_sec: int = 300
    password: str

    model_config = SettingsConfigDict(env_prefix="TASK_SERVICE_REDIS_")


class TokenSettings(BaseSettings):
    secret_key: str
    algorithm: str

    model_config = SettingsConfigDict(env_prefix="TASK_SERVICE_TOKEN_")


class LoggingSettings(BaseSettings):
    level: str = "INFO"


class KafkaSettings(BaseSettings):
    bootstrap_servers: str
    topic_user_registered: str
    topic_user_profile_updated: str
    topic_task_created: str
    topic_task_status_updated: str

    model_config = SettingsConfigDict(env_prefix="TASK_SERVICE_KAFKA_")


class SubmissionGatewaySettings(BaseSettings):
    url: str = "http://submission_service:8000"
    timeout_sec: float = 5.0

    model_config = SettingsConfigDict(env_prefix="TASK_SERVICE_SUBMISSION_")


class AgentGatewaySettings(BaseSettings):
    url: str = "http://agent_service:8000"
    token: str = ""
    timeout_sec: float = 45.0

    model_config = SettingsConfigDict(env_prefix="TASK_SERVICE_AGENT_")


class UserGatewaySettings(BaseSettings):
    url: str = "http://user_service:8000"
    timeout_sec: float = 5.0

    model_config = SettingsConfigDict(env_prefix="TASK_SERVICE_USER_")


class CloseGateSettings(BaseSettings):
    pass_score: int = 8
    max_rounds: int = 2

    model_config = SettingsConfigDict(env_prefix="TASK_SERVICE_CLOSE_")


class Settings(BaseSettings):
    mongo_settings: MongoSettings = MongoSettings()  # type: ignore[call-arg]
    redis_settings: RedisSettings = RedisSettings()  # type: ignore[call-arg]
    token_settings: TokenSettings = TokenSettings()  # type: ignore[call-arg]
    logging_settings: LoggingSettings = LoggingSettings()
    kafka_settings: KafkaSettings = KafkaSettings()  # type: ignore[call-arg]
    submission_gateway_settings: SubmissionGatewaySettings = SubmissionGatewaySettings()
    agent_gateway_settings: AgentGatewaySettings = AgentGatewaySettings()
    user_gateway_settings: UserGatewaySettings = UserGatewaySettings()
    close_gate_settings: CloseGateSettings = CloseGateSettings()
