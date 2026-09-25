from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    typesafe_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    anthropic_workspace_id: str | None = None
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


# Some hosted agent environments reserve ANTHROPIC_API_KEY for the agent itself, so the key for
# GameTagger's own Claude calls may be supplied under this second name instead.
ANTHROPIC_KEY_NAMES = ("ANTHROPIC_API_KEY", "GAMETAGGER_ANTHROPIC_API_KEY")


def anthropic_api_key() -> str | None:
    """The first non-empty Anthropic key in the environment. Never log the returned value."""
    import os

    return next((v for n in ANTHROPIC_KEY_NAMES if (v := os.environ.get(n))), None)
