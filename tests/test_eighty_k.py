"""80,000 Hours role feed (E-012). No network -- page fetcher injected."""

from __future__ import annotations

import json

import pytest

from src.common.models import Role
from src.db import companies as company_queries
from src.db.init import get_con, init_tables
from src.db.insert import COMPANIES, sync
from src.db.roles import open_role_count, snapshot_company, start_run
from src.sources.eighty_k.feed import (
    SOURCE,
    fetch_all_roles,
    parse_hits,
    run_feed_snapshot,
)

HIT = {
    "post_pk": 20917,
    "objectID": "20917",
    "title": "Executive Assistant, EU Law and Legal Frontiers",
    "company_id": "institute-for-law-and-ai",
    "company_name": "Institute for Law and AI",
    "url_external": "https://law-ai.org/career/exa-eu-lf/",
    "posted_at": 1788912300,
    "created_at": 1788952762,
    "updated_at": 1789018304,
    "card_locations": ["Cambridge, UK"],
    "tags_city": ["Cambridge, UK"],
    "tags_skill": ["Operations", "Legal"],
    "evergreen": False,
}


def page(hits, nb_pages=1):
    return 200, json.dumps({"hits": hits, "nbPages": nb_pages}).encode()


# --- normalisation ------------------------------------------------------------


def test_maps_the_documented_fields():
    (role,) = parse_hits([HIT])
    assert role.platform == SOURCE
    assert role.token == "institute-for-law-and-ai"
    assert role.external_id == "20917"
    assert role.title.startswith("Executive Assistant")
    assert role.location == "Cambridge, UK"
    assert role.url == "https://law-ai.org/career/exa-eu-lf/"


def test_epoch_seconds_become_iso():
    (role,) = parse_hits([HIT])
    assert role.first_published and role.first_published.startswith("2026-")
    assert role.updated_at and role.updated_at.startswith("2026-")


def test_department_is_left_empty_and_tags_are_kept_separate():
    """The construct-validity rule: 53% of 80k roles carry more than one skill
    tag, so tags are multi-label while ATS departments partition. Writing tags
    into `department` would make the two silently incomparable.
    """
    (role,) = parse_hits([HIT])
    assert role.department == ""
    assert role.tags == ("Operations", "Legal")


def test_source_evergreen_flag_overrides_the_title_heuristic():
    """80k states evergreen per role; the heuristic is only a fallback."""
    looks_evergreen = dict(HIT, title="Join our Talent Community", evergreen=False)
    (role,) = parse_hits([looks_evergreen])
    assert role.evergreen_flag is False
    assert role.is_evergreen is False, "source flag must win over the title guess"

    plain_title = dict(HIT, title="Senior Engineer", evergreen=True)
    (role,) = parse_hits([plain_title])
    assert role.is_evergreen is True


def test_missing_flag_falls_back_to_the_heuristic():
    hit = {k: v for k, v in HIT.items() if k != "evergreen"}
    (role,) = parse_hits([dict(hit, title="Join our Talent Community")])
    assert role.evergreen_flag is None
    assert role.is_evergreen is True


def test_platform_never_collides_with_an_ats_role():
    (feed_role,) = parse_hits([HIT])
    ats_role = Role(
        platform="greenhouse", token="institute-for-law-and-ai",
        external_id="20917", title="x", location="", department="", url="",
        first_published=None, updated_at=None, raw="{}",
    )
    assert feed_role.identity != ats_role.identity


@pytest.mark.parametrize("bad", [{}, {"post_pk": 1}, {"company_id": "x"}, "junk", 42])
def test_hits_without_id_or_company_are_skipped(bad):
    assert parse_hits([bad]) == []


# --- pagination and failure ---------------------------------------------------


def test_paginates_until_the_last_page():
    calls = []

    def fetch(p):
        calls.append(p)
        return page([dict(HIT, post_pk=100 + p)], nb_pages=3)

    ok, roles = fetch_all_roles(fetch)
    assert ok and calls == [0, 1, 2]
    assert len(roles) == 3


def test_a_failed_page_aborts_and_returns_nothing():
    """A partial feed must not look complete: the missing pages' roles would
    otherwise be closed as though the source had dropped them."""
    def fetch(p):
        return page([HIT], nb_pages=3) if p == 0 else (500, b"")

    ok, roles = fetch_all_roles(fetch)
    assert ok is False
    assert roles == []


def test_unparseable_body_aborts():
    ok, roles = fetch_all_roles(lambda p: (200, b"not json"))
    assert ok is False and roles == []


def test_transport_error_aborts():
    ok, roles = fetch_all_roles(lambda p: (None, b""))
    assert ok is False and roles == []


# --- snapshot integration -----------------------------------------------------


@pytest.fixture
def db(isolate_database):
    init_tables()
    con = get_con()
    for t in ("roles", "role_changes", "runs", "company_ats", "companies"):
        con.execute(f"DELETE FROM {t}")
    return con


