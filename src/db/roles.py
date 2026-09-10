# src/db/roles.py
"""Role snapshots and run-over-run diffing (E-005).

This is the part that makes Scout more than a job board: history.

Two correctness rules drive the design.

**Identity is the stable ATS id, never the title.** R-002 noted reposts and
title churn; keying on title would manufacture phantom "new role" events. A
renamed role is a `changed` event, not an `appeared` one.

**A failed fetch must close nothing.** Roles are only closed for companies whose
fetch actually succeeded in that run. Otherwise one network blip would mark an
entire company's roles as closed and report it as mass hiring freeze.

Change detection compares *content*, not timestamps: E-003 established that only
Greenhouse reports `updated_at`, so a timestamp-based design would silently
never detect changes on Lever or Ashby.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.db.init import get_con
from src.log import get_logger
from src.common.models import Role

logger = get_logger("roles")

#: Fields whose change is worth recording. Deliberately excludes `raw` (noisy:
#: any upstream field churn would fire) and the timestamps (not comparable
#: across platforms).
COMPARE_FIELDS: Tuple[str, ...] = ("title", "location", "department", "url")

Identity = Tuple[str, str, str]


class ChangeType(str, Enum):
    APPEARED = "appeared"
    CHANGED = "changed"
    CLOSED = "closed"
    REOPENED = "reopened"


@dataclass(frozen=True)
class RoleChange:
    change_type: ChangeType
    company_name: str
    platform: str
    token: str
    external_id: str
    title: str = ""
    field: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None


# --- runs ---------------------------------------------------------------------


def start_run() -> int:
    con = get_con()
    con.execute("INSERT INTO runs (started_at) VALUES (CURRENT_TIMESTAMP)")
    return int(con.execute("SELECT max(run_id) FROM runs").fetchone()[0])


def finish_run(
    run_id: int, *, attempted: int, fetched: int, failed: int, roles_seen: int
) -> None:
    get_con().execute(
        """
        UPDATE runs SET finished_at = CURRENT_TIMESTAMP,
          companies_attempted = ?, companies_fetched = ?,
          companies_failed = ?, roles_seen = ?
        WHERE run_id = ?
        """,
        [attempted, fetched, failed, roles_seen, run_id],
    )


def completed_runs() -> List[int]:
    return [
        int(r[0])
        for r in get_con()
        .execute("SELECT run_id FROM runs WHERE finished_at IS NOT NULL ORDER BY run_id")
        .fetchall()
    ]


def previous_completed_run(before: int) -> Optional[int]:
    row = (
        get_con()
        .execute(
            "SELECT max(run_id) FROM runs WHERE finished_at IS NOT NULL AND run_id < ?",
            [before],
        )
        .fetchone()
    )
    return int(row[0]) if row and row[0] is not None else None


# --- snapshots ----------------------------------------------------------------


def _existing_for_company(company_name: str) -> Dict[Identity, dict]:
    rows = (
        get_con()
        .execute(
            "SELECT platform, token, external_id, title, location, department, url, "
            "closed_at FROM roles WHERE company_name = ?",
            [company_name],
        )
        .fetchall()
    )
    out: Dict[Identity, dict] = {}
    for platform, token, external_id, title, location, department, url, closed_at in rows:
        out[(platform, token, external_id)] = {
            "title": title or "",
            "location": location or "",
            "department": department or "",
            "url": url or "",
            "closed_at": closed_at,
        }
    return out


def _record_change(run_id: int, change: RoleChange) -> None:
    get_con().execute(
        """
        INSERT INTO role_changes (
          run_id, platform, token, external_id, company_name, title,
          change_type, field, old_value, new_value
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            run_id,
            change.platform,
            change.token,
            change.external_id,
            change.company_name,
            change.title,
            change.change_type.value,
            change.field,
            change.old_value,
            change.new_value,
        ],
    )


def snapshot_company(
    run_id: int, company_name: str, roles: Sequence[Role]
) -> List[RoleChange]:
    """Record one company's roles for this run and diff against the last state.

    **Only call this for a company whose fetch succeeded.** Passing an empty
    list because a request failed would close every role the company has. The
    caller must distinguish "fetched, zero roles" from "fetch failed"; see
    `src/sources/ats/snapshot.py`.
    """
    con = get_con()
    existing = _existing_for_company(company_name)
    changes: List[RoleChange] = []
    seen: set[Identity] = set()

    for role in roles:
        key = role.identity
        seen.add(key)
        prior = existing.get(key)

        if prior is None:
            con.execute(
                """
                INSERT INTO roles (
                  platform, token, external_id, company_name, title, location,
                  department, url, first_published, updated_at, raw,
                  tags, is_evergreen,
                  first_seen, last_seen, closed_at, first_seen_run, last_seen_run
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, ?, ?)
                """,
                [
                    role.platform, role.token, role.external_id, company_name,
                    role.title, role.location, role.department, role.url,
                    role.first_published, role.updated_at, role.raw,
                    json.dumps(list(role.tags)) if role.tags else None,
                    role.evergreen_flag,
                    run_id, run_id,
                ],
            )
            change = RoleChange(
                ChangeType.APPEARED, company_name, role.platform, role.token,
                role.external_id, role.title,
            )
            changes.append(change)
            _record_change(run_id, change)
            continue

        # Seen before: note any field change, and any return from closed.
        if prior["closed_at"] is not None:
            change = RoleChange(
                ChangeType.REOPENED, company_name, role.platform, role.token,
                role.external_id, role.title,
            )
            changes.append(change)
            _record_change(run_id, change)

        for field in COMPARE_FIELDS:
            new_value = getattr(role, field) or ""
            if prior[field] != new_value:
                change = RoleChange(
                    ChangeType.CHANGED, company_name, role.platform, role.token,
                    role.external_id, role.title,
                    field=field, old_value=prior[field], new_value=new_value,
                )
                changes.append(change)
                _record_change(run_id, change)

        con.execute(
            """
            UPDATE roles SET
              title = ?, location = ?, department = ?, url = ?,
              first_published = ?, updated_at = ?, raw = ?,
              tags = ?, is_evergreen = ?,
              last_seen = CURRENT_TIMESTAMP, last_seen_run = ?, closed_at = NULL
            WHERE platform = ? AND token = ? AND external_id = ?
            """,
            [
                role.title, role.location, role.department, role.url,
                role.first_published, role.updated_at, role.raw,
                json.dumps(list(role.tags)) if role.tags else None,
                role.evergreen_flag, run_id,
                role.platform, role.token, role.external_id,
            ],
        )

    # Roles the board no longer lists. Only reachable because this fetch
    # succeeded -- see the docstring.
    for key, prior in existing.items():
        if key in seen or prior["closed_at"] is not None:
            continue
        platform, token, external_id = key
        con.execute(
            """
            UPDATE roles SET closed_at = CURRENT_TIMESTAMP, last_seen_run = ?
            WHERE platform = ? AND token = ? AND external_id = ?
            """,
            [run_id, platform, token, external_id],
        )
        change = RoleChange(
            ChangeType.CLOSED, company_name, platform, token, external_id,
            prior["title"],
        )
        changes.append(change)
        _record_change(run_id, change)

    return changes


