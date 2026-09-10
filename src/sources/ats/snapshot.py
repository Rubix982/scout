# src/sources/ats/snapshot.py
"""Drive one snapshot run across all resolved employers (E-005).

This module calls the fetcher directly rather than going through
`fetch_roles()`, because `fetch_roles` returns `[]` on a failed request and that
collapses the one distinction that matters here:

- **fetched, zero roles** -> the board is genuinely empty; close everything
- **fetch failed**        -> we know nothing; close nothing

Conflating them would let a single network blip mark an entire company's roles
as closed and report it as a hiring freeze.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from src.db.init import get_con
from src.db.roles import (
    ChangeType,
    RoleChange,
    finish_run,
    previous_completed_run,
    snapshot_company,
    start_run,
)
from src.log import get_logger
from src.sources.ats.platforms import Platform
from src.sources.ats.resolve import Fetcher, http_fetch
from src.sources.ats.roles import endpoint_for, parse_roles
from src.sources.eighty_k.feed import SOURCE as FEED_SOURCE
from src.sources.eighty_k.feed import PageFetcher, http_page_fetcher, run_feed_snapshot

logger = get_logger("ats.snapshot")


@dataclass(frozen=True)
class CompanyOutcome:
    company_name: str
    platform: str
    token: str
    ok: bool
    role_count: int = 0
    changes: Sequence[RoleChange] = ()
    error: Optional[str] = None


@dataclass
class RunReport:
    run_id: int
    previous_run_id: Optional[int]
    outcomes: List[CompanyOutcome] = field(default_factory=list)
    #: Feed results are tracked separately: a feed is fetched whole, so it is
    #: one success/failure rather than one per company.
    feed_ok: Optional[bool] = None
    feed_companies: int = 0
    feed_roles: int = 0
    feed_changes: List[RoleChange] = field(default_factory=list)

    @property
    def fetched(self) -> List[CompanyOutcome]:
        return [o for o in self.outcomes if o.ok]

    @property
    def failed(self) -> List[CompanyOutcome]:
        return [o for o in self.outcomes if not o.ok]

    @property
    def roles_seen(self) -> int:
        return sum(o.role_count for o in self.fetched) + self.feed_roles

    @property
    def changes(self) -> List[RoleChange]:
        return [c for o in self.outcomes for c in o.changes] + list(self.feed_changes)

    def of_type(self, change_type: ChangeType) -> List[RoleChange]:
        return [c for c in self.changes if c.change_type is change_type]

    @property
    def is_first_run(self) -> bool:
        return self.previous_run_id is None


def resolved_boards() -> List[tuple]:
    """(company_name, platform, token) for every employer with a live board."""
    return get_con().execute(
        "SELECT company_name, platform, token FROM company_ats "
        "WHERE status = 'resolved' AND platform IS NOT NULL AND token IS NOT NULL "
        "ORDER BY company_name"
    ).fetchall()


def run_snapshot(
    fetch: Fetcher = http_fetch,
    *,
    include_content: bool = True,
    include_feed: bool = False,
    feed_fetch: Optional[PageFetcher] = None,
) -> RunReport:
    """Snapshot every resolved board, and optionally the 80,000 Hours feed.

    `include_feed` defaults **False** so that calling this function never makes
    an unrequested network round-trip. It defaulted True briefly and the test
    suite silently began hitting the live Algolia index -- 937 real roles into a
    temp database, and 77s of runtime. The decision to reach the network belongs
    at the CLI edge, not in a library default.
    """
    run_id = start_run()
    report = RunReport(run_id=run_id, previous_run_id=previous_completed_run(run_id))

    for company_name, platform_value, token in resolved_boards():
        platform = Platform(platform_value)
        url = endpoint_for(platform, token, include_content=include_content)
        status, body = fetch(url)

        if status != 200:
            # Explicitly do NOT snapshot. Nothing is closed for this company.
            logger.warning(
                "[SNAPSHOT] %s (%s/%s): HTTP %s -- skipped, nothing closed",
                company_name, platform_value, token, status,
            )
            report.outcomes.append(
                CompanyOutcome(
                    company_name, platform_value, token, ok=False,
                    error=f"HTTP {status}",
                )
            )
            continue

        roles = parse_roles(platform, token, body)
        changes = snapshot_company(run_id, company_name, roles)
        logger.info(
            "[SNAPSHOT] %s: %d roles, %d change(s)",
            company_name, len(roles), len(changes),
        )
        report.outcomes.append(
            CompanyOutcome(
                company_name, platform_value, token, ok=True,
                role_count=len(roles), changes=changes,
            )
        )

    if include_feed:
        ok, feed_changes, n_companies = run_feed_snapshot(
            run_id, feed_fetch or http_page_fetcher
        )
        report.feed_ok = ok
        report.feed_changes = feed_changes
        report.feed_companies = n_companies
        if ok:
            report.feed_roles = open_role_count_for_platform(FEED_SOURCE)

    finish_run(
        run_id,
        attempted=len(report.outcomes) + (1 if include_feed else 0),
        fetched=len(report.fetched) + (1 if report.feed_ok else 0),
        failed=len(report.failed) + (1 if report.feed_ok is False else 0),
        roles_seen=report.roles_seen,
    )
    return report


def open_role_count_for_platform(platform: str) -> int:
    return int(
        get_con()
        .execute(
            "SELECT count(*) FROM roles WHERE platform = ? AND closed_at IS NULL",
            [platform],
        )
        .fetchone()[0]
    )
