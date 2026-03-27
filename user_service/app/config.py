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

    model_config = SettingsConfigDict(env_prefix="USER_SERVICE_MONGO_")

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

    model_config = SettingsConfigDict(env_prefix="USER_SERVICE_REDIS_")


class LoggingSettings(BaseSettings):
    level: str = "INFO"


class RegisterSettings(BaseSettings):
    ttl_refresh: int = 604800
    secret_key: str
    algorithm: str
    access_token_expire: int = 900

    model_config = SettingsConfigDict(env_prefix="USER_SERVICE_REGISTER_")


class KafkaSettings(BaseSettings):
    bootstrap_servers: str
    topic_user_registered: str
    topic_user_profile_updated: str

    model_config = SettingsConfigDict(env_prefix="USER_SERVICE_KAFKA_")


class Settings(BaseSettings):
    redis_settings: RedisSettings = RedisSettings()  # type: ignore[call-arg]
    mongo_settings: MongoSettings = MongoSettings()  # type: ignore[call-arg]
    logging_settings: LoggingSettings = LoggingSettings()
    register_settings: RegisterSettings = RegisterSettings()  # type: ignore[call-arg]
    kafka_settings: KafkaSettings = KafkaSettings()  # type: ignore[call-arg]
