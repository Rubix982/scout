# src/sources/ats/resolve.py
"""Resolve employers to ATS boards from user-supplied URLs (E-011).

Manual entry is the primary path, not a fallback. R-002 measured automatic
resolution at 7/36 (19%) with link-seeding contributing zero, and found 13 of 18
employers running career pages with no ATS signature. Pasting a board root is one
click from a careers page; automatic resolution is a convenience for later
(E-004) and must never outrank `manual`.

Every outcome is recorded. An employer we cannot resolve gets a row with a
`reason`, because silently omitting it would overstate coverage -- the exact
failure the R-002 re-pass exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional, Tuple

import requests

from src.db.companies import Company, employers_needing_resolution
from src.db.init import get_con
from src.log import get_logger
from src.sources.ats.platforms import (
    ENDPOINTS,
    ParsedBoard,
    Platform,
    parse_board_url,
    role_count,
)

logger = get_logger("ats.resolve")

USER_AGENT = "scout/0.1 (+https://github.com/Rubix982/scout)"
TIMEOUT_SECONDS = 20


class Status(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class Reason(str, Enum):
    NO_BOARD_URL = "no_board_url"
    UNRECOGNISED_URL = "unrecognised_url"
    NO_TOKEN_IN_URL = "no_token_in_url"
    PLATFORM_UNSUPPORTED = "platform_unsupported"
    BOARD_UNREACHABLE = "board_unreachable"
    BOARD_EMPTY = "board_empty"


EXPLANATIONS = {
    Reason.NO_BOARD_URL: "no Board URL in the sheet",
    Reason.UNRECOGNISED_URL: "Board URL is not a recognised ATS board",
    Reason.NO_TOKEN_IN_URL: "URL identifies the platform but carries no board token",
    Reason.PLATFORM_UNSUPPORTED: "platform recognised but no adapter yet (E-003)",
    Reason.BOARD_UNREACHABLE: "board did not respond successfully",
    Reason.BOARD_EMPTY: "board responded but lists no open roles",
}

#: (status_code, body). status_code is None on a transport error.
Fetcher = Callable[[str], Tuple[Optional[int], bytes]]


def http_fetch(url: str) -> Tuple[Optional[int], bytes]:
    try:
        response = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS
        )
        return response.status_code, response.content
    except requests.RequestException as exc:
        logger.warning("[ATS] transport error for %s: %s", url, exc)
        return None, b""


@dataclass(frozen=True)
class Resolution:
    company_name: str
    status: Status
    platform: Optional[Platform] = None
    token: Optional[str] = None
    role_count: int = 0
    reason: Optional[Reason] = None
    method: str = "manual"

    @property
    def explanation(self) -> str:
        return EXPLANATIONS.get(self.reason, "") if self.reason else ""


def validate(parsed: ParsedBoard, fetch: Fetcher = http_fetch) -> Tuple[bool, int, Optional[Reason]]:
    """Check a parsed board against the live API.

    Content-based: a 200 is not enough. SmartRecruiters answers 200 with
    `totalFound: 0` for companies that do not exist (R-001), so zero roles is
    treated as a failure to resolve, not a successful empty board.
    """
    if parsed.token is None:
        return False, 0, Reason.NO_TOKEN_IN_URL
    if parsed.platform not in ENDPOINTS:
        return False, 0, Reason.PLATFORM_UNSUPPORTED

    status_code, body = fetch(ENDPOINTS[parsed.platform].format(token=parsed.token))
    if status_code != 200:
        return False, 0, Reason.BOARD_UNREACHABLE

    count = role_count(parsed.platform, body)
    if count <= 0:
        return False, 0, Reason.BOARD_EMPTY
    return True, count, None


def resolve_company(company: Company, fetch: Fetcher = http_fetch) -> Resolution:
    if not company.board_url.strip():
        return Resolution(company.company_name, Status.UNRESOLVED, reason=Reason.NO_BOARD_URL)

    parsed = parse_board_url(company.board_url)
    if parsed is None:
        return Resolution(
            company.company_name, Status.UNRESOLVED, reason=Reason.UNRECOGNISED_URL
        )

    ok, count, reason = validate(parsed, fetch=fetch)
    if not ok:
        return Resolution(
            company.company_name,
            Status.UNRESOLVED,
            platform=parsed.platform,
            token=parsed.token,
            reason=reason,
        )
    return Resolution(
        company.company_name,
        Status.RESOLVED,
        platform=parsed.platform,
        token=parsed.token,
        role_count=count,
    )


def record(resolution: Resolution) -> None:
    get_con().execute(
        """
        INSERT OR REPLACE INTO company_ats (
          company_name, platform, token, resolution_method,
          status, reason, last_role_count, resolved_at, last_validated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?,
                  CASE WHEN ? = 'resolved' THEN CURRENT_TIMESTAMP ELSE NULL END,
                  CURRENT_TIMESTAMP)
        """,
        [
            resolution.company_name,
            resolution.platform.value if resolution.platform else None,
            resolution.token,
            resolution.method,
            resolution.status.value,
            resolution.reason.value if resolution.reason else None,
            resolution.role_count,
            resolution.status.value,
        ],
    )


def resolve_all_employers(fetch: Fetcher = http_fetch) -> List[Resolution]:
    """Resolve every resolution-eligible employer, recording both outcomes.

    Feed-discovered companies are excluded -- their roles arrive directly, so an
    absent board URL is not a coverage gap for them.
    """
    results: List[Resolution] = []
    for company in employers_needing_resolution():
        resolution = resolve_company(company, fetch=fetch)
        record(resolution)
        if resolution.status is Status.RESOLVED:
            logger.info(
                "[ATS] %s -> %s/%s (%d roles)",
                resolution.company_name,
                resolution.platform.value,
                resolution.token,
                resolution.role_count,
            )
        else:
            logger.info(
                "[ATS] %s unresolved: %s",
                resolution.company_name,
                resolution.explanation,
            )
        results.append(resolution)
    return results
