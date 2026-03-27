from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_prefix: str = "/api"

    user_service_url: str
    task_service_url: str
    submission_service_url: str
    agent_service_url: str

    proxy_timeout_sec: int = 120

    model_config = SettingsConfigDict(env_prefix="API_GATEWAY_SETTINGS_")
