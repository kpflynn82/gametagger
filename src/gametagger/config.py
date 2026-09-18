from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    typesafe_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    typesafe_model: str = "jev-latest"
    jev_shadow_mode: bool = True
    decision_engine: str = "jev"
    observer_provider: str = "anthropic"
    observer_model: str | None = None
    app_env: str = "development"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
