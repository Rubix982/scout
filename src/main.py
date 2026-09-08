# src/main.py
"""Entry point. Run with `python -m src.main` (or `make run`)."""

from src.clients import SheetAccessError
from src.db import companies as company_queries
from src.db.init import db_path, init_tables, schema_version
from src.db.insert import SyncError, sync_companies


def main() -> int:
    applied = init_tables()
    if applied:
        print(f"schema: applied {len(applied)} migration(s)")
    print(f"schema version {schema_version()} at {db_path()}")

    try:
        plan = sync_companies()
    except SheetAccessError as exc:
        print(f"\nCould not read the sheet:\n  {exc}")
        return 1
    except SyncError as exc:
        print(f"\nSheet contains a value Scout cannot interpret:\n  {exc}")
        return 1

    print(
        f"companies: +{len(plan.to_insert)} new, ~{len(plan.to_update)} changed, "
        f"-{len(plan.to_delete)} removed, ={plan.unchanged} unchanged"
    )

    # Coverage is stated, never implied. R-002's 19% was measured against a
    # population that silently included 16 non-employers.
    employers = company_queries.employers()
    sources = company_queries.sources()
    unclassified = company_queries.unclassified()
    print(
        f"  tracked as employers: {len(employers)}\n"
        f"  excluded as sources:  {len(sources)}\n"
        f"  unclassified:         {len(unclassified)}"
        + (
            "  <- blank Type in the sheet; not assumed to be employers"
            if unclassified
            else ""
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
