# src/sources/ats/platforms.py
"""ATS platform knowledge: endpoints, URL patterns, role counting.

Every endpoint here was verified live in R-001/R-002; see
`agents/shared/findings.md`. Two hard-won rules are encoded:

1. **Count roles from the response body, never trust the status code.**
   SmartRecruiters returns HTTP 200 with `{"totalFound": 0, "content": []}` for
   companies that do not exist. Status-based validation would "resolve" every
   company to SmartRecruiters with zero roles.
2. **Greenhouse US and EU are separate tenancies on separate hosts.** A token
   valid on one 404s on the other, so they are distinct platforms here.

Patterns recognise more platforms than we can fetch. That is deliberate: it lets
an unresolved employer be reported as `platform_unsupported` (we know what it
uses, we just cannot read it yet) rather than the far less useful
`token_not_found`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple


class Platform(str, Enum):
    GREENHOUSE = "greenhouse"
    GREENHOUSE_EU = "greenhouse_eu"
    LEVER = "lever"
    ASHBY = "ashby"
    # Recognised but not yet fetchable -- R-002 found these among the employers.
    WORKABLE = "workable"
    SMARTRECRUITERS = "smartrecruiters"
    JAZZHR = "jazzhr"
    RIPPLING = "rippling"
    WORKDAY = "workday"
    TEAMTAILOR = "teamtailor"
    PERSONIO = "personio"
    RECRUITEE = "recruitee"


#: Platforms E-003 can actually fetch in v1.
SUPPORTED_PLATFORMS = frozenset(
    {
        Platform.GREENHOUSE,
        Platform.GREENHOUSE_EU,
        Platform.LEVER,
        Platform.ASHBY,
    }
)

ENDPOINTS: Dict[Platform, str] = {
    Platform.GREENHOUSE: "https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
    Platform.GREENHOUSE_EU: "https://boards-api.eu.greenhouse.io/v1/boards/{token}/jobs",
    Platform.LEVER: "https://api.lever.co/v0/postings/{token}?mode=json",
    Platform.ASHBY: "https://api.ashbyhq.com/posting-api/job-board/{token}",
    Platform.WORKABLE: "https://apply.workable.com/api/v1/widget/accounts/{token}?details=true",
    Platform.SMARTRECRUITERS: "https://api.smartrecruiters.com/v1/companies/{token}/postings",
}

#: Canonical board root, for showing a user what we resolved to.
CANONICAL_URLS: Dict[Platform, str] = {
    Platform.GREENHOUSE: "https://boards.greenhouse.io/{token}",
    Platform.GREENHOUSE_EU: "https://boards.eu.greenhouse.io/{token}",
    Platform.LEVER: "https://jobs.lever.co/{token}",
    Platform.ASHBY: "https://jobs.ashbyhq.com/{token}",
}

# Order matters: the EU host must be tried before the generic Greenhouse
# pattern, and marker-only patterns (which yield no token) come last so a real
# token always wins.
_URL_PATTERNS: Tuple[Tuple[Platform, str], ...] = (
    (Platform.GREENHOUSE_EU, r"(?:boards|job-boards)\.eu\.greenhouse\.io/([A-Za-z0-9._-]+)"),
    (Platform.GREENHOUSE, r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9._-]+)"),
    (Platform.LEVER, r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9._-]+)"),
    (Platform.ASHBY, r"jobs\.ashbyhq\.com/([A-Za-z0-9._-]+)"),
    (Platform.WORKABLE, r"apply\.workable\.com/([A-Za-z0-9._-]+)"),
    (Platform.SMARTRECRUITERS, r"careers\.smartrecruiters\.com/([A-Za-z0-9._-]+)"),
    (Platform.TEAMTAILOR, r"([A-Za-z0-9-]+)\.teamtailor\.com"),
    (Platform.PERSONIO, r"([A-Za-z0-9-]+)\.jobs\.personio\.(?:de|com)"),
    (Platform.RECRUITEE, r"([A-Za-z0-9-]+)\.recruitee\.com"),
    (Platform.RIPPLING, r"ats\.rippling\.com/([A-Za-z0-9._-]+)"),
    (Platform.JAZZHR, r"([A-Za-z0-9-]+)\.applytojob\.com"),
    (Platform.WORKDAY, r"([A-Za-z0-9-]+)\.(?:wd\d+\.)?myworkdayjobs\.com"),
)

# Markers that identify a platform without revealing a token.
_MARKER_ONLY: Tuple[Tuple[Platform, str], ...] = (
    (Platform.GREENHOUSE, r"[?&]gh_jid="),
    (Platform.GREENHOUSE, r"grnh\.se/"),
)

#: Path segments that are never a board token.
_NOT_TOKENS = frozenset(
    {"embed", "job_board", "www", "jobs", "job", "api", "careers", "career",
     "boards", "board", "o", "j", "apply", "postings", "search"}
)


@dataclass(frozen=True)
class ParsedBoard:
    platform: Platform
    token: Optional[str]

    @property
    def is_supported(self) -> bool:
        return self.platform in SUPPORTED_PLATFORMS

    @property
    def is_complete(self) -> bool:
        return self.token is not None and self.is_supported


def parse_board_url(url: str) -> Optional[ParsedBoard]:
    """Extract (platform, token) from a job-board URL.

    Returns None when nothing is recognised. Returns a `ParsedBoard` with
    `token=None` when the platform is identifiable but the URL carries no token
    -- e.g. `fingerprint.com/careers/jobs/apply/?gh_jid=5361182004`, which says
    "Greenhouse" but not which board.
    """
    if not url or not url.strip():
        return None
    text = url.strip()

    for platform, pattern in _URL_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            token = match.group(1)
            if token and token.lower() not in _NOT_TOKENS:
                return ParsedBoard(platform=platform, token=token)

    for platform, pattern in _MARKER_ONLY:
        if re.search(pattern, text, re.I):
            return ParsedBoard(platform=platform, token=None)

    return None


def board_url_for(platform: Platform, token: str) -> str:
    template = CANONICAL_URLS.get(platform)
    return template.format(token=token) if template else ""


def role_count(platform: Platform, body: bytes) -> int:
    """Count open roles in a response body.

    Content-based by design -- see rule 1 in the module docstring.
    """
    try:
        payload = json.loads(body)
    except Exception:
        return 0

    if platform is Platform.LEVER:
        return len(payload) if isinstance(payload, list) else 0
    if not isinstance(payload, dict):
        return 0
    if platform is Platform.ASHBY:
        return len(payload.get("jobs") or [])
    if platform in (Platform.GREENHOUSE, Platform.GREENHOUSE_EU):
        meta = payload.get("meta") or {}
        total = meta.get("total")
        return int(total) if total is not None else len(payload.get("jobs") or [])
    if platform is Platform.WORKABLE:
        return len(payload.get("jobs") or [])
    if platform is Platform.SMARTRECRUITERS:
        return int(payload.get("totalFound") or 0)
    return 0
