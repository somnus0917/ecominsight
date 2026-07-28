from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ECOM_API_",
        extra="ignore",
        case_sensitive=False,
    )

    database_path: Path = Path("data/processed/ecom_insight.duckdb")
    feedback_database_path: Path = Path("data/processed/feedback.sqlite")
    data_mode: Literal["real", "demo"] = "demo"
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @field_validator("database_path", "feedback_database_path")
    @classmethod
    def resolve_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()

