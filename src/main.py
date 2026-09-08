# src/main.py
"""Entry point. Run with `python -m src.main` (or `make run`)."""

from src.clients import SheetAccessError
from src.db import companies as company_queries
from src.db.init import db_path, init_tables, schema_version
from src.db.insert import SyncError, sync_companies
from src.sources.ats.resolve import Status, resolve_all_employers


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

    resolutions = resolve_all_employers()
    resolved = [r for r in resolutions if r.status is Status.RESOLVED]
    unresolved = [r for r in resolutions if r.status is not Status.RESOLVED]

    print(f"\nATS boards: {len(resolved)}/{len(resolutions)} employers resolved")
    for r in sorted(resolved, key=lambda r: -r.role_count):
        print(f"  {r.company_name:24} {r.platform.value:14} {r.token:20} {r.role_count:4d} roles")
    if resolved:
        print(f"  {'':24} {'':14} {'total':20} {sum(r.role_count for r in resolved):4d} roles")
    if unresolved:
        print(f"\n  unresolved ({len(unresolved)}) -- recorded with a reason, not omitted:")
        for r in sorted(unresolved, key=lambda r: r.company_name):
            print(f"    {r.company_name:24} {r.explanation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
