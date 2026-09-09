# src/config.py
"""Single owner of configuration.

Before this module, config was read from three places with no owner: `gsuite.py`
called `os.getenv` at call time, `log/config.py` read three variables at import
time, `global.env` existed and was loaded by nothing, and
`secrets/gcp/common.env` was *validated but never loaded* -- so the two sheet-name
variables it defines silently never applied.

Precedence, later wins:

1. ``secrets/gcp/common.env``  -- shared non-secret defaults, committed
2. ``secrets/gcp/.env``        -- local secrets, git-ignored
3. the real process environment

Loading happens once, on first access, never at import (E-001's invariant).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GCP_SECRETS_DIR = PROJECT_ROOT / "secrets" / "gcp"
COMMON_ENV_FILE = GCP_SECRETS_DIR / "common.env"
SECRETS_ENV_FILE = GCP_SECRETS_DIR / ".env"

# Loaded in order; later files override earlier ones. A missing file is not an
# error here -- absence is only an error when a *required* value turns out to be
# unset, which produces a far more useful message than "file not found".
ENV_FILES = (COMMON_ENV_FILE, SECRETS_ENV_FILE)


class ConfigError(RuntimeError):
    """Raised when a required setting is missing or malformed."""


@dataclass(frozen=True)
class Setting:
    """One configuration variable and where a human should go to set it."""

    name: str
    belongs_in: str
    default: Optional[str] = None

    @property
    def required(self) -> bool:
        return self.default is None


SHEET_URL = Setting("SHEET_URL", str(SECRETS_ENV_FILE))
SERVICE_ACCOUNT_FILENAME = Setting(
    "GCLOUD_SERVICE_ACCOUNT_FILENAME",
    str(SECRETS_ENV_FILE),
    default="gcloud_service_account.json",
)
COMPANY_RESEARCH_SHEET_NAME = Setting(
    "COMPANY_RESEARCH_SHEET_NAME", str(COMMON_ENV_FILE), default="Company Research"
)
PROCESSED_COMPANIES_SHEET_NAME = Setting(
    "PROCESSED_COMPANIES_SHEET_NAME",
    str(COMMON_ENV_FILE),
    default="Processed Companies",
)
COMPANIES_SHEET_NAME = Setting(
    "COMPANIES_SHEET_NAME", str(COMMON_ENV_FILE), default="Sheet1"
)
DB_PATH = Setting("SCOUT_DB_PATH", "the environment", default="")
LOG_LEVEL = Setting("LOG_LEVEL", "the environment", default="DEBUG")
LOG_MAX_BYTES = Setting("LOG_MAX_BYTES", "the environment", default=str(5 * 1024 * 1024))
LOG_BACKUP_COUNT = Setting("LOG_BACKUP_COUNT", "the environment", default="2")

_loaded = False


def load(force: bool = False) -> None:
    """Load env files once. Idempotent; safe to call from anywhere."""
    global _loaded
    if _loaded and not force:
        return
    for path in ENV_FILES:
        if path.is_file():
            # override=True so that a later file genuinely wins over an earlier
            # one. python-dotenv defaults to override=False, which would make
            # `.env` unable to override `common.env` -- the opposite of the
            # documented precedence.
            load_dotenv(path, override=True)
    _loaded = True


def get(setting: Setting) -> str:
    """Return a setting's value, or raise ConfigError naming where to set it."""
    load()
    value = os.getenv(setting.name)
    if value is not None and value != "":
        return value
    if setting.required:
        raise ConfigError(
            f"{setting.name} is not set. Add it to {setting.belongs_in} "
            f"(see secrets/gcp/example.env for the expected shape)."
        )
    return setting.default or ""


def get_int(setting: Setting) -> int:
    raw = get(setting)
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(
            f"{setting.name} must be an integer, got {raw!r}. "
            f"Set it in {setting.belongs_in}."
        ) from exc


def sheet_url() -> str:
    return get(SHEET_URL)


def service_account_path() -> Path:
    """Resolve and verify the service-account JSON path."""
    path = GCP_SECRETS_DIR / get(SERVICE_ACCOUNT_FILENAME)
    if not path.is_file():
        raise ConfigError(
            f"Service account file not found: {path}. "
            f"Download it from GCP (see docs/google_auth_setup.md) or set "
            f"{SERVICE_ACCOUNT_FILENAME.name} in {SERVICE_ACCOUNT_FILENAME.belongs_in}."
        )
    return path


def db_path() -> Path:
    """Database location. Overridable via SCOUT_DB_PATH so tests never touch
    the developer's real database."""
    override = get(DB_PATH)
    path = Path(override).expanduser() if override else Path.home() / ".scout" / "scout.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def describe() -> Dict[str, str]:
    """Current resolved config, for diagnostics. Never includes secret values."""
    load()
    return {
        "env_files_loaded": ", ".join(str(p) for p in ENV_FILES if p.is_file()) or "none",
        "SHEET_URL": "set" if os.getenv(SHEET_URL.name) else "MISSING (required)",
        COMPANY_RESEARCH_SHEET_NAME.name: get(COMPANY_RESEARCH_SHEET_NAME),
        PROCESSED_COMPANIES_SHEET_NAME.name: get(PROCESSED_COMPANIES_SHEET_NAME),
        COMPANIES_SHEET_NAME.name: get(COMPANIES_SHEET_NAME),
        "db_path": str(db_path()),
        LOG_LEVEL.name: get(LOG_LEVEL),
    }
