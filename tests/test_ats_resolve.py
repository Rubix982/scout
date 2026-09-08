"""Board resolution from user-supplied URLs (E-011). No network -- fetcher injected."""

from __future__ import annotations

import json

import pytest

from src.db.companies import Company, employers
from src.db.init import get_con, init_tables
from src.db.insert import COMPANIES, sync
from src.sources.ats.platforms import Platform
from src.sources.ats.resolve import (
    Reason,
    Status,
    resolve_all_employers,
    resolve_company,
    validate,
)


def greenhouse_body(n):
    return json.dumps({"jobs": list(range(n)), "meta": {"total": n}}).encode()


def fetcher(status=200, body=b"", calls=None):
    def _fetch(url):
        if calls is not None:
            calls.append(url)
        return status, body
    return _fetch


def company(name, board_url="", entity_type="employer"):
    return Company(
        company_name=name, entity_type=entity_type, comments="", link="",
        board_url=board_url,
    )


# --- validation ---------------------------------------------------------------


def test_resolves_when_the_board_returns_roles():
    c = company("wolt", "https://boards.greenhouse.io/wolt")
    r = resolve_company(c, fetch=fetcher(200, greenhouse_body(242)))
    assert r.status is Status.RESOLVED
    assert (r.platform, r.token, r.role_count) == (Platform.GREENHOUSE, "wolt", 242)
    assert r.reason is None
    assert r.method == "manual"


def test_two_hundred_with_zero_roles_is_not_a_resolution():
    """Content-based validation. A 200 alone means nothing -- SmartRecruiters
    returns it for companies that do not exist (R-001)."""
    c = company("ghost", "https://boards.greenhouse.io/ghost")
    r = resolve_company(c, fetch=fetcher(200, greenhouse_body(0)))
    assert r.status is Status.UNRESOLVED
    assert r.reason is Reason.BOARD_EMPTY


def test_dead_board_is_unreachable_not_empty():
    """A token that used to work and now 404s -- strapi's Lever board (R-002)."""
    c = company("strapi", "https://jobs.lever.co/strapi")
    r = resolve_company(c, fetch=fetcher(404, b""))
    assert r.reason is Reason.BOARD_UNREACHABLE
    assert r.token == "strapi", "the parsed token is retained for diagnosis"


def test_transport_error_is_unreachable():
    c = company("wolt", "https://boards.greenhouse.io/wolt")
    r = resolve_company(c, fetch=fetcher(None, b""))
    assert r.reason is Reason.BOARD_UNREACHABLE


def test_marker_only_url_reports_missing_token():
    c = company("fingerprint", "https://fingerprint.com/careers/?gh_jid=5361182004")
    r = resolve_company(c, fetch=fetcher(200, greenhouse_body(23)))
    assert r.reason is Reason.NO_TOKEN_IN_URL
    assert r.platform is Platform.GREENHOUSE


def test_recognised_but_unsupported_platform_says_so():
    """Distinguishing 'we know what they use but cannot read it' from 'we have no
    idea' is the whole reason patterns are broader than adapters."""
    c = company("everli", "https://everli.applytojob.com")
    r = resolve_company(c, fetch=fetcher(200, b"{}"))
    assert r.reason is Reason.PLATFORM_UNSUPPORTED
    assert r.platform is Platform.JAZZHR


def test_blank_board_url_needs_no_network():
    calls = []
    r = resolve_company(company("Clari", ""), fetch=fetcher(200, b"{}", calls))
    assert r.reason is Reason.NO_BOARD_URL
    assert calls == [], "must not call the API when there is nothing to check"


def test_unrecognised_url_is_distinct_from_missing_one():
    r = resolve_company(company("soar", "https://soar.com/careers"), fetch=fetcher())
    assert r.reason is Reason.UNRECOGNISED_URL


def test_every_reason_has_an_explanation():
    """The explanation is what the user actually reads, so a new Reason without
    one would print an empty string next to the company name."""
    from src.sources.ats.resolve import EXPLANATIONS

    assert set(EXPLANATIONS) == set(Reason)
    assert all(EXPLANATIONS[r].strip() for r in Reason)


