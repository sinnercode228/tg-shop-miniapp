"""Application settings loaded from environment variables / `.env`."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# bot/tgshop/config.py -> repo root is two levels above the package directory.
_DEFAULT_SHARED_DIR = Path(__file__).resolve().parents[2] / "shared"


def _split_csv(value: Any) -> Any:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    """Runtime configuration. Every field maps to an upper-case env variable."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: SecretStr
    webapp_url: str = "https://sinnercode228.github.io/tg-shop-miniapp/"
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    database_url: str = "sqlite+aiosqlite:///./tgshop.db"

    api_host: str = "0.0.0.0"  # noqa: S104 - container-friendly default
    api_port: int = 8080
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["https://sinnercode228.github.io", "http://localhost:5173"]
    )

    init_data_ttl: int = Field(default=24 * 60 * 60, ge=60)
    stars_enabled: bool = True
    shared_dir: Path = _DEFAULT_SHARED_DIR
    log_level: str = "INFO"

    @field_validator("admin_ids", "cors_origins", mode="before")
    @classmethod
    def _parse_csv(cls, value: Any) -> Any:
        return _split_csv(value)

    @cached_property
    def catalog_path(self) -> Path:
        return self.shared_dir / "catalog.json"

    @cached_property
    def pricing_path(self) -> Path:
        return self.shared_dir / "pricing.json"
