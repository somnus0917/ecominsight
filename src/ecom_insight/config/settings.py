from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Runtime settings loaded from environment variables or explicit arguments."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ECOM_",
        extra="ignore",
        case_sensitive=False,
    )

    source_root: Path
    output_root: Path = Path("data/processed")
    salt_file: Path = Path("data/.secrets/hmac_salt")
    hmac_salt: SecretStr | None = None
    log_level: str = "INFO"
    external_api_enabled: bool = False

    @field_validator("source_root")
    @classmethod
    def source_root_must_exist(cls, value: Path) -> Path:
        resolved = value.expanduser().resolve()
        if not resolved.is_dir():
            msg = f"Source root does not exist or is not a directory: {resolved}"
            raise ValueError(msg)
        return resolved

    @field_validator("output_root", "salt_file")
    @classmethod
    def local_paths_are_resolved(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    def luopan_db(self) -> Path:
        return self.source_root / "state" / "luopan.db"

    def inventory_root(self) -> Path:
        return self.source_root / "output" / "inventory"

    def orders_root(self) -> Path:
        return self.source_root / "output" / "orders"

    def external_orders_file(self) -> Path:
        return self.source_root / "output" / "external_orders" / "orders_daily.json"

    def settlement_root(self) -> Path:
        return self.source_root / "output" / "settlement"

    def validate_expected_sources(self) -> None:
        required = (
            self.luopan_db(),
            self.inventory_root(),
            self.orders_root(),
            self.external_orders_file(),
            self.settlement_root(),
        )
        missing = [path for path in required if not path.exists()]
        if missing:
            joined = ", ".join(str(path) for path in missing)
            raise ValueError(f"Required source paths are missing: {joined}")
