# src/sources/ats/roles.py
"""Normalise ATS job payloads into a single Role record (E-003).

Field names and shapes below were read off live responses, not documentation.
The three platforms disagree more than the original design assumed:

===========  ===============  =====================  ==================
field        Greenhouse       Lever                  Ashby
===========  ===============  =====================  ==================
id           int              uuid str               uuid str
title        ``title``        ``text``               ``title``
location     ``location.name`` ``categories.location`` ``location``
department   ``metadata[]``   ``categories.department`` ``department``
created      first_published  ``createdAt`` (epoch ms) ``publishedAt``
**updated**  ``updated_at``   **absent**             **absent**
===========  ===============  =====================  ==================

**Only Greenhouse reports a modification time.** Lever and Ashby expose creation
time alone, so run-over-run change detection cannot rely on `updated_at` -- it
has to compare the normalised fields themselves. That constrains E-005 and is
recorded in findings.

Greenhouse's ``?content=true`` **is** used by default, despite costing ~15x the
payload. An earlier version of this module avoided it and read department from
``metadata`` as "External Department" instead. That was wrong:

- ``metadata`` entries are *tenant-defined custom fields*, not a schema. Affirm
  happens to define "External Department"; wolt defines three different
  department-ish keys ("Wolt: Careers Site Department", "Careers Page Sorting:
  Department", "Job Family") and fingerprint defines only "Employment Type".
- ``departments[]`` is the actual Greenhouse field, and it is empty unless
  ``content=true``. With it, coverage is total: 242/242 for wolt, 23/23 for
  fingerprint.

Measured, department was populated for affirm alone -- 212 of 477 roles -- and
empty for the 265 belonging to wolt and fingerprint. Since the v1 deliverable is
role mix *by department* (E-006), the cheaper request loses the field the report
is built on. ~5.4MB per run across three boards is a fine price for a tool that
runs locally on a schedule, and it hands thread T-005 its answer for free: the
JD text arrives too.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.log import get_logger
from src.sources.ats.platforms import ENDPOINTS, Platform

logger = get_logger("ats.roles")

Fetcher = Callable[[str], Tuple[Optional[int], bytes]]


@dataclass(frozen=True)
class Role:
    """One open role, normalised across platforms."""

    platform: str
    token: str
    external_id: str
    title: str
    location: str
    department: str
    url: str
    first_published: Optional[str]
    updated_at: Optional[str]
    raw: str

    @property
    def identity(self) -> Tuple[str, str, str]:
        """Stable identity for diffing.

        Keyed on the ATS id, never the title: R-002 noted reposts and title
        churn, and keying on title would manufacture phantom "new role" events.
        """
        return (self.platform, self.token, self.external_id)


def _epoch_ms_to_iso(value: Any) -> Optional[str]:
    """Lever reports createdAt as epoch milliseconds."""
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _greenhouse_department(job: Dict[str, Any]) -> str:
    """Prefer the real `departments[]` field; fall back to custom metadata.

    The fallback only helps tenants that happen to define an
    "External Department" custom field (affirm does; wolt and fingerprint do
    not), so it is a courtesy for `content=false` callers, never the main path.
    """
    departments = job.get("departments") or []
    if departments:
        name = _text(departments[0].get("name"))
        if name:
            return name
    for entry in job.get("metadata") or []:
        if entry.get("name") == "External Department" and entry.get("value"):
            return _text(entry["value"])
    return ""


def _normalise_greenhouse(platform: Platform, token: str, job: Dict[str, Any]) -> Role:
    return Role(
        platform=platform.value,
        token=token,
        external_id=str(job.get("id", "")),
        title=_text(job.get("title")),
        location=_text((job.get("location") or {}).get("name")),
        department=_greenhouse_department(job),
        url=_text(job.get("absolute_url")),
        first_published=_text(job.get("first_published")) or None,
        updated_at=_text(job.get("updated_at")) or None,
        raw=json.dumps(job, sort_keys=True),
    )


def _normalise_lever(platform: Platform, token: str, job: Dict[str, Any]) -> Role:
    categories = job.get("categories") or {}
    return Role(
        platform=platform.value,
        token=token,
        external_id=_text(job.get("id")),
        # Lever calls the title `text`; there is no `title` key at all.
        title=_text(job.get("text")),
        location=_text(categories.get("location")),
        department=_text(categories.get("department")),
        url=_text(job.get("hostedUrl")),
        first_published=_epoch_ms_to_iso(job.get("createdAt")),
        updated_at=None,  # Lever does not expose one
        raw=json.dumps(job, sort_keys=True),
    )


def _normalise_ashby(platform: Platform, token: str, job: Dict[str, Any]) -> Role:
    return Role(
        platform=platform.value,
        token=token,
        external_id=_text(job.get("id")),
        title=_text(job.get("title")),
        location=_text(job.get("location")),
        department=_text(job.get("department")),
        url=_text(job.get("jobUrl")),
        first_published=_text(job.get("publishedAt")) or None,
        updated_at=None,  # Ashby does not expose one
        raw=json.dumps(job, sort_keys=True),
    )


def _jobs_from_payload(platform: Platform, payload: Any) -> List[Dict[str, Any]]:
    if platform is Platform.LEVER:
        return payload if isinstance(payload, list) else []
    if not isinstance(payload, dict):
        return []
    jobs = payload.get("jobs")
    return jobs if isinstance(jobs, list) else []


_NORMALISERS = {
    Platform.GREENHOUSE: _normalise_greenhouse,
    Platform.GREENHOUSE_EU: _normalise_greenhouse,
    Platform.LEVER: _normalise_lever,
    Platform.ASHBY: _normalise_ashby,
}


def parse_roles(platform: Platform, token: str, body: bytes) -> List[Role]:
    """Normalise a response body into Role records."""
    normalise = _NORMALISERS.get(platform)
    if normalise is None:
        raise ValueError(f"no adapter for platform {platform.value!r}")
    try:
        payload = json.loads(body)
    except Exception:
        logger.warning("[ROLES] %s/%s: unparseable body", platform.value, token)
        return []

    roles: List[Role] = []
    for job in _jobs_from_payload(platform, payload):
        if not isinstance(job, dict):
            continue
        role = normalise(platform, token, job)
        if not role.external_id:
            logger.warning("[ROLES] %s/%s: job with no id, skipped", platform.value, token)
            continue
        roles.append(role)
    return roles


def endpoint_for(platform: Platform, token: str, *, include_content: bool = True) -> str:
    url = ENDPOINTS[platform].format(token=token)
    if include_content and platform in (Platform.GREENHOUSE, Platform.GREENHOUSE_EU):
        url += ("&" if "?" in url else "?") + "content=true"
    return url


def fetch_roles(
    platform: Platform,
    token: str,
    fetch: Fetcher,
    *,
    include_content: bool = True,
) -> List[Role]:
    """Fetch and normalise every open role for one board.

    `include_content` defaults True because Greenhouse omits `departments[]`
    without it -- see the module docstring. Pass False when only titles and
    locations are needed and payload size matters.
    """
    status, body = fetch(endpoint_for(platform, token, include_content=include_content))
    if status != 200:
        logger.warning("[ROLES] %s/%s: HTTP %s", platform.value, token, status)
        return []
    return parse_roles(platform, token, body)
