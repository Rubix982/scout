"""Role normalisation across platforms (E-003). No network.

Fixtures mirror real payload shapes read off live responses -- notably that
Lever calls the title `text` and reports epoch milliseconds, and that neither
Lever nor Ashby exposes a modification time.
"""

from __future__ import annotations

import json

import pytest

from src.sources.ats.platforms import Platform
from src.sources.ats.roles import Role, endpoint_for, fetch_roles, parse_roles

GREENHOUSE_JOB = {
    "id": 7850544003,
    "title": "Administrative Assistant IV",
    "location": {"name": "Remote US"},
    "absolute_url": "https://job-boards.greenhouse.io/affirm/jobs/7850544003",
    "updated_at": "2026-08-19T16:06:53-04:00",
    "first_published": "2026-08-19T12:29:00-04:00",
    "departments": [{"id": 1, "name": "Architecture"}],
    "metadata": [{"name": "External Department", "value": "Engineering"}],
}
LEVER_JOB = {
    "id": "51459e7f-01ff-46d4-86ec-f8188db8c7bb",
    "text": "Affiliate Manager | Propr.xyz",
    "categories": {
        "commitment": "Full-time",
        "department": "XBorg",
        "location": "Remote - Europe Timezone",
    },
    "createdAt": 1777551217923,
    "hostedUrl": "https://jobs.lever.co/swissborg/51459e7f-01ff-46d4-86ec-f8188db8c7bb",
}
ASHBY_JOB = {
    "id": "21acd589-f6eb-42cd-8c75-3eac4e3fb1e7",
    "title": "Senior Backend Engineer",
    "department": "Engineering",
    "location": "Remote",
    "publishedAt": "2025-12-15T17:27:20.000+00:00",
    "jobUrl": "https://jobs.ashbyhq.com/checkly/21acd589",
}


def gh(jobs, total=None):
    return json.dumps({"jobs": jobs, "meta": {"total": total or len(jobs)}}).encode()


# --- per-platform normalisation ----------------------------------------------


def test_greenhouse_normalisation():
    (role,) = parse_roles(Platform.GREENHOUSE, "affirm", gh([GREENHOUSE_JOB]))
    assert role.external_id == "7850544003", "int id must become a string"
    assert role.title == "Administrative Assistant IV"
    assert role.location == "Remote US"
    assert role.url.endswith("/7850544003")
    assert role.updated_at == "2026-08-19T16:06:53-04:00"
    assert role.first_published == "2026-08-19T12:29:00-04:00"


def test_lever_normalisation_reads_title_from_text():
    """Lever has no `title` key at all -- the title lives in `text`."""
    (role,) = parse_roles(Platform.LEVER, "swissborg", json.dumps([LEVER_JOB]).encode())
    assert role.title == "Affiliate Manager | Propr.xyz"
    assert role.location == "Remote - Europe Timezone"
    assert role.department == "XBorg"


def test_lever_epoch_milliseconds_become_iso():
    (role,) = parse_roles(Platform.LEVER, "swissborg", json.dumps([LEVER_JOB]).encode())
    assert role.first_published is not None
    assert role.first_published.startswith("2026-04-30T")


@pytest.mark.parametrize("bad", [None, "", "not-a-number", {}])
def test_lever_unparseable_timestamp_becomes_none(bad):
    job = dict(LEVER_JOB, createdAt=bad)
    (role,) = parse_roles(Platform.LEVER, "t", json.dumps([job]).encode())
    assert role.first_published is None


def test_ashby_normalisation():
    (role,) = parse_roles(Platform.ASHBY, "checkly", gh([ASHBY_JOB]))
    assert role.title == "Senior Backend Engineer"
    assert role.department == "Engineering"
    assert role.first_published == "2025-12-15T17:27:20.000+00:00"


@pytest.mark.parametrize(
    "platform,token,body",
    [
        (Platform.LEVER, "swissborg", json.dumps([LEVER_JOB]).encode()),
        (Platform.ASHBY, "checkly", gh([ASHBY_JOB])),
    ],
)
def test_only_greenhouse_reports_a_modification_time(platform, token, body):
    """Documented constraint, verified live: Lever and Ashby expose creation
    time only. E-005 therefore cannot diff on `updated_at` -- it must compare
    the normalised fields themselves.
    """
    (role,) = parse_roles(platform, token, body)
    assert role.updated_at is None
    assert role.first_published is not None


# --- department resolution ----------------------------------------------------


def test_departments_field_wins_over_custom_metadata():
    """`departments[]` is the real schema; `metadata` keys are tenant-defined."""
    (role,) = parse_roles(Platform.GREENHOUSE, "affirm", gh([GREENHOUSE_JOB]))
    assert role.department == "Architecture"


