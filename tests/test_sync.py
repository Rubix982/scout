"""Delta-sync tests (E-002). No network -- rows are passed in directly."""

from __future__ import annotations

import pytest

from src.db.init import get_con, init_tables
from src.db.insert import (
    COMPANIES,
    SheetTable,
    compute_plan,
    fetch_existing,
    normalize,
    sync,
    to_db_row,
)


@pytest.fixture
def db(isolate_database):
    init_tables()
    con = get_con()
    con.execute("DELETE FROM companies")
    return con


def row(name, comments="", link=""):
    return {"Company Name": name, "Comments": comments, "Link": link}


# --- normalization ------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, ""),
        ("", ""),
        ("  wolt  ", "wolt"),
        (True, "TRUE"),
        (False, "FALSE"),
        (42, "42"),
    ],
)
def test_normalize(value, expected):
    assert normalize(value) == expected


def test_normalize_reconciles_sheet_strings_with_duckdb_natives():
    """The regression that made the delta never converge.

    Sheet cells arrive as `"TRUE"`; DuckDB returns `True`. Compared raw they are
    unequal, so every row looked changed on every run and the sync reported 36
    updates forever.
    """
    assert normalize("TRUE") == normalize(True)
    assert normalize("") == normalize(None)


# --- mapping ------------------------------------------------------------------


def test_to_db_row_uses_the_explicit_mapping():
    # No `Type` key in the row, so the entity_type validator yields "unknown"
    # rather than defaulting to "employer" (E-010).
    assert to_db_row(COMPANIES, row("wolt", "note", "http://x")) == {
        "company_name": "wolt",
        "comments": "note",
        "link": "http://x",
        "entity_type": "unknown",
    }


def test_to_db_row_applies_validators():
    r = row("wolt")
    r["Type"] = "  EMPLOYER "
    assert to_db_row(COMPANIES, r)["entity_type"] == "employer"


def test_to_db_row_ignores_unmapped_sheet_columns():
    """A phantom or not-yet-mapped column must not reach the insert."""
    r = row("wolt")
    r[""] = "phantom"
    r["Board URL"] = "http://boards"  # mapped by E-011, not yet
    assert set(to_db_row(COMPANIES, r)) == {
        "company_name",
        "comments",
        "link",
        "entity_type",
    }


def test_compare_columns_excludes_the_primary_key():
    assert COMPANIES.primary_key not in COMPANIES.compare_columns


# --- delta --------------------------------------------------------------------


def test_first_sync_inserts_everything(db):
    plan = sync(COMPANIES, [row("wolt"), row("affirm")])
    assert len(plan.to_insert) == 2
    assert plan.changes == 2
    assert fetch_existing(COMPANIES).keys() == {"wolt", "affirm"}


def test_second_identical_sync_reports_zero_changes(db):
    """E-002 acceptance criterion."""
    rows = [row("wolt", link="http://a"), row("affirm"), row("Checkly", "note")]
    sync(COMPANIES, rows)

    plan = sync(COMPANIES, rows)
    assert plan.changes == 0, (
        f"expected convergence, got +{len(plan.to_insert)} "
        f"~{len(plan.to_update)} -{len(plan.to_delete)}"
    )
    assert plan.unchanged == 3


def test_changed_cell_is_an_update_not_an_insert(db):
    sync(COMPANIES, [row("wolt", link="http://old")])
    plan = sync(COMPANIES, [row("wolt", link="http://new")])
    assert len(plan.to_update) == 1 and not plan.to_insert
    assert fetch_existing(COMPANIES)["wolt"]["link"] == "http://new"


def test_removed_row_is_deleted(db):
    sync(COMPANIES, [row("wolt"), row("affirm")])
    plan = sync(COMPANIES, [row("wolt")])
    assert plan.to_delete == ["affirm"]
    assert fetch_existing(COMPANIES).keys() == {"wolt"}


def test_whitespace_only_change_is_not_a_change(db):
    """Trailing spaces in a cell must not manufacture an update."""
    sync(COMPANIES, [row("wolt", "note")])
    plan = sync(COMPANIES, [row("wolt", "  note  ")])
    assert plan.changes == 0


def test_row_with_empty_company_name_is_skipped(db):
    plan = sync(COMPANIES, [row(""), row("wolt")])
    assert len(plan.to_insert) == 1
    assert fetch_existing(COMPANIES).keys() == {"wolt"}


def test_duplicate_company_keeps_the_first_and_does_not_crash(db):
    plan = sync(COMPANIES, [row("wolt", "first"), row("wolt", "second")])
    assert len(plan.to_insert) == 1
    assert fetch_existing(COMPANIES)["wolt"]["comments"] == "first"


def test_sync_is_idempotent_across_many_runs(db):
    rows = [row(f"c{i}", link=f"http://{i}") for i in range(10)]
    sync(COMPANIES, rows)
    for _ in range(3):
        assert sync(COMPANIES, rows).changes == 0


def test_declarative_spec_works_for_a_different_table(db):
    """The mapping carries the schema, so one code path serves any table."""
    get_con().execute(
        "CREATE TABLE IF NOT EXISTS t_alt (k TEXT PRIMARY KEY, v TEXT)"
    )
    spec = SheetTable(table="t_alt", primary_key="k", columns={"K": "k", "V": "v"})
    plan = sync(spec, [{"K": "a", "V": "1"}])
    assert len(plan.to_insert) == 1
    assert sync(spec, [{"K": "a", "V": "1"}]).changes == 0
