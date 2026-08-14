from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Roof"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 24 * 30  # 30 days

    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'app.db'}"

    uploads_dir: Path = BASE_DIR / "uploads"
    max_upload_mb: int = 10

    cors_origins: str = "*"

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()

# Allow SECRET_KEY env override even when running without .env
if env_secret := os.getenv("SECRET_KEY"):
    settings.secret_key = env_secret
