from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.app.data.repository import DEFAULT_DIRECTORY


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WIND_", env_file=".env", extra="ignore"
    )

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    log_level: str = "INFO"

    processed_dir: Path = DEFAULT_DIRECTORY
    default_cutoff: str = Field(
        default="09:30", pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$"
    )