def test_metadata_is_only_a_fallback_when_departments_is_empty():
    job = dict(GREENHOUSE_JOB, departments=[])
    (role,) = parse_roles(Platform.GREENHOUSE, "affirm", gh([job]))
    assert role.department == "Engineering"


def test_department_is_empty_when_neither_source_is_present():
    """wolt and fingerprint under content=false -- 265 of 477 roles."""
    job = dict(GREENHOUSE_JOB, departments=[], metadata=[{"name": "Employment Type", "value": "FT"}])
    (role,) = parse_roles(Platform.GREENHOUSE, "fingerprint", gh([job]))
    assert role.department == ""


# --- identity -----------------------------------------------------------------


def test_identity_is_keyed_on_external_id_not_title():
    """R-002 noted reposts and title churn; keying on title would manufacture
    phantom 'new role' events."""
    a = parse_roles(Platform.GREENHOUSE, "affirm", gh([GREENHOUSE_JOB]))[0]
    renamed = parse_roles(
        Platform.GREENHOUSE, "affirm", gh([dict(GREENHOUSE_JOB, title="Renamed Role")])
    )[0]
    assert a.identity == renamed.identity
    assert a.title != renamed.title


def test_identity_separates_the_two_greenhouse_tenancies():
    us = parse_roles(Platform.GREENHOUSE, "acme", gh([GREENHOUSE_JOB]))[0]
    eu = parse_roles(Platform.GREENHOUSE_EU, "acme", gh([GREENHOUSE_JOB]))[0]
    assert us.identity != eu.identity


# --- payload handling ---------------------------------------------------------


def test_lever_expects_a_bare_array_not_an_object():
    assert parse_roles(Platform.LEVER, "t", gh([LEVER_JOB])) == []
    assert len(parse_roles(Platform.LEVER, "t", json.dumps([LEVER_JOB]).encode())) == 1


@pytest.mark.parametrize("body", [b"", b"not json", b"null", b"{}", b'{"jobs": null}'])
def test_garbage_bodies_yield_no_roles(body):
    assert parse_roles(Platform.GREENHOUSE, "t", body) == []


def test_job_without_an_id_is_skipped():
    job = dict(GREENHOUSE_JOB)
    del job["id"]
    assert parse_roles(Platform.GREENHOUSE, "t", gh([job, GREENHOUSE_JOB])) != []
    assert len(parse_roles(Platform.GREENHOUSE, "t", gh([job, GREENHOUSE_JOB]))) == 1


def test_non_dict_entries_are_skipped():
    body = json.dumps({"jobs": ["junk", GREENHOUSE_JOB, 42]}).encode()
    assert len(parse_roles(Platform.GREENHOUSE, "t", body)) == 1


def test_raw_payload_is_retained_for_reprocessing():
    """Keeping the original JSON means a normalisation change can be replayed
    against stored data instead of requiring a re-fetch."""
    (role,) = parse_roles(Platform.GREENHOUSE, "affirm", gh([GREENHOUSE_JOB]))
    assert json.loads(role.raw) == GREENHOUSE_JOB


def test_unsupported_platform_raises():
    with pytest.raises(ValueError, match="no adapter"):
        parse_roles(Platform.JAZZHR, "everli", b"{}")


# --- endpoint + fetch ---------------------------------------------------------


def test_content_flag_is_on_by_default_for_greenhouse():
    """Greenhouse omits departments[] without it -- 44% coverage vs 100%."""
    assert "content=true" in endpoint_for(Platform.GREENHOUSE, "wolt")
    assert "content=true" not in endpoint_for(Platform.GREENHOUSE, "wolt", include_content=False)


def test_content_flag_is_ignored_for_other_platforms():
    assert "content=true" not in endpoint_for(Platform.LEVER, "swissborg")
    assert "content=true" not in endpoint_for(Platform.ASHBY, "checkly")


def test_content_flag_respects_an_existing_query_string():
    url = endpoint_for(Platform.LEVER, "t", include_content=True)
    assert url.count("?") == 1


def test_fetch_roles_returns_nothing_on_a_failed_request():
    assert fetch_roles(Platform.GREENHOUSE, "t", lambda url: (404, b"")) == []
    assert fetch_roles(Platform.GREENHOUSE, "t", lambda url: (None, b"")) == []


def test_fetch_roles_normalises_a_successful_response():
    roles = fetch_roles(Platform.GREENHOUSE, "affirm", lambda url: (200, gh([GREENHOUSE_JOB])))
    assert len(roles) == 1 and isinstance(roles[0], Role)
