"""Configuration settings for JARVIS OS Core."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from core.constants import APP_NAME, DEFAULT_HOST, DEFAULT_PORT, DEFAULT_DB_PATH


class Settings(BaseSettings):
    """Core runtime settings, configurable via environment variables."""

    app_name: str = APP_NAME
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    database_path: str = DEFAULT_DB_PATH
    enable_demo_tool: bool = True
    voice_stt_provider: str = "deterministic"
    voice_tts_provider: str = "deterministic"
    voice_default_language: str = "en-US"
    voice_default_voice: str = "default"
    voice_sample_rate: int = 16000

    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