def test_feed_snapshot_ingests_and_registers_companies(db):
    ok, changes, n = run_feed_snapshot(start_run(), lambda p: page([HIT]))
    assert ok and n == 1
    assert len(changes) == 1
    assert open_role_count() == 1
    assert [c.company_name for c in company_queries.employers_from(SOURCE)] == [
        "Institute for Law and AI"
    ]


def test_a_failed_feed_closes_nothing(db):
    run_feed_snapshot(start_run(), lambda p: page([HIT]))
    assert open_role_count() == 1

    ok, changes, n = run_feed_snapshot(start_run(), lambda p: (500, b""))
    assert ok is False and changes == []
    assert open_role_count() == 1, "a failed feed fetch closed roles"


def test_a_role_dropped_from_the_feed_is_closed(db):
    run_feed_snapshot(start_run(), lambda p: page([HIT, dict(HIT, post_pk=999)]))
    assert open_role_count() == 2

    ok, changes, _ = run_feed_snapshot(start_run(), lambda p: page([HIT]))
    assert ok
    assert [c.change_type.value for c in changes] == ["closed"]
    assert open_role_count() == 1


def test_a_company_vanishing_entirely_has_its_roles_closed(db):
    """Source-level close: the feed is fetched whole, so absence is real."""
    other = dict(HIT, post_pk=555, company_id="other-org", company_name="Other Org")
    run_feed_snapshot(start_run(), lambda p: page([HIT, other]))
    assert open_role_count() == 2

    run_feed_snapshot(start_run(), lambda p: page([HIT]))
    assert open_role_count("Other Org") == 0
    assert open_role_count("Institute for Law and AI") == 1


def test_identical_second_feed_run_reports_no_changes(db):
    run_feed_snapshot(start_run(), lambda p: page([HIT]))
    ok, changes, _ = run_feed_snapshot(start_run(), lambda p: page([HIT]))
    assert ok and changes == []


# --- the sync-safety invariant ------------------------------------------------


def test_sheet_sync_does_not_delete_feed_discovered_companies(db):
    """Without `companies.source` scoping, `compute_plan` would delete every
    discovered company as "absent from the sheet" on the next sync -- silently
    destroying hundreds of rows.
    """
    run_feed_snapshot(start_run(), lambda p: page([HIT]))
    sync(COMPANIES, [{"Company Name": "wolt", "Type": "employer",
                      "Comments": "", "Link": "", "Board URL": ""}])

    names = {c.company_name for c in company_queries.all_companies()}
    assert "Institute for Law and AI" in names, "feed company was deleted by sync"
    assert "wolt" in names


def test_sheet_sync_still_deletes_its_own_removed_rows(db):
    """The ownership guard must not make the sync inert."""
    rows = [{"Company Name": n, "Type": "employer", "Comments": "", "Link": "",
             "Board URL": ""} for n in ("wolt", "affirm")]
    sync(COMPANIES, rows)
    plan = sync(COMPANIES, rows[:1])
    assert plan.to_delete == ["affirm"]


def test_feed_companies_are_excluded_from_ats_resolution(db):
    """386 feed organisations must not each produce an `unresolved / no_board_url`
    row -- that would drown the coverage report in false negatives."""
    run_feed_snapshot(start_run(), lambda p: page([HIT]))
    sync(COMPANIES, [{"Company Name": "wolt", "Type": "employer",
                      "Comments": "", "Link": "", "Board URL": ""}])

    eligible = {c.company_name for c in company_queries.employers_needing_resolution()}
    assert eligible == {"wolt"}


def test_a_feed_company_given_a_board_url_becomes_eligible(db):
    """The rule is "sheet-owned OR has a board URL", so a discovered company can
    be promoted to first-party tracking later."""
    run_feed_snapshot(start_run(), lambda p: page([HIT]))
    get_con().execute(
        "UPDATE companies SET board_url = 'https://boards.greenhouse.io/x' "
        "WHERE company_name = 'Institute for Law and AI'"
    )
    eligible = {c.company_name for c in company_queries.employers_needing_resolution()}
    assert "Institute for Law and AI" in eligible


def test_run_snapshot_does_not_touch_the_network_by_default(db, monkeypatch):
    """Guard for the regression above: a library call must not reach out unasked.

    Both real fetchers are replaced with tripwires; `run_snapshot()` with no
    arguments must complete without calling either.
    """
    import src.sources.ats.resolve as resolve_mod
    import src.sources.eighty_k.feed as feed_mod
    from src.sources.ats.snapshot import run_snapshot

    def tripwire(*args, **kwargs):
        raise AssertionError("unexpected network call from run_snapshot()")

    monkeypatch.setattr(feed_mod, "http_page_fetcher", tripwire)
    monkeypatch.setattr(resolve_mod, "http_fetch", tripwire)

    report = run_snapshot()
    assert report.feed_ok is None, "feed must be off unless explicitly requested"
    assert report.outcomes == []
