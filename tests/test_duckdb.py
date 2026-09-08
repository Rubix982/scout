"""Schema and migration tests (E-009)."""

from __future__ import annotations

import duckdb
import pytest

from src.db.init import get_con, init_tables, schema_version
from src.db.migrations import MIGRATIONS, apply_pending, current_version

BASELINE_TABLES = {
    "company_research",
    "processed_companies",
    "company_contacts",
    "contact_profiles",
    "email_drafts",
    "replies_log",
    "api_errors_log",
    "send_log",
}
EXPECTED_TABLES = BASELINE_TABLES | {"schema_version"}


def _tables(con: duckdb.DuckDBPyConnection) -> set[str]:
    return {row[0] for row in con.execute("SHOW TABLES").fetchall()}


@pytest.fixture
def migrated_db(isolate_database):
    init_tables()
    return get_con()


def test_expected_tables_exist(migrated_db):
    """`company_research` was previously missing from this assertion, so the test
    would have passed against an incomplete schema."""
    missing = EXPECTED_TABLES - _tables(migrated_db)
    assert not missing, f"Missing tables: {missing}"


def test_schema_is_at_latest_version(migrated_db):
    assert schema_version() == max(m.version for m in MIGRATIONS)


def test_migrations_are_idempotent(migrated_db):
    """Running migrations twice must be a no-op, not an error."""
    before = _tables(migrated_db)
    applied = apply_pending(migrated_db)
    assert applied == []
    assert _tables(migrated_db) == before


def test_migration_versions_are_unique_and_ordered():
    versions = [m.version for m in MIGRATIONS]
    assert versions == sorted(versions), "MIGRATIONS must be in ascending order"
    assert len(versions) == len(set(versions)), "duplicate migration version"


def test_fresh_and_preexisting_databases_converge(tmp_path):
    """A database created by the pre-migration `init_tables()` must end up with
    the same schema as a freshly-migrated one.

    Simulates the legacy path: baseline tables present, no `schema_version`.
    """
    fresh = duckdb.connect(str(tmp_path / "fresh.db"))
    apply_pending(fresh)

    legacy = duckdb.connect(str(tmp_path / "legacy.db"))
    for statement in MIGRATIONS[0].statements:
        legacy.execute(statement)
    assert "schema_version" not in _tables(legacy)
    assert current_version(legacy) == 0

    applied = apply_pending(legacy)
    assert [m.version for m in applied] == [1]

    assert _tables(legacy) == _tables(fresh)
    assert current_version(legacy) == current_version(fresh)

    fresh.close()
    legacy.close()


def test_failed_migration_rolls_back(tmp_path):
    """A migration that raises must leave no partial schema behind."""
    from src.db.migrations import Migration

    con = duckdb.connect(str(tmp_path / "rollback.db"))
    current_version(con)  # create schema_version

    bad = Migration(
        version=999,
        name="deliberately_broken",
        statements=(
            "CREATE TABLE should_not_survive (x INTEGER);",
            "THIS IS NOT VALID SQL;",
        ),
    )
    import src.db.migrations as mig

    original = mig.MIGRATIONS
    mig.MIGRATIONS = original + (bad,)
    try:
        with pytest.raises(Exception):
            apply_pending(con)
    finally:
        mig.MIGRATIONS = original

    assert "should_not_survive" not in _tables(con)
    assert current_version(con) != 999
    con.close()