def test_validate_skips_the_call_for_an_unsupported_platform():
    from src.sources.ats.platforms import ParsedBoard
    calls = []
    ok, count, reason = validate(
        ParsedBoard(Platform.RIPPLING, "fabric"), fetch=fetcher(200, b"{}", calls)
    )
    assert (ok, reason) == (False, Reason.PLATFORM_UNSUPPORTED)
    assert calls == []


# --- persistence --------------------------------------------------------------


ROWS = [
    {"Company Name": "wolt", "Type": "employer", "Comments": "", "Link": "",
     "Board URL": "https://boards.greenhouse.io/wolt"},
    {"Company Name": "Clari", "Type": "employer", "Comments": "", "Link": "",
     "Board URL": ""},
    {"Company Name": "everli", "Type": "employer", "Comments": "", "Link": "",
     "Board URL": "https://everli.applytojob.com"},
    {"Company Name": "honeypot", "Type": "board", "Comments": "", "Link": "",
     "Board URL": "https://boards.greenhouse.io/honeypot"},
]


@pytest.fixture
def seeded(isolate_database):
    init_tables()
    con = get_con()
    con.execute("DELETE FROM companies")
    con.execute("DELETE FROM company_ats")
    sync(COMPANIES, ROWS)
    return con


def test_unresolved_employers_are_recorded_never_omitted(seeded):
    """The central guarantee of the R-002 re-pass.

    Overstating coverage is the failure this whole design exists to prevent, so
    every employer must appear in company_ats -- resolved or not.
    """
    results = resolve_all_employers(fetch=fetcher(200, greenhouse_body(242)))
    stored = {r[0] for r in seeded.execute("SELECT company_name FROM company_ats").fetchall()}
    assert stored == {c.company_name for c in employers()}
    assert len(results) == 3


def test_sources_are_not_resolved_at_all(seeded):
    """honeypot is typed `board` and has a plausible Greenhouse URL. It must be
    ignored: a job board's postings are not its own roles."""
    resolve_all_employers(fetch=fetcher(200, greenhouse_body(5)))
    stored = {r[0] for r in seeded.execute("SELECT company_name FROM company_ats").fetchall()}
    assert "honeypot" not in stored


def test_recorded_rows_carry_status_reason_and_method(seeded):
    resolve_all_employers(fetch=fetcher(200, greenhouse_body(242)))
    rows = dict(
        (r[0], r[1:])
        for r in seeded.execute(
            "SELECT company_name, status, reason, resolution_method, last_role_count "
            "FROM company_ats"
        ).fetchall()
    )
    assert rows["wolt"] == ("resolved", None, "manual", 242)
    assert rows["Clari"][:2] == ("unresolved", "no_board_url")
    assert rows["everli"][:2] == ("unresolved", "platform_unsupported")


def test_resolution_is_idempotent(seeded):
    resolve_all_employers(fetch=fetcher(200, greenhouse_body(242)))
    before = seeded.execute("SELECT count(*) FROM company_ats").fetchone()[0]
    resolve_all_employers(fetch=fetcher(200, greenhouse_body(242)))
    assert seeded.execute("SELECT count(*) FROM company_ats").fetchone()[0] == before


def test_a_board_going_dead_flips_status_back_to_unresolved(seeded):
    """R-002 found strapi's Lever board dead within ~6 months. A previously
    resolved company must not keep a stale `resolved` row."""
    resolve_all_employers(fetch=fetcher(200, greenhouse_body(242)))
    assert seeded.execute(
        "SELECT status FROM company_ats WHERE company_name = 'wolt'"
    ).fetchone()[0] == "resolved"

    resolve_all_employers(fetch=fetcher(404, b""))
    status, reason = seeded.execute(
        "SELECT status, reason FROM company_ats WHERE company_name = 'wolt'"
    ).fetchone()
    assert (status, reason) == ("unresolved", "board_unreachable")
