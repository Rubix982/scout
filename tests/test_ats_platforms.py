"""ATS platform parsing and counting (E-011). No network."""

from __future__ import annotations

import json

import pytest

from src.sources.ats.platforms import (
    SUPPORTED_PLATFORMS,
    Platform,
    board_url_for,
    parse_board_url,
    role_count,
)


@pytest.mark.parametrize(
    "url,platform,token",
    [
        ("https://boards.greenhouse.io/wolt", Platform.GREENHOUSE, "wolt"),
        ("https://job-boards.greenhouse.io/affirm", Platform.GREENHOUSE, "affirm"),
        ("https://jobs.lever.co/swissborg", Platform.LEVER, "swissborg"),
        ("https://jobs.eu.lever.co/acme", Platform.LEVER, "acme"),
        ("https://jobs.ashbyhq.com/checkly", Platform.ASHBY, "checkly"),
        ("https://apply.workable.com/strapi", Platform.WORKABLE, "strapi"),
        ("https://ats.rippling.com/fabric", Platform.RIPPLING, "fabric"),
        ("https://everli.applytojob.com", Platform.JAZZHR, "everli"),
    ],
)
def test_parses_board_roots(url, platform, token):
    parsed = parse_board_url(url)
    assert parsed is not None
    assert (parsed.platform, parsed.token) == (platform, token)


def test_greenhouse_eu_is_a_distinct_platform():
    """US and EU are separate hosts with separate tenancies -- a token valid on
    one 404s on the other (R-001). The EU pattern must win, not the generic one.
    """
    parsed = parse_board_url(
        "https://boards.eu.greenhouse.io/cherryventures/jobs/4053703101?gh_src=dc724f02teu"
    )
    assert parsed.platform is Platform.GREENHOUSE_EU
    assert parsed.token == "cherryventures"


def test_token_is_extracted_from_a_deep_posting_url():
    parsed = parse_board_url("https://jobs.lever.co/strapi/0d55549c-bd53-47ed-b4d0/apply")
    assert (parsed.platform, parsed.token) == (Platform.LEVER, "strapi")


def test_marker_only_url_yields_platform_but_no_token():
    """From the real sheet: identifies Greenhouse, but not which board."""
    parsed = parse_board_url("https://fingerprint.com/careers/jobs/apply/?gh_jid=5361182004")
    assert parsed.platform is Platform.GREENHOUSE
    assert parsed.token is None
    assert not parsed.is_complete


@pytest.mark.parametrize(
    "url", ["", "   ", "https://www.example.com/careers", "not a url", "https://clari.com/careers/"]
)
def test_unrecognised_urls_return_none(url):
    assert parse_board_url(url) is None


@pytest.mark.parametrize("segment", ["embed", "jobs", "careers", "api", "www"])
def test_generic_path_segments_are_never_treated_as_tokens(segment):
    parsed = parse_board_url(f"https://boards.greenhouse.io/{segment}")
    assert parsed is None or parsed.token != segment


def test_supported_is_narrower_than_recognised():
    """Recognising more than we can fetch is deliberate: it lets an employer be
    reported as `platform_unsupported` rather than the useless
    `token_not_found`."""
    assert SUPPORTED_PLATFORMS < set(Platform)
    assert Platform.JAZZHR not in SUPPORTED_PLATFORMS
    assert Platform.RIPPLING not in SUPPORTED_PLATFORMS
    assert Platform.GREENHOUSE_EU in SUPPORTED_PLATFORMS


def test_board_url_for_round_trips():
    assert parse_board_url(board_url_for(Platform.ASHBY, "checkly")).token == "checkly"


# --- role counting ------------------------------------------------------------


def test_smartrecruiters_empty_result_counts_as_zero():
    """The R-001 trap: SmartRecruiters answers HTTP 200 with totalFound 0 for a
    company that does not exist. Counting from the body is what stops every
    company 'resolving' to SmartRecruiters with no roles."""
    body = json.dumps({"offset": 0, "limit": 100, "totalFound": 0, "content": []}).encode()
    assert role_count(Platform.SMARTRECRUITERS, body) == 0


@pytest.mark.parametrize(
    "platform,payload,expected",
    [
        (Platform.GREENHOUSE, {"jobs": [1, 2], "meta": {"total": 205}}, 205),
        (Platform.GREENHOUSE, {"jobs": [1, 2, 3]}, 3),  # meta absent
        (Platform.GREENHOUSE_EU, {"meta": {"total": 7}}, 7),
        (Platform.LEVER, [1, 2, 3], 3),
        (Platform.ASHBY, {"jobs": [1], "apiVersion": "1"}, 1),
        (Platform.WORKABLE, {"name": "x", "jobs": []}, 0),
        (Platform.SMARTRECRUITERS, {"totalFound": 12}, 12),
    ],
)
def test_role_count_per_platform(platform, payload, expected):
    assert role_count(platform, json.dumps(payload).encode()) == expected


@pytest.mark.parametrize("body", [b"", b"not json", b"null", b"[]"])
def test_role_count_survives_garbage(body):
    assert role_count(Platform.GREENHOUSE, body) == 0
