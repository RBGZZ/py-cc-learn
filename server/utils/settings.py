from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return Path(base) / "Claude"
    return Path.home() / ".claude"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Anthropic ---
    anthropic_api_key: str | None = Field(default=None)
    anthropic_base_url: str = Field(default="https://api.anthropic.com")
    anthropic_model: str = Field(default="claude-sonnet-4-20250514")
    anthropic_default_haiku_model: str = Field(default="claude-3-5-haiku-20241022")
    anthropic_default_opus_model: str = Field(default="claude-3-opus-20240229")
    anthropic_default_sonnet_model: str = Field(default="claude-sonnet-4-20250514")

    # --- OpenAI ---
    openai_api_key: str | None = Field(default=None)
    openai_model: str = Field(default="gpt-4o")

    # --- DeepSeek ---
    deepseek_api_key: str | None = Field(default=None)
    deepseek_model: str = Field(default="deepseek-v4-flash")

    # --- Google ---
    google_api_key: str | None = Field(default=None)
    google_model: str = Field(default="gemini-2.0-flash")

    # --- API ---
    api_timeout_ms: int = Field(default=600_000)

    # --- Telemetry ---
    disable_nonessential_traffic: bool = Field(default=True)
    disable_telemetry: bool = Field(default=True)

    # --- Logging ---
    log_level: str = Field(default="INFO")

    # --- Server ---
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)

    # --- Config paths ---
    config_dir: Path = Field(default_factory=_default_config_dir)
    config_file: Path = Field(default_factory=lambda: _default_config_dir() / "settings.json")

    @field_validator("api_timeout_ms", mode="before")
    @classmethod
    def _validate_api_timeout(cls, v: str | int | None) -> int:
        if v is None:
            return 600_000
        return int(v)

    @field_validator("log_level", mode="before")
    @classmethod
    def _validate_log_level(cls, v: str | None) -> str:
        if v is None:
            return "INFO"
        v = v.upper()
        if v not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            return "INFO"
        return v


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_for_testing() -> Settings:
    global _settings
    _settings = Settings()
    return _settings
