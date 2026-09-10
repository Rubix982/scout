"""Role snapshots and run-over-run diffing (E-005). No network."""

from __future__ import annotations

import json

import pytest

from src.common.models import Role
from src.db.init import get_con, init_tables
from src.db.roles import (
    COMPARE_FIELDS,
    ChangeType,
    changes_for_run,
    department_mix,
    finish_run,
    open_role_count,
    previous_completed_run,
    snapshot_company,
    start_run,
)
from src.sources.ats.platforms import Platform
from src.sources.ats.snapshot import run_snapshot


def role(external_id, title="Engineer", location="Remote", department="Engineering",
         platform="greenhouse", token="acme"):
    return Role(
        platform=platform, token=token, external_id=str(external_id), title=title,
        location=location, department=department,
        url=f"https://example/{external_id}",
        first_published="2026-01-01T00:00:00Z", updated_at=None, raw="{}",
    )


@pytest.fixture
def db(isolate_database):
    init_tables()
    con = get_con()
    for t in ("roles", "role_changes", "runs", "company_ats", "companies"):
        con.execute(f"DELETE FROM {t}")
    return con


def types(changes):
    return sorted(c.change_type.value for c in changes)


# --- basic lifecycle ----------------------------------------------------------


def test_first_snapshot_reports_everything_as_appeared(db):
    run = start_run()
    changes = snapshot_company(run, "acme", [role(1), role(2)])
    assert types(changes) == ["appeared", "appeared"]
    assert open_role_count("acme") == 2


def test_identical_second_snapshot_reports_nothing(db):
    roles = [role(1), role(2)]
    snapshot_company(start_run(), "acme", roles)
    changes = snapshot_company(start_run(), "acme", roles)
    assert changes == []


def test_removed_role_is_closed(db):
    snapshot_company(start_run(), "acme", [role(1), role(2)])
    changes = snapshot_company(start_run(), "acme", [role(1)])
    assert types(changes) == ["closed"]
    assert open_role_count("acme") == 1
    assert db.execute(
        "SELECT closed_at FROM roles WHERE external_id = '2'"
    ).fetchone()[0] is not None


def test_a_closed_role_is_not_closed_again(db):
    snapshot_company(start_run(), "acme", [role(1)])
    snapshot_company(start_run(), "acme", [])
    changes = snapshot_company(start_run(), "acme", [])
    assert changes == [], "an already-closed role must not re-emit a closed event"


def test_returning_role_is_reopened_not_appeared(db):
    snapshot_company(start_run(), "acme", [role(1)])
    snapshot_company(start_run(), "acme", [])
    changes = snapshot_company(start_run(), "acme", [role(1)])
    assert "reopened" in types(changes)
    assert "appeared" not in types(changes)
    assert open_role_count("acme") == 1


# --- identity -----------------------------------------------------------------


def test_renamed_role_is_changed_not_replaced(db):
    """Keying on the ATS id, not the title. Otherwise a rename would read as one
    role closing and another appearing."""
    snapshot_company(start_run(), "acme", [role(1, title="Engineer")])
    changes = snapshot_company(start_run(), "acme", [role(1, title="Senior Engineer")])
    assert types(changes) == ["changed"]
    assert changes[0].field == "title"
    assert (changes[0].old_value, changes[0].new_value) == ("Engineer", "Senior Engineer")
    assert open_role_count("acme") == 1


def test_distinct_ids_with_the_same_title_are_separate_roles(db):
    """Real data: wolt lists 'Grocery Associate' 14 times under distinct ids.
    Title-keying would collapse them and churn on every run."""
    run = start_run()
    changes = snapshot_company(
        run, "wolt", [role(i, title="Grocery Associate") for i in range(1, 15)]
    )
    assert len(changes) == 14
    assert open_role_count("wolt") == 14
    assert snapshot_company(
        start_run(), "wolt", [role(i, title="Grocery Associate") for i in range(1, 15)]
    ) == []


def test_the_two_greenhouse_tenancies_never_collide(db):
    """Same external id on both hosts must be two distinct roles.

    Both are passed in one call: snapshot_company is the *complete* picture for
    a company in a run, so calling it twice would correctly close whatever the
    second call omitted.
    """
    changes = snapshot_company(
        start_run(),
        "acme",
        [role(1, platform="greenhouse"), role(1, platform="greenhouse_eu")],
    )
    assert types(changes) == ["appeared", "appeared"]
    assert open_role_count("acme") == 2


def test_compare_fields_are_all_covered_below():
    """Guard: if a field joins COMPARE_FIELDS, the parametrised test below must
    grow to match it."""
    assert set(COMPARE_FIELDS) == {"title", "location", "department", "url"}


@pytest.mark.parametrize(
    "field,new",
    [("title", "New Title"), ("location", "Berlin"),
     ("department", "Sales"), ("url", "https://example/changed")],
)
def test_each_field_change_is_recorded(db, field, new):
    snapshot_company(start_run(), "acme", [role(1)])
    changed = role(1)
    changes = snapshot_company(
        start_run(), "acme", [Role(**{**changed.__dict__, field: new})]
    )
    assert [c.field for c in changes] == [field]


# --- the guardrail ------------------------------------------------------------


def test_a_failed_fetch_closes_nothing(db):
    """The most important invariant in this module.

    A single network blip must not mark a company's entire role set closed and
    report it as a hiring freeze.
    """
    db.execute(
        "INSERT INTO company_ats (company_name, platform, token, status) "
        "VALUES ('acme', 'greenhouse', 'acme', 'resolved')"
    )
    ok_body = json.dumps(
        {"jobs": [{"id": 1, "title": "Engineer", "location": {"name": "Remote"},
                   "departments": [{"name": "Engineering"}],
                   "absolute_url": "https://example/1"}], "meta": {"total": 1}}
    ).encode()

    run_snapshot(fetch=lambda url: (200, ok_body))
    assert open_role_count("acme") == 1

    report = run_snapshot(fetch=lambda url: (500, b""))
    assert report.failed and not report.fetched
    assert report.changes == []
    assert open_role_count("acme") == 1, "a failed fetch closed roles"


