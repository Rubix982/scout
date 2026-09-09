# tests/conftest.py
"""Shared test fixtures.

The previous version inserted `../src` into `sys.path` by hand. That is no longer
needed (and was wrong): `pytest.ini` sets `pythonpath = .`, which puts the project
root on the path so `import src.<pkg>` resolves properly.
"""

from __future__ import annotations

import os

import pytest

_GCP_SECRETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "secrets", "gcp"
)


def gcp_secrets_present() -> bool:
    """True when real Google credentials are available locally."""
    return os.path.isfile(os.path.join(_GCP_SECRETS_DIR, ".env")) and os.path.isfile(
        os.path.join(_GCP_SECRETS_DIR, "gcloud_service_account.json")
    )


requires_gcp_secrets = pytest.mark.skipif(
    not gcp_secrets_present(),
    reason="Google service-account credentials not present in secrets/gcp/",
)


@pytest.fixture(scope="session", autouse=True)
def isolate_database(tmp_path_factory):
    """Point the whole suite at a throwaway database (E-009).

    `tests/test_duckdb.py` used to call `init_tables()` at *import* time against
    `~/.scout/scout.db`, so merely collecting the suite mutated the developer's
    real data. Autouse and session-scoped so it is in place before any test
    imports the storage layer.
    """
    db = tmp_path_factory.mktemp("scout-db") / "test.db"
    os.environ["SCOUT_DB_PATH"] = str(db)

    from src import config
    from src.db import init as db_init

    config.load(force=True)
    db_init.close_con()
    try:
        yield db
    finally:
        db_init.close_con()
