# src/compass.py
"""Reading material for the Compass heading-check (E-013).

The global Compass prescribes a habit: every few weeks, read 5-10 job
descriptions in the target area and ask *which listed needs does my current work
produce evidence for?*

This module does the mechanical half — find relevant roles, pull out the needs
they state — and stops there. It deliberately does not score alignment, keep
history, or suggest what to work on next. The Compass is explicit that building a
tracking system for the heading-check is itself the difficulty-trap, and the
judgment step requires knowing the work being checked, which a corpus does not.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from src.db.init import get_con

#: JD-bearing fields, in preference order, across both sources.
_JD_FIELDS = ("content", "description", "description_short", "descriptionPlain")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t ]+")

#: Lines that read like a stated need rather than boilerplate.
_NEED_HINTS = re.compile(
    r"\b(experience|years|proficien|familiar|expertise|skilled|knowledge of|"
    r"background in|you (?:have|will|are)|ability to|comfortable with|"
    r"strong |deep |hands-on|track record)\b",
    re.I,
)

#: Legal, pay and EEO boilerplate. These match _NEED_HINTS by accident -- "you
#: have read Affirm's Global Candidate Privacy Notice" trips "you have" -- and
#: padding a heading-check with them is worse than showing nothing, because the
#: whole point is reading the *stated needs*.
_BOILERPLATE = re.compile(
    r"(privacy notice|equal (?:opportunity|employment)|pay (?:grade|range|band)|"
    r"compensation|salary range|benefits package|clicking|submit application|"
    r"disabilit|accommodation|background check|e-verify|affirmative action|"
    r"we believe|it'?s on us|regardless of race|protected veteran|"
    r"visa sponsorship is|401\(k\)|equity grade)",
    re.I,
)


@dataclass(frozen=True)
class CompassRole:
    #: Higher means the role says more about the searched area. See `find_roles`.
    relevance: int
    company_name: str
    platform: str
    title: str
    location: str
    department: str
    tags: Sequence[str]
    url: str
    needs: Sequence[str]


def _plain_text(raw_html: str) -> str:
    text = html.unescape(raw_html or "")
    text = html.unescape(text)  # Greenhouse double-escapes its content field
    text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.I)
    text = re.sub(r"</(p|div|li|ul|h\d)>", "\n", text, flags=re.I)
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _jd_text(raw: str) -> str:
    try:
        payload = json.loads(raw)
    except Exception:
        return ""
    parts = [payload.get(f) for f in _JD_FIELDS if payload.get(f)]
    return _plain_text("\n".join(str(p) for p in parts))


def extract_needs(jd_text: str, term: str, limit: int = 5) -> List[str]:
    """Lines that state a requirement, preferring ones mentioning `term`.

    Accepts plain text or raw HTML. Handed HTML it used to degrade silently:
    `splitlines()` saw one long line, so a single boilerplate phrase anywhere in
    the markup discarded the entire description. Normalising here removes the
    trap rather than documenting it.
    """
    if _TAG_RE.search(jd_text or ""):
        jd_text = _plain_text(jd_text)
    lines = [
        re.sub(r"^[-*•]\s*", "", line).strip()
        for line in jd_text.splitlines()
        if 25 <= len(line) <= 320
    ]
    lines = [l for l in lines if not _BOILERPLATE.search(l)]
    lowered = term.lower()
    on_term = [l for l in lines if lowered in l.lower() and _NEED_HINTS.search(l)]

    # Only fall back to generic requirement lines when the role states nothing
    # about the term itself -- and never pad to `limit`. An honest "nothing
    # stated" beats filler.
    generic = (
        [l for l in lines if _NEED_HINTS.search(l) and l not in on_term]
        if not on_term
        else []
    )

    out: List[str] = []
    for line in on_term + generic[:2]:
        if line not in out:
            out.append(line)
        if len(out) >= limit:
            break
    return out


def composition() -> Dict[str, int]:
    """Open roles per platform, for the bias banner."""
    return {
        row[0]: int(row[1])
        for row in get_con()
        .execute(
            "SELECT platform, count(*) FROM roles WHERE closed_at IS NULL "
            "GROUP BY 1 ORDER BY 2 DESC"
        )
        .fetchall()
    }


def find_roles(term: str, limit: int = 8) -> List[CompassRole]:
    """Up to `limit` matching open roles, **one per company**.

    One per company on purpose: wolt alone has 233 open roles, and a
    most-recent-overall sample would let a single prolific poster crowd out the
    breadth a heading-check depends on.
    """
    pattern = f"%{term.lower()}%"
    rows = (
        get_con()
        .execute(
            """
            SELECT company_name, platform, title, location, department, tags,
                   url, raw
            FROM roles
            WHERE closed_at IS NULL
              AND (lower(title) LIKE ? OR lower(raw) LIKE ?)
            ORDER BY coalesce(first_published, '') DESC
            """,
            [pattern, pattern],
        )
        .fetchall()
    )

    lowered = term.lower()
    candidates: List[CompassRole] = []
    for company, platform, title, location, department, tags, url, raw in rows:
        try:
            tag_list = list(json.loads(tags)) if tags else []
        except Exception:
            tag_list = []
        needs = extract_needs(_jd_text(raw), term)

        # Rank by how much the role actually SAYS about the area, not by whether
        # the word appears somewhere in the payload. Searching "security"
        # otherwise surfaces roles that merely mention it in a company blurb,
        # which is useless for a heading-check: the question is what needs are
        # *stated*.
        on_term_needs = sum(1 for n in needs if lowered in n.lower())
        relevance = (
            3 * (lowered in title.lower())
            + 2 * min(on_term_needs, 3)
            + 1 * any(lowered in t.lower() for t in tag_list)
        )
        candidates.append(
            CompassRole(
                relevance=relevance,
                company_name=company,
                platform=platform,
                title=title,
                location=location or "",
                department=department or "",
                tags=tag_list,
                url=url or "",
                needs=needs,
            )
        )

    candidates.sort(key=lambda r: -r.relevance)
    seen: set[str] = set()
    out: List[CompassRole] = []
    for role in candidates:
        if role.company_name in seen:
            continue
        seen.add(role.company_name)
        out.append(role)
        if len(out) >= limit:
            break
    return out