# --- queries ------------------------------------------------------------------


def open_role_count(company_name: Optional[str] = None) -> int:
    sql = "SELECT count(*) FROM roles WHERE closed_at IS NULL"
    params: List[str] = []
    if company_name:
        sql += " AND company_name = ?"
        params.append(company_name)
    return int(get_con().execute(sql, params).fetchone()[0])


@dataclass(frozen=True)
class OpenRole:
    company_name: str
    platform: str
    external_id: str
    title: str
    location: str
    department: str
    url: str
    first_published: Optional[str]
    first_seen_run: Optional[int]
    tags_json: Optional[str] = None
    is_evergreen_flag: Optional[bool] = None

    @property
    def tags(self) -> List[str]:
        if not self.tags_json:
            return []
        try:
            return list(json.loads(self.tags_json))
        except Exception:
            return []

    @property
    def evergreen(self) -> bool:
        """Source flag when present, title heuristic otherwise."""
        if self.is_evergreen_flag is not None:
            return bool(self.is_evergreen_flag)
        from src.common.models import is_evergreen

        return is_evergreen(self.title)


def open_roles(company_name: Optional[str] = None) -> List[OpenRole]:
    sql = (
        "SELECT company_name, platform, external_id, title, location, department, "
        "url, first_published, first_seen_run, tags, is_evergreen "
        "FROM roles WHERE closed_at IS NULL"
    )
    params: List[object] = []
    if company_name:
        sql += " AND company_name = ?"
        params.append(company_name)
    sql += " ORDER BY company_name, title"
    return [OpenRole(*row) for row in get_con().execute(sql, params).fetchall()]


def companies_with_open_roles_from(platform: str) -> List[str]:
    """Companies that currently have open roles attributed to `platform`.

    Used for source-level closing: a feed is fetched whole, so a company absent
    from a *successful* fetch really has no live roles there any more.
    """
    return [
        r[0]
        for r in get_con()
        .execute(
            "SELECT DISTINCT company_name FROM roles "
            "WHERE platform = ? AND closed_at IS NULL",
            [platform],
        )
        .fetchall()
    ]


def latest_completed_run() -> Optional[int]:
    row = get_con().execute(
        "SELECT max(run_id) FROM runs WHERE finished_at IS NOT NULL"
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def run_summary(run_id: int) -> Optional[dict]:
    row = get_con().execute(
        "SELECT run_id, started_at, finished_at, companies_attempted, "
        "companies_fetched, companies_failed, roles_seen FROM runs WHERE run_id = ?",
        [run_id],
    ).fetchone()
    if row is None:
        return None
    keys = ("run_id", "started_at", "finished_at", "attempted", "fetched", "failed", "roles_seen")
    return dict(zip(keys, row))


def changes_for_run(run_id: int, change_type: Optional[ChangeType] = None) -> List[dict]:
    sql = (
        "SELECT company_name, change_type, title, field, old_value, new_value, "
        "external_id FROM role_changes WHERE run_id = ?"
    )
    params: List[object] = [run_id]
    if change_type is not None:
        sql += " AND change_type = ?"
        params.append(change_type.value)
    sql += " ORDER BY company_name, change_type, title"
    keys = (
        "company_name", "change_type", "title", "field",
        "old_value", "new_value", "external_id",
    )
    return [dict(zip(keys, row)) for row in get_con().execute(sql, params).fetchall()]


def department_mix(company_name: str) -> List[Tuple[str, int, float]]:
    """Open roles by department, as (name, count, share).

    Share rather than count: company size co-varies with posting volume, so raw
    counts compare headcount instead of focus (plan.md lens 6).
    """
    rows = (
        get_con()
        .execute(
            "SELECT coalesce(nullif(department, ''), '(unspecified)'), count(*) "
            "FROM roles WHERE company_name = ? AND closed_at IS NULL "
            "GROUP BY 1 ORDER BY 2 DESC, 1",
            [company_name],
        )
        .fetchall()
    )
    total = sum(n for _, n in rows) or 1
    return [(name, n, n / total) for name, n in rows]
