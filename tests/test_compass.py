"""Compass heading-check reading material (E-013). No network."""

from __future__ import annotations

import json

import pytest

from src.cli import cmd_compass, build_parser
from src.common.models import Role
from src.compass import composition, extract_needs, find_roles
from src.db.init import get_con, init_tables
from src.db.roles import snapshot_company, start_run


def gh_raw(content: str, **extra):
    return json.dumps({"content": content, **extra})


def role(external_id, title, company, content="", platform="greenhouse", tags=()):
    return Role(
        platform=platform, token=company, external_id=str(external_id), title=title,
        location="Remote", department="Engineering",
        url=f"https://example/{external_id}",
        first_published="2026-01-01T00:00:00Z", updated_at=None,
        raw=gh_raw(content), tags=tuple(tags),
    )


@pytest.fixture
def db(isolate_database):
    init_tables()
    con = get_con()
    for t in ("roles", "role_changes", "runs", "company_ats", "companies"):
        con.execute(f"DELETE FROM {t}")
    return con


# --- needs extraction ---------------------------------------------------------


def test_extracts_requirement_lines_mentioning_the_term():
    jd = (
        "<ul><li>You have 5+ years of experience with Kubernetes in production</li>"
        "<li>We offer a competitive benefits package</li></ul>"
    )
    needs = extract_needs(jd, "kubernetes")
    assert len(needs) == 1
    assert "Kubernetes" in needs[0]


@pytest.mark.parametrize(
    "line",
    [
        "By clicking Submit Application you acknowledge you have read our Privacy Notice",
        "We are an equal opportunity employer and you have our commitment to fairness",
        "Base Pay Grade N. Employees new to the company have a starting pay range",
        "It's On Us to provide an inclusive interview experience for people with disabilities",
    ],
)
def test_legal_and_pay_boilerplate_is_excluded(line):
    """These trip the requirement hints by accident -- "you have read our Privacy
    Notice" matches "you have" -- and padding a heading-check with them defeats
    the purpose, which is reading the stated needs."""
    jd = f"<ul><li>{line}</li></ul>"
    assert extract_needs(jd, "kubernetes") == []


def test_does_not_pad_to_the_limit():
    """An honest "nothing stated" beats filler."""
    jd = "<ul><li>You have 5+ years of experience with Kubernetes</li></ul>"
    assert len(extract_needs(jd, "kubernetes", limit=5)) == 1


def test_falls_back_to_generic_needs_only_when_nothing_on_term():
    jd = "<ul><li>You have 3+ years of experience in backend development</li></ul>"
    assert extract_needs(jd, "kubernetes") != []   # generic fallback
    assert extract_needs(jd, "backend") != []      # on-term


def test_empty_or_unparseable_jd_yields_nothing():
    assert extract_needs("", "security") == []
    assert extract_needs("<p>short</p>", "security") == []


# --- search and ranking -------------------------------------------------------


def test_returns_one_role_per_company(db):
    """wolt alone has 233 open roles live; a prolific poster must not crowd out
    the breadth a heading-check depends on."""
    roles = [
        role(i, f"Security Engineer {i}", "wolt", "You have experience in security")
        for i in range(5)
    ]
    snapshot_company(start_run(), "wolt", roles)
    snapshot_company(start_run(), "affirm", [role(99, "Security Lead", "affirm",
                                                  "You have security experience")])
    found = find_roles("security", limit=8)
    assert sorted(r.company_name for r in found) == ["affirm", "wolt"]


def test_ranks_roles_that_say_more_about_the_area_higher(db):
    """Searching "security" must not surface a role that merely mentions it in a
    company blurb above one that states security requirements."""
    stated = role(1, "Security Engineer", "acme",
                  "You have 5 years of experience in application security")
    mentioned = role(2, "Office Manager", "beta",
                     "We are a security company. You have strong organisational skills.")
    snapshot_company(start_run(), "acme", [stated])
    snapshot_company(start_run(), "beta", [mentioned])

    found = find_roles("security", limit=8)
    assert found[0].company_name == "acme"
    assert found[0].relevance > found[-1].relevance


def test_no_matches_returns_empty(db):
    snapshot_company(start_run(), "acme", [role(1, "Chef", "acme", "You can cook")])
    assert find_roles("kubernetes") == []


def test_closed_roles_are_not_offered_as_reading(db):
    snapshot_company(start_run(), "acme",
                     [role(1, "Security Engineer", "acme", "security experience")])
    snapshot_company(start_run(), "acme", [])
    assert find_roles("security") == []


def test_composition_counts_open_roles_per_platform(db):
    snapshot_company(start_run(), "acme", [role(1, "A", "acme")])
    snapshot_company(start_run(), "feedco",
                     [role(2, "B", "feedco", platform="80000hours")])
    assert composition() == {"greenhouse": 1, "80000hours": 1}


# --- CLI ----------------------------------------------------------------------


class Args:
    def __init__(self, area, limit=8):
        self.area = area
        self.limit = limit


def test_banner_is_always_printed(db, capsys):
    snapshot_company(start_run(), "acme",
                     [role(1, "Security Engineer", "acme", "security experience")])
    cmd_compass(Args(["security"]))
    out = capsys.readouterr().out
    assert "Corpus this is read from" in out


def test_feed_dominated_corpus_gets_an_explicit_caveat(db, capsys):
    """The corpus is 67% 80,000 Hours live. Reading absence as demand signal
    without this caveat would point the heading at 80k's editorial priorities."""
    snapshot_company(start_run(), "feedco", [
        role(i, f"Role {i}", "feedco", "security experience", platform="80000hours")
        for i in range(9)
    ])
    snapshot_company(start_run(), "acme",
                     [role(99, "Security Engineer", "acme", "security experience")])
    cmd_compass(Args(["security"]))
    out = capsys.readouterr().out
    assert "CAVEAT" in out
    assert "not that nobody wants it" in out


def test_no_matches_says_it_is_about_the_corpus(db, capsys):
    snapshot_company(start_run(), "acme", [role(1, "Chef", "acme", "You can cook")])
    assert cmd_compass(Args(["kubernetes"])) == 0
    out = capsys.readouterr().out
    assert "No open roles match" in out
    assert "statement about the corpus, not about demand" in out


def test_output_contains_no_alignment_score_or_recommendation(db, capsys):
    """The Compass calls the heading-check a habit, not a system, and warns that
    building a tracking system for it is the difficulty-trap. Scoring the
    judgment would be exactly that -- and would need to know work a corpus
    cannot see."""
    snapshot_company(start_run(), "acme",
                     [role(1, "Security Engineer", "acme", "security experience")])
    cmd_compass(Args(["security"]))
    out = capsys.readouterr().out.lower()
    for forbidden in (
        "alignment score", "% aligned", "match score", "you should focus",
        "we recommend", "next brick", "fit score",
    ):
        assert forbidden not in out, f"compass must not emit {forbidden!r}"
    assert "scout deliberately does not score" in out


def test_empty_area_is_rejected(db, capsys):
    assert cmd_compass(Args([" "])) == 1
    assert "Give an area" in capsys.readouterr().out


def test_parser_accepts_multi_word_areas_and_a_limit():
    args = build_parser().parse_args(["compass", "--area", "cloud", "security", "--limit", "3"])
    assert args.area == ["cloud", "security"]
    assert args.limit == 3
