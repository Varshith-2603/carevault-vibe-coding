"""Runtime settings, read once from environment variables.

Nothing secret lives in source code. Every value has a safe local default so the
app runs out of the box; production deployments override them (see README).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    base_url: str
    production: bool
    enable_demo: bool
    pbkdf2_iterations: int
    session_timeout_min: int
    max_upload_mb: int
    max_login_attempts: int
    lockout_minutes: int
    ai_model: str

    @property
    def db_path(self) -> Path:
        return self.data_dir / "medione.db"

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"

    @property
    def key_file(self) -> Path:
        return self.data_dir / "secret.key"


def load_settings() -> Settings:
    production = os.environ.get("MEDIONE_ENV", "development").lower() == "production"
    return Settings(
        data_dir=Path(os.environ.get("MEDIONE_DATA_DIR", ROOT / "instance")),
        base_url=os.environ.get("MEDIONE_BASE_URL", "http://localhost:8501").rstrip("/"),
        production=production,
        enable_demo=_bool("MEDIONE_ENABLE_DEMO", not production),
        pbkdf2_iterations=_int("MEDIONE_PBKDF2_ITERATIONS", 600_000),
        session_timeout_min=_int("MEDIONE_SESSION_TIMEOUT_MIN", 30),
        max_upload_mb=_int("MEDIONE_MAX_UPLOAD_MB", 15),
        max_login_attempts=_int("MEDIONE_MAX_LOGIN_ATTEMPTS", 5),
        lockout_minutes=_int("MEDIONE_LOCKOUT_MINUTES", 15),
        ai_model=os.environ.get("MEDIONE_AI_MODEL", "claude-opus-5-5"),
    )


settings = load_settings()


def reload_settings() -> Settings:
    """Re-read the environment (used by tests that point the app at a temp folder)."""
    global settings
    settings = load_settings()
    return settings
