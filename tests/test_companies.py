"""Employer/source partitioning tests (E-010)."""

from __future__ import annotations

import pytest

from src.db import companies as q
from src.db.init import get_con, init_tables
from src.db.insert import COMPANIES, SyncError, sync

ROWS = [
    {"Company Name": "wolt", "Type": "employer", "Comments": "", "Link": ""},
    {"Company Name": "affirm", "Type": "employer", "Comments": "", "Link": ""},
    {"Company Name": "honeypot", "Type": "board", "Comments": "", "Link": ""},
    {"Company Name": "piper", "Type": "agency", "Comments": "", "Link": ""},
    {"Company Name": "foundrgroup", "Type": "investor", "Comments": "", "Link": ""},
    {"Company Name": "buildspace", "Type": "community", "Comments": "", "Link": ""},
    {"Company Name": "soar", "Type": "", "Comments": "", "Link": ""},
]


@pytest.fixture
def seeded(isolate_database):
    init_tables()
    get_con().execute("DELETE FROM companies")
    sync(COMPANIES, ROWS)
    return get_con()


def test_employers_excludes_every_source_kind(seeded):
    assert [c.company_name for c in q.employers()] == ["affirm", "wolt"]


def test_sources_covers_board_agency_investor_community(seeded):
    assert {c.company_name for c in q.sources()} == {
        "honeypot",
        "piper",
        "foundrgroup",
        "buildspace",
    }


def test_blank_type_lands_in_unclassified_not_employers(seeded):
    assert [c.company_name for c in q.unclassified()] == ["soar"]
    assert "soar" not in {c.company_name for c in q.employers()}


def test_the_three_buckets_partition_the_whole_list(seeded):
    """No row may be silently dropped or double-counted."""
    total = len(q.all_companies())
    assert total == len(ROWS)
    assert len(q.employers()) + len(q.sources()) + len(q.unclassified()) == total


def test_counts_by_type_sums_to_total(seeded):
    assert sum(q.counts_by_type().values()) == len(ROWS)


def test_agency_postings_are_not_treated_as_its_own_roles(seeded):
    """R-002 regression: OnHires contributed 47 client roles and Greenhouse-the-
    vendor its own 18, both inflating resolution upward. Typed as sources, they
    are excluded from role tracking entirely."""
    tracked = {c.company_name for c in q.employers()}
    assert "piper" not in tracked and "honeypot" not in tracked


# --- validation ---------------------------------------------------------------


def test_unrecognised_type_fails_the_sync_naming_the_row(seeded):
    with pytest.raises(SyncError) as exc:
        sync(COMPANIES, [{"Company Name": "weird co", "Type": "startup", "Comments": "", "Link": ""}])
    message = str(exc.value)
    assert "weird co" in message
    assert "startup" in message


def test_a_rejected_row_does_not_partially_write(seeded):
    before = {c.company_name for c in q.all_companies()}
    with pytest.raises(SyncError):
        sync(COMPANIES, ROWS + [{"Company Name": "bad", "Type": "nope", "Comments": "", "Link": ""}])
    assert {c.company_name for c in q.all_companies()} == before
