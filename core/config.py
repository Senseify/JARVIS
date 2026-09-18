"""Configuration settings for JARVIS OS Core."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from core.constants import APP_NAME, DEFAULT_HOST, DEFAULT_PORT


class Settings(BaseSettings):
    """Core runtime settings, configurable via environment variables."""

    app_name: str = APP_NAME
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT

    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
