# src/db/companies.py
"""Queries over the company list, split by entity kind (E-010).

Role tracking must only ever consider employers. A job board or recruiting
agency has postings, but they are not *its* roles -- R-002 found
`OnHires/482 Solutions` contributing 47 client roles and Greenhouse-the-vendor
contributing its own 18, both of which would corrupt any role-mix claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from src.common.entities import EntityType
from src.db.init import get_con


@dataclass(frozen=True)
class Company:
    company_name: str
    entity_type: str
    comments: str
    link: str


def _rows(where: str = "", params: tuple = ()) -> List[Company]:
    sql = (
        "SELECT company_name, entity_type, comments, link FROM companies "
        f"{where} ORDER BY company_name"
    )
    return [Company(*r) for r in get_con().execute(sql, list(params)).fetchall()]


def all_companies() -> List[Company]:
    return _rows()


def employers() -> List[Company]:
    """The only rows eligible for role tracking."""
    return _rows("WHERE entity_type = ?", (EntityType.EMPLOYER.value,))


def sources() -> List[Company]:
    """Rows that yield companies rather than roles. Excluded from tracking."""
    kinds = [e.value for e in EntityType if e.is_source]
    placeholders = ", ".join("?" * len(kinds))
    return _rows(f"WHERE entity_type IN ({placeholders})", tuple(kinds))


def unclassified() -> List[Company]:
    """Rows with no type yet. Surfaced as a count, never assumed to be employers."""
    return _rows("WHERE entity_type = ?", (EntityType.UNKNOWN.value,))


def counts_by_type() -> Dict[str, int]:
    rows = get_con().execute(
        "SELECT entity_type, count(*) FROM companies GROUP BY entity_type"
    ).fetchall()
    return {t: n for t, n in sorted(rows, key=lambda r: -r[1])}
