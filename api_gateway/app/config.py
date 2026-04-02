from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_prefix: str = "/api"

    user_service_url: str
    task_service_url: str
    submission_service_url: str
    agent_service_url: str
    rate_limit_redis_url: str

    proxy_timeout_sec: int = 120
    rate_limit_enabled: bool = True
    rate_limit_max_requests: int = 120
    rate_limit_window_sec: int = 60
    rate_limit_service_max_requests: str = ""
    sticky_enabled: bool = True

    model_config = SettingsConfigDict(env_prefix="API_GATEWAY_SETTINGS_")
