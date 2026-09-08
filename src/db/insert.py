# src/db/insert.py
"""Sheet -> DuckDB delta sync.

Declarative: a `SheetTable` states the worksheet-header -> db-column mapping, and
one code path handles any table. Previously five parallel `if table_name == ...`
dispatch functions carried the schema, and column names were reconstructed by
title-casing the db column (`prettify_column_names`), so renaming a sheet header
broke the insert silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from src.db.init import get_con
from src.log import get_logger

logger = get_logger("sync")


@dataclass(frozen=True)
class SheetTable:
    """Maps one worksheet onto one DuckDB table."""

    table: str
    primary_key: str
    columns: Mapping[str, str]  # sheet header -> db column

    @property
    def db_columns(self) -> Tuple[str, ...]:
        return tuple(self.columns.values())

    @property
    def compare_columns(self) -> Tuple[str, ...]:
        return tuple(c for c in self.db_columns if c != self.primary_key)


COMPANIES = SheetTable(
    table="companies",
    primary_key="company_name",
    columns={
        "Company Name": "company_name",
        "Comments": "comments",
        "Link": "link",
    },
)


def normalize(value: Any) -> str:
    """Render a value into a form comparable across Sheets and DuckDB.

    Sheet cells arrive as strings (`"TRUE"`, `""`), DuckDB returns native types
    (`True`, `None`). Comparing them raw made every row look changed on every
    run, so the delta reported 36 updates forever and never converged.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, str):
        return value.strip()
    return str(value)


def to_db_row(spec: SheetTable, sheet_row: Mapping[str, Any]) -> Dict[str, str]:
    """Project a sheet record onto db columns via the explicit mapping."""
    return {
        db_col: normalize(sheet_row.get(header))
        for header, db_col in spec.columns.items()
    }


@dataclass(frozen=True)
class SyncPlan:
    to_insert: List[Dict[str, str]]
    to_update: List[Dict[str, str]]
    to_delete: List[str]
    unchanged: int

    @property
    def changes(self) -> int:
        return len(self.to_insert) + len(self.to_update) + len(self.to_delete)


def fetch_existing(spec: SheetTable) -> Dict[str, Dict[str, str]]:
    cols = ", ".join(spec.db_columns)
    rows = get_con().execute(f"SELECT {cols} FROM {spec.table}").fetchall()
    out: Dict[str, Dict[str, str]] = {}
    for row in rows:
        record = {col: normalize(val) for col, val in zip(spec.db_columns, row)}
        out[record[spec.primary_key]] = record
    return out


def compute_plan(
    spec: SheetTable,
    existing: Mapping[str, Mapping[str, str]],
    incoming: Sequence[Mapping[str, Any]],
) -> SyncPlan:
    to_insert: List[Dict[str, str]] = []
    to_update: List[Dict[str, str]] = []
    unchanged = 0
    seen: set[str] = set()

    for sheet_row in incoming:
        record = to_db_row(spec, sheet_row)
        key = record[spec.primary_key]
        if not key:
            logger.warning("[SYNC] skipping row with empty %s", spec.primary_key)
            continue
        if key in seen:
            logger.warning("[SYNC] duplicate %s %r -- keeping first", spec.primary_key, key)
            continue
        seen.add(key)

        prior = existing.get(key)
        if prior is None:
            to_insert.append(record)
        elif any(record[c] != prior.get(c, "") for c in spec.compare_columns):
            to_update.append(record)
        else:
            unchanged += 1

    to_delete = [k for k in existing if k not in seen]
    return SyncPlan(to_insert, to_update, to_delete, unchanged)


def apply_plan(spec: SheetTable, plan: SyncPlan) -> None:
    con = get_con()
    cols = ", ".join(spec.db_columns)
    placeholders = ", ".join("?" * len(spec.db_columns))
    upsert = f"INSERT OR REPLACE INTO {spec.table} ({cols}) VALUES ({placeholders})"

    for record in plan.to_insert + plan.to_update:
        con.execute(upsert, [record[c] for c in spec.db_columns])
    for key in plan.to_delete:
        con.execute(
            f"DELETE FROM {spec.table} WHERE {spec.primary_key} = ?", [key]
        )


def sync(spec: SheetTable, incoming: Sequence[Mapping[str, Any]]) -> SyncPlan:
    """Sync `incoming` sheet records into `spec.table`.

    Rows are passed in rather than fetched here, so the delta logic is testable
    without network access.
    """
    plan = compute_plan(spec, fetch_existing(spec), incoming)
    apply_plan(spec, plan)
    logger.info(
        "[SYNC] %s: +%d insert, ~%d update, -%d delete, =%d unchanged",
        spec.table,
        len(plan.to_insert),
        len(plan.to_update),
        len(plan.to_delete),
        plan.unchanged,
    )
    return plan


def sync_companies() -> SyncPlan:
    from src.clients import get_companies

    return sync(COMPANIES, get_companies())
