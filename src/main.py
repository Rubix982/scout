# src/main.py
"""Entry point. Run with `python -m src.main` (or `make run`)."""

from src.clients import SheetAccessError
from src.db.init import db_path, init_tables, schema_version
from src.db.insert import sync_companies


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

    print(
        f"companies: +{len(plan.to_insert)} new, ~{len(plan.to_update)} changed, "
        f"-{len(plan.to_delete)} removed, ={plan.unchanged} unchanged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
