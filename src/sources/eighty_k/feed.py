# src/sources/eighty_k/feed.py
"""80,000 Hours job board as a role feed (E-012).

Unlike the ATS adapters, this source needs **no board-token resolution**: the
roles are already in a public Algolia index, so all 937 arrive in one request.
That sidesteps the constraint R-002 measured, where only 19% of employers could
be resolved to a readable board.

The credentials below are search-only and are published in the board's own page
source -- that is how Algolia InstantSearch works. They are public config, not
secrets, and deliberately do not live in `secrets/`.

Note on curation: 80,000 Hours selects roles by cause area (605 of 937 tagged
"AI safety & policy"). Its distribution therefore describes 80k's editorial
focus as much as the market's, which is why roles are attributed to their source
in storage and in the report rather than pooled with first-party ATS data.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.common.models import Role
from src.db.init import get_con
from src.db.roles import RoleChange, companies_with_open_roles_from, snapshot_company
from src.log import get_logger

logger = get_logger("eighty_k")

#: Platform value under which these roles are stored. Distinct from any ATS, so
#: source-fed roles can never collide with first-party ones.
SOURCE = "80000hours"

APP_ID = "W6KM1UDIB3"
SEARCH_KEY = "d1d7f2c8696e7b36837d5ed337c4a319"  # search-only, public
INDEX = "jobs_prod"
HITS_PER_PAGE = 1000
QUERY_URL = f"https://{APP_ID}-dsn.algolia.net/1/indexes/{INDEX}/query"

#: (status_code, body). status_code None on a transport error.
PageFetcher = Callable[[int], Tuple[Optional[int], bytes]]


def http_page_fetcher(page: int) -> Tuple[Optional[int], bytes]:
    import requests

    try:
        response = requests.post(
            QUERY_URL,
            headers={
                "X-Algolia-Application-Id": APP_ID,
                "X-Algolia-API-Key": SEARCH_KEY,
                "Content-Type": "application/json",
                "User-Agent": "scout/0.1 (+https://github.com/Rubix982/scout)",
            },
            data=json.dumps({"params": f"query=&hitsPerPage={HITS_PER_PAGE}&page={page}"}),
            timeout=30,
        )
        return response.status_code, response.content
    except Exception as exc:
        logger.warning("[80K] transport error on page %d: %s", page, exc)
        return None, b""


def _epoch_seconds_to_iso(value: Any) -> Optional[str]:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _location(hit: Dict[str, Any]) -> str:
    for key in ("card_locations", "tags_city", "tags_country"):
        values = hit.get(key) or []
        if values:
            return ", ".join(str(v) for v in values if v)
    return ""


def parse_hits(hits: Sequence[Dict[str, Any]]) -> List[Role]:
    """Normalise Algolia hits into Role records.

    `department` is left empty on purpose. 80k's `tags_skill` is multi-label --
    53% of roles carry more than one -- while ATS departments partition. Writing
    tags into `department` would make the two silently incomparable; they go to
    `tags` instead.
    """
    roles: List[Role] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        external_id = _text(str(hit.get("post_pk") or hit.get("objectID") or ""))
        company_id = _text(hit.get("company_id")) or _text(hit.get("company_name"))
        if not external_id or not company_id:
            logger.warning("[80K] hit without id or company, skipped")
            continue
        roles.append(
            Role(
                platform=SOURCE,
                token=company_id,
                external_id=external_id,
                title=_text(hit.get("title")),
                location=_location(hit),
                department="",
                url=_text(hit.get("url_external")),
                first_published=_epoch_seconds_to_iso(hit.get("posted_at"))
                or _epoch_seconds_to_iso(hit.get("created_at")),
                updated_at=_epoch_seconds_to_iso(hit.get("updated_at")),
                raw=json.dumps(hit, sort_keys=True),
                tags=tuple(str(t) for t in (hit.get("tags_skill") or []) if t),
                evergreen_flag=bool(hit["evergreen"]) if "evergreen" in hit else None,
            )
        )
    return roles


def fetch_all_roles(fetch: PageFetcher = http_page_fetcher) -> Tuple[bool, List[Role]]:
    """Fetch every page. Returns (ok, roles).

    `ok` is False if **any** page failed. A partial feed must not be treated as
    complete, or the missing pages' roles would be closed as though the source
    had dropped them.
    """
    roles: List[Role] = []
    page = 0
    while True:
        status, body = fetch(page)
        if status != 200:
            logger.warning("[80K] page %d returned %s -- aborting", page, status)
            return False, []
        try:
            payload = json.loads(body)
        except Exception:
            logger.warning("[80K] page %d unparseable -- aborting", page)
            return False, []

        roles.extend(parse_hits(payload.get("hits") or []))
        n_pages = int(payload.get("nbPages") or 1)
        if page >= n_pages - 1:
            break
        page += 1
    return True, roles


def _record_companies(roles: Sequence[Role]) -> int:
    """Register discovered companies, without disturbing sheet-owned rows.

    Inserted with `source = SOURCE` so the sheet delta sync -- which deletes any
    `companies` row absent from the sheet -- leaves them alone (migration 006).
    """
    con = get_con()
    by_name = {r.token: r for r in roles}
    inserted = 0
    for role in by_name.values():
        name = _company_name_for(role)
        exists = con.execute(
            "SELECT count(*) FROM companies WHERE company_name = ?", [name]
        ).fetchone()[0]
        if exists:
            continue
        con.execute(
            "INSERT INTO companies (company_name, comments, link, entity_type, "
            "board_url, source) VALUES (?, '', '', 'employer', '', ?)",
            [name, SOURCE],
        )
        inserted += 1
    return inserted


def _company_name_for(role: Role) -> str:
    """Human-readable company name, recovered from the retained payload."""
    try:
        return _text(json.loads(role.raw).get("company_name")) or role.token
    except Exception:
        return role.token


def run_feed_snapshot(
    run_id: int, fetch: PageFetcher = http_page_fetcher
) -> Tuple[bool, List[RoleChange], int]:
    """Snapshot the whole feed. Returns (ok, changes, company_count).

    On a failed fetch this closes nothing at all -- the same guardrail the ATS
    snapshot runner enforces. On success, companies that previously had open
    roles here and are now absent have those roles closed, because a whole-feed
    fetch makes absence real information.
    """
    ok, roles = fetch_all_roles(fetch)
    if not ok:
        logger.warning("[80K] feed fetch failed -- nothing closed")
        return False, [], 0

    _record_companies(roles)

    grouped: Dict[str, List[Role]] = {}
    for role in roles:
        grouped.setdefault(_company_name_for(role), []).append(role)

    changes: List[RoleChange] = []
    for company_name, company_roles in grouped.items():
        changes.extend(snapshot_company(run_id, company_name, company_roles))

    # Source-level close: previously seen here, absent from a successful fetch.
    for company_name in companies_with_open_roles_from(SOURCE):
        if company_name not in grouped:
            changes.extend(snapshot_company(run_id, company_name, []))

    logger.info(
        "[80K] %d roles across %d companies, %d change(s)",
        len(roles), len(grouped), len(changes),
    )
    return True, changes, len(grouped)
