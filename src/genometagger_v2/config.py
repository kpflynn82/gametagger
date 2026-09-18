from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    typesafe_api_key: str | None = None
    typesafe_model: str = "jev-latest"
    jev_shadow_mode: bool = True
    decision_engine: str = "legacy"
    observer_provider: str = "stub"
    observer_model: str | None = None
    app_env: str = "development"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
