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

    model_config = SettingsConfigDict(env_prefix="MONGO_")

    @property
    def connection_string(self) -> MultiHostUrl:
        return MultiHostUrl.build(
            scheme="mongodb",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            path=self.name
        )


class RedisSettings(BaseSettings):
    host: str
    port: int
    db: int
    cache_ttl_sec: int = 300

    model_config = SettingsConfigDict(env_prefix="REDIS_")


class TokenSettings(BaseSettings):
    secret_key: str
    algorithm: str

    model_config = SettingsConfigDict(env_prefix="TOKEN_")


class LoggingSettings(BaseSettings):
    level: str = "INFO"


class Settings(BaseSettings):
    mongo_settings: MongoSettings = MongoSettings()  # type: ignore[call-arg]
    redis_settings: RedisSettings = RedisSettings()  # type: ignore[call-arg]
    token_settings: TokenSettings = TokenSettings()  # type: ignore[call-arg]
    logging_settings: LoggingSettings = LoggingSettings()
