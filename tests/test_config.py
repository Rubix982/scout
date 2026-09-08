"""E-008 regression tests for the config layer.

The headline test is `test_value_set_only_in_common_env_is_applied`. The original
bug was that `secrets/gcp/common.env` was checked for existence and then never
loaded, so the two sheet-name variables it defines silently never applied.

It survived six months undetected because the values in `common.env` are
byte-identical to the hardcoded fallbacks -- loading the file or not made no
observable difference. So the test deliberately uses a value that is *not* the
default; anything else would pass whether or not the bug is present.
"""

from __future__ import annotations

import os

import pytest

from src import config


@pytest.fixture
def env_sandbox(tmp_path, monkeypatch):
    """Point the config layer at throwaway env files and restore os.environ.

    `load_dotenv` writes straight into `os.environ`, bypassing monkeypatch's
    bookkeeping, so the environment is snapshotted and restored by hand.
    """
    snapshot = dict(os.environ)
    common = tmp_path / "common.env"
    secrets = tmp_path / ".env"
    common.write_text("")
    secrets.write_text("")
    monkeypatch.setattr(config, "COMMON_ENV_FILE", common)
    monkeypatch.setattr(config, "SECRETS_ENV_FILE", secrets)
    monkeypatch.setattr(config, "ENV_FILES", (common, secrets))
    try:
        yield common, secrets
    finally:
        os.environ.clear()
        os.environ.update(snapshot)
        config.load(force=True)


def test_value_set_only_in_common_env_is_applied(env_sandbox):
    """A setting defined only in common.env must reach the application."""
    common, _ = env_sandbox
    common.write_text('COMPANY_RESEARCH_SHEET_NAME="Deliberately Not The Default"\n')
    os.environ.pop("COMPANY_RESEARCH_SHEET_NAME", None)
    config.load(force=True)

    assert config.get(config.COMPANY_RESEARCH_SHEET_NAME) == (
        "Deliberately Not The Default"
    )


def test_secrets_env_overrides_common_env(env_sandbox):
    """Documented precedence: .env wins over common.env."""
    common, secrets = env_sandbox
    common.write_text("COMPANIES_SHEET_NAME=from_common\n")
    secrets.write_text("COMPANIES_SHEET_NAME=from_secrets\n")
    os.environ.pop("COMPANIES_SHEET_NAME", None)
    config.load(force=True)

    assert config.get(config.COMPANIES_SHEET_NAME) == "from_secrets"


def test_missing_required_setting_names_the_variable_and_file(env_sandbox):
    """A required setting must fail with an actionable message, not a bare
    FileNotFoundError."""
    os.environ.pop("SHEET_URL", None)
    config.load(force=True)

    with pytest.raises(config.ConfigError) as exc:
        config.sheet_url()

    message = str(exc.value)
    assert "SHEET_URL" in message
    assert ".env" in message


def test_defaulted_setting_falls_back_silently(env_sandbox):
    os.environ.pop("LOG_LEVEL", None)
    config.load(force=True)
    assert config.get(config.LOG_LEVEL) == "DEBUG"


def test_malformed_integer_setting_is_rejected(env_sandbox):
    _, secrets = env_sandbox
    secrets.write_text("LOG_BACKUP_COUNT=not_a_number\n")
    config.load(force=True)

    with pytest.raises(config.ConfigError) as exc:
        config.get_int(config.LOG_BACKUP_COUNT)
    assert "LOG_BACKUP_COUNT" in str(exc.value)


def test_db_path_is_overridable(env_sandbox, tmp_path):
    """Tests must be able to point storage away from the real database."""
    target = tmp_path / "nested" / "test.db"
    os.environ["SCOUT_DB_PATH"] = str(target)
    config.load(force=True)

    assert config.db_path() == target
    assert target.parent.is_dir(), "parent directory should be created on demand"


def test_missing_env_files_are_not_an_error(env_sandbox):
    """Absence of an env file is only a problem if a required value is unset."""
    common, secrets = env_sandbox
    common.unlink()
    secrets.unlink()
    config.load(force=True)
    assert config.get(config.LOG_LEVEL) == "DEBUG"
