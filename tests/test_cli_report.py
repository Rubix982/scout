"""Report CLI and evergreen detection (E-006). No network."""

from __future__ import annotations

import pytest

from src.cli import build_parser, cmd_report, main
from src.common.models import Role, is_evergreen
from src.db.init import get_con, init_tables
from src.db.roles import finish_run, snapshot_company, start_run


# --- evergreen detection ------------------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        "Don't see the role you're looking for? Join our Talent Community!",
        "Dont see the role you are looking for?",
        "Join our Talent Network",
        "General Application",
        "Speculative application - Engineering",
        "Future Opportunities at Acme",
        "Expression of interest",
        "Can't find the role you want?",
        "TALENT POOL",
    ],
)
def test_evergreen_titles_are_flagged(title):
    assert is_evergreen(title)


@pytest.mark.parametrize(
    "title",
    [
        "Senior Backend Engineer",
        "Product Manager (DevTools & AI Reliability, remote)",
        "Grocery Associate",
        "Talent Acquisition Partner",       # a real recruiting job
        "Head of Talent",                    # also real
        "Community Manager",                 # real, despite 'community'
        "Application Security Engineer",     # real, despite 'application'
        "",
    ],
)
def test_real_roles_are_not_flagged(title):
    """The heuristic runs on free text, so the false-positive cases matter as
    much as the true ones -- 'Talent Acquisition Partner' and 'Community
    Manager' are real jobs."""
    assert not is_evergreen(title)


def test_role_exposes_the_flag():
    role = Role(
        platform="ashby", token="checkly", external_id="1",
        title="Join our Talent Community", location="Remote", department="",
        url="", first_published=None, updated_at=None, raw="{}",
    )
    assert role.is_evergreen


# --- report -------------------------------------------------------------------


def role(external_id, title="Engineer", department="Engineering", company="acme"):
    return Role(
        platform="greenhouse", token=company, external_id=str(external_id),
        title=title, location="Remote", department=department,
        url=f"https://example/{external_id}", first_published=None,
        updated_at=None, raw="{}",
    )


@pytest.fixture
def db(isolate_database):
    init_tables()
    con = get_con()
    for t in ("roles", "role_changes", "runs", "company_ats", "companies"):
        con.execute(f"DELETE FROM {t}")
    return con


def seed_company(con, name, entity_type="employer", status="resolved", reason=None):
    con.execute(
        "INSERT OR REPLACE INTO companies (company_name, comments, link, entity_type, board_url) "
        "VALUES (?, '', '', ?, '')", [name, entity_type]
    )
    if entity_type == "employer":
        con.execute(
            "INSERT OR REPLACE INTO company_ats "
            "(company_name, platform, token, status, reason, resolution_method) "
            "VALUES (?, 'greenhouse', ?, ?, ?, 'manual')",
            [name, name, status, reason],
        )


def test_report_refuses_politely_with_no_completed_runs(db, capsys):
    assert cmd_report(None) == 1
    assert "No completed runs yet" in capsys.readouterr().out


def test_first_run_says_it_is_a_baseline(db, capsys):
    seed_company(db, "acme")
    run = start_run()
    snapshot_company(run, "acme", [role(1)])
    finish_run(run, attempted=1, fetched=1, failed=0, roles_seen=1)

    assert cmd_report(None) == 0
    out = capsys.readouterr().out
    assert "first completed run" in out
    assert "establishes the baseline" in out


def test_report_states_coverage_including_what_it_cannot_see(db, capsys):
    seed_company(db, "acme")
    seed_company(db, "blind", status="unresolved", reason="no_board_url")
    seed_company(db, "honeypot", entity_type="board")
    seed_company(db, "dunno", entity_type="unknown")
    run = start_run()
    snapshot_company(run, "acme", [role(1)])
    finish_run(run, attempted=1, fetched=1, failed=0, roles_seen=1)

    cmd_report(None)
    out = capsys.readouterr().out
    assert "Coverage" in out
    assert "sources excluded       " in out
    assert "unclassified" in out
    assert "Employers Scout cannot see (1)" in out
    assert "no_board_url" in out


def test_evergreen_postings_are_excluded_from_counts_but_reported(db, capsys):
    seed_company(db, "acme")
    run = start_run()
    snapshot_company(run, "acme", [
        role(1, title="Senior Engineer"),
        role(2, title="Join our Talent Community"),
    ])
    finish_run(run, attempted=1, fetched=1, failed=0, roles_seen=2)

    cmd_report(None)
    out = capsys.readouterr().out
    assert "(1 open roles)" in out, "evergreen posting must not count as a vacancy"
    assert "1 talent-pool posting(s) set aside" in out


def test_mix_is_reported_as_shares_with_the_caveat(db, capsys):
    seed_company(db, "acme")
    run = start_run()
    snapshot_company(run, "acme", [
        role(1, department="Engineering"), role(2, department="Engineering"),
        role(3, department="Engineering"), role(4, department="Sales"),
    ])
    finish_run(run, attempted=1, fetched=1, failed=0, roles_seen=4)

    cmd_report(None)
    out = capsys.readouterr().out
    assert "share of open roles" in out
    assert "would compare headcount rather than focus" in out
    assert "75.0%" in out and "25.0%" in out


def test_changes_since_the_previous_run_are_listed(db, capsys):
    seed_company(db, "acme")
    first = start_run()
    snapshot_company(first, "acme", [role(1, title="Engineer")])
    finish_run(first, attempted=1, fetched=1, failed=0, roles_seen=1)

    second = start_run()
    snapshot_company(second, "acme", [role(1, title="Engineer"), role(2, title="Designer")])
    finish_run(second, attempted=1, fetched=1, failed=0, roles_seen=2)

    cmd_report(None)
    out = capsys.readouterr().out
    assert f"Since run {first}" in out
    assert "New roles (1)" in out
    assert "Designer" in out


def test_a_failed_board_is_warned_about_in_the_header(db, capsys):
    seed_company(db, "acme")
    run = start_run()
    snapshot_company(run, "acme", [role(1)])
    finish_run(run, attempted=2, fetched=1, failed=1, roles_seen=1)

    cmd_report(None)
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "left untouched rather than closed" in out


def test_report_makes_no_trend_claim(db, capsys):
    """v1 deliberately reports state and deltas only. A trend claim needs months
    of history to beat 'the company simply posts a lot of everything'."""
    seed_company(db, "acme")
    run = start_run()
    snapshot_company(run, "acme", [role(1)])
    finish_run(run, attempted=1, fetched=1, failed=0, roles_seen=1)

    cmd_report(None)
    out = capsys.readouterr().out.lower()
    for forbidden in ("trend", "growing", "increasing", "investing in", "shifting toward"):
        assert forbidden not in out, f"v1 must not imply a trend ({forbidden!r})"


# --- parser -------------------------------------------------------------------


@pytest.mark.parametrize("command", ["sync", "snapshot", "report", "run"])
def test_every_subcommand_parses(command):
    assert build_parser().parse_args([command]).command == command


def test_no_subcommand_defaults_to_the_full_run():
    assert build_parser().parse_args([]).command is None


def test_report_via_main_entrypoint(db, capsys):
    assert main(["report"]) == 1  # no completed runs
    assert "No completed runs yet" in capsys.readouterr().out
