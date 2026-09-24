from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import Target


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    vfs_dashboard_url: str = "https://visa.vfsglobal.com/rus/ru/fra/dashboard"
    vfs_email: str | None = None
    vfs_password: SecretStr | None = None

    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None

    headless: bool = True
    locale: str = "ru-RU"
    timezone: str = "Europe/Moscow"
    cdp_url: str = "http://127.0.0.1:9222"
    check_interval_seconds: int = Field(default=120, ge=30)
    check_jitter_seconds: int = Field(default=30, ge=0, le=900)
    navigation_timeout_ms: int = Field(default=45_000, ge=5_000)
    action_timeout_ms: int = Field(default=15_000, ge=3_000)
    heartbeat_hours: int = Field(default=6, ge=1, le=72)

    targets_path: Path = Path("targets.yml")
    database_path: Path = Path(".data/state.db")
    storage_state_path: Path = Path(".data/vfs-storage-state.json")
    debug_dir: Path = Path(".data/debug")


class TargetsDocument(BaseModel):
    targets: list[Target]


def load_targets(path: Path) -> list[Target]:
    if not path.exists():
        raise FileNotFoundError(
            f"Targets file not found: {path}. Copy targets.example.yml to targets.yml first."
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    document = TargetsDocument.model_validate(data)
    enabled = [target for target in document.targets if target.enabled]
    if not enabled:
        raise ValueError("No enabled targets configured")
    return enabled