def test_a_transport_error_also_closes_nothing(db):
    db.execute(
        "INSERT INTO company_ats (company_name, platform, token, status) "
        "VALUES ('acme', 'greenhouse', 'acme', 'resolved')"
    )
    body = json.dumps({"jobs": [{"id": 1, "title": "E", "location": {"name": "R"},
                                 "absolute_url": "u"}], "meta": {"total": 1}}).encode()
    run_snapshot(fetch=lambda url: (200, body))
    run_snapshot(fetch=lambda url: (None, b""))
    assert open_role_count("acme") == 1


def test_a_successful_fetch_of_an_empty_board_does_close_everything(db):
    """The distinction the runner exists to preserve: 'fetched, zero roles' is
    real information; 'fetch failed' is not."""
    db.execute(
        "INSERT INTO company_ats (company_name, platform, token, status) "
        "VALUES ('acme', 'greenhouse', 'acme', 'resolved')"
    )
    body = json.dumps({"jobs": [{"id": 1, "title": "E", "location": {"name": "R"},
                                 "absolute_url": "u"}], "meta": {"total": 1}}).encode()
    run_snapshot(fetch=lambda url: (200, body))
    assert open_role_count("acme") == 1

    empty = json.dumps({"jobs": [], "meta": {"total": 0}}).encode()
    report = run_snapshot(fetch=lambda url: (200, empty))
    assert report.fetched and not report.failed
    assert [c.change_type for c in report.changes] == [ChangeType.CLOSED]
    assert open_role_count("acme") == 0


def test_one_company_failing_does_not_block_the_others(db):
    for name in ("acme", "beta"):
        db.execute(
            "INSERT INTO company_ats (company_name, platform, token, status) "
            f"VALUES ('{name}', 'greenhouse', '{name}', 'resolved')"
        )
    body = json.dumps({"jobs": [{"id": 1, "title": "E", "location": {"name": "R"},
                                 "absolute_url": "u"}], "meta": {"total": 1}}).encode()

    def fetch(url):
        return (500, b"") if "acme" in url else (200, body)

    report = run_snapshot(fetch=fetch)
    assert [o.company_name for o in report.failed] == ["acme"]
    assert [o.company_name for o in report.fetched] == ["beta"]
    assert open_role_count("beta") == 1


# --- runs ---------------------------------------------------------------------


def test_run_records_attempt_and_failure_counts(db):
    for name in ("acme", "beta"):
        db.execute(
            "INSERT INTO company_ats (company_name, platform, token, status) "
            f"VALUES ('{name}', 'greenhouse', '{name}', 'resolved')"
        )
    report = run_snapshot(fetch=lambda url: (500, b""))
    row = db.execute(
        "SELECT companies_attempted, companies_fetched, companies_failed, roles_seen "
        "FROM runs WHERE run_id = ?", [report.run_id]
    ).fetchone()
    # No feed in this run (include_feed defaults False), so the counts are the
    # two boards only.
    assert row == (2, 0, 2, 0)


def test_first_run_is_flagged_as_such(db):
    db.execute(
        "INSERT INTO company_ats (company_name, platform, token, status) "
        "VALUES ('acme', 'greenhouse', 'acme', 'resolved')"
    )
    first = run_snapshot(fetch=lambda url: (200, b'{"jobs": [], "meta": {"total": 0}}'))
    assert first.is_first_run
    second = run_snapshot(fetch=lambda url: (200, b'{"jobs": [], "meta": {"total": 0}}'))
    assert not second.is_first_run
    assert second.previous_run_id == first.run_id


def test_unfinished_runs_are_not_treated_as_previous(db):
    orphan = start_run()  # never finished
    later = start_run()
    finish_run(later, attempted=0, fetched=0, failed=0, roles_seen=0)
    assert previous_completed_run(later) is None


def test_changes_are_queryable_per_run(db):
    run = start_run()
    snapshot_company(run, "acme", [role(1), role(2)])
    finish_run(run, attempted=1, fetched=1, failed=0, roles_seen=2)
    rows = changes_for_run(run, ChangeType.APPEARED)
    assert len(rows) == 2
    assert {r["company_name"] for r in rows} == {"acme"}


# --- reporting helpers --------------------------------------------------------


def test_department_mix_reports_shares_not_counts(db):
    """Company size co-varies with posting volume, so shares are the comparable
    quantity (plan.md lens 6)."""
    run = start_run()
    snapshot_company(run, "acme", [
        role(1, department="Engineering"), role(2, department="Engineering"),
        role(3, department="Engineering"), role(4, department="Sales"),
    ])
    mix = department_mix("acme")
    assert mix[0][0] == "Engineering"
    assert mix[0][1] == 3
    assert mix[0][2] == pytest.approx(0.75)
    assert sum(share for _, _, share in mix) == pytest.approx(1.0)


def test_department_mix_labels_missing_departments(db):
    snapshot_company(start_run(), "acme", [role(1, department="")])
    assert department_mix("acme")[0][0] == "(unspecified)"


def test_closed_roles_are_excluded_from_the_mix(db):
    snapshot_company(start_run(), "acme", [role(1, department="Sales")])
    snapshot_company(start_run(), "acme", [])
    assert department_mix("acme") == []
