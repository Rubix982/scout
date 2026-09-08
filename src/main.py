# src/main.py
"""Entry point. Run with `python -m src.main` (or `make run`)."""

from src.clients import SheetAccessError
from src.db import companies as company_queries
from src.db.init import db_path, init_tables, schema_version
from src.db.insert import SyncError, sync_companies
from src.db.roles import ChangeType, open_role_count
from src.sources.ats.resolve import Status, resolve_all_employers
from src.sources.ats.snapshot import run_snapshot


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

    if not resolved:
        print("\nNo resolved boards -- nothing to snapshot.")
        return 0

    report = run_snapshot()
    print(f"\nRun {report.run_id}: {len(report.fetched)}/{len(report.outcomes)} boards fetched, "
          f"{report.roles_seen} roles seen, {open_role_count()} open in total")
    if report.failed:
        print(f"  {len(report.failed)} board(s) failed -- nothing closed for them:")
        for o in report.failed:
            print(f"    {o.company_name:24} {o.error}")

    if report.is_first_run:
        print("  first run -- establishing the baseline, so every role reads as new")

    for change_type, label in (
        (ChangeType.APPEARED, "new"),
        (ChangeType.CLOSED, "closed"),
        (ChangeType.REOPENED, "reopened"),
        (ChangeType.CHANGED, "changed"),
    ):
        items = report.of_type(change_type)
        if not items:
            continue
        print(f"\n  {label} ({len(items)}):")
        for c in items[:15]:
            detail = f"  {c.field}: {c.old_value!r} -> {c.new_value!r}" if c.field else ""
            print(f"    {c.company_name:14} {c.title[:52]:54}{detail}")
        if len(items) > 15:
            print(f"    ... and {len(items) - 15} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
