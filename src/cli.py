# src/cli.py
"""Scout command line.

`report` carries the v1 deliverable (plan.md lens 9): what changed since the
last run, which companies are hiring for what, and -- stated as a first-class
number rather than implied -- how much of the list Scout cannot see.

Deliberately absent in v1: alignment scoring (thread T-004, needs the role
corpus first) and any trend claim over time. Several months of history are
required before "they are investing in X" beats the null hypothesis that the
company simply posts a lot of everything (plan.md lens 6/7).
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Sequence

from src.clients import SheetAccessError
from src.common.models import is_evergreen
from src.db import companies as company_queries
from src.db.init import db_path, init_tables, schema_version
from src.db.insert import SyncError, sync_companies
from src.db.roles import (
    ChangeType,
    changes_for_run,
    latest_completed_run,
    open_roles,
    previous_completed_run,
    run_summary,
)
from src.sources.ats.resolve import Status, resolve_all_employers
from src.sources.ats.snapshot import run_snapshot
from src.sources.eighty_k.feed import SOURCE as FEED_SOURCE

BAR_WIDTH = 24


def _bar(share: float) -> str:
    filled = round(share * BAR_WIDTH)
    return "#" * filled + "." * (BAR_WIDTH - filled)


def _rule(title: str) -> str:
    return f"\n{title}\n{'-' * len(title)}"


# --- sync ---------------------------------------------------------------------


def cmd_sync(_args) -> int:
    init_tables()
    try:
        plan = sync_companies()
    except SheetAccessError as exc:
        print(f"Could not read the sheet:\n  {exc}")
        return 1
    except SyncError as exc:
        print(f"Sheet contains a value Scout cannot interpret:\n  {exc}")
        return 1

    print(
        f"companies: +{len(plan.to_insert)} new, ~{len(plan.to_update)} changed, "
        f"-{len(plan.to_delete)} removed, ={plan.unchanged} unchanged"
    )
    resolutions = resolve_all_employers()
    resolved = [r for r in resolutions if r.status is Status.RESOLVED]
    print(f"boards: {len(resolved)}/{len(resolutions)} employers resolved")
    return 0


# --- snapshot -----------------------------------------------------------------


def cmd_snapshot(_args) -> int:
    init_tables()
    report = run_snapshot(include_feed=True)
    print(
        f"run {report.run_id}: {len(report.fetched)}/{len(report.outcomes)} boards "
        f"fetched, {report.roles_seen} roles seen"
    )
    if report.feed_ok is False:
        print("  FAILED 80,000 Hours feed (nothing closed for it)")
    elif report.feed_ok:
        print(
            f"  80,000 Hours feed: {report.feed_roles} roles across "
            f"{report.feed_companies} organisations"
        )
    for outcome in report.failed:
        print(f"  FAILED {outcome.company_name}: {outcome.error} (nothing closed)")
    for change_type in ChangeType:
        n = len(report.of_type(change_type))
        if n:
            print(f"  {change_type.value}: {n}")
    return 0


# --- report -------------------------------------------------------------------


def _coverage_section() -> None:
    sheet_employers = company_queries.employers_from("sheet")
    feed_employers = company_queries.employers_from(FEED_SOURCE)
    sources = company_queries.sources()
    unclassified = company_queries.unclassified()

    roles = open_roles()
    real = [r for r in roles if not r.evergreen]
    evergreen = len(roles) - len(real)
    feed_roles = [r for r in real if r.platform == FEED_SOURCE]
    ats_roles = [r for r in real if r.platform != FEED_SOURCE]
    ats_with_board = len({r.company_name for r in ats_roles})

    print(_rule("Coverage"))
    print(f"  from the sheet         {len(sheet_employers):4d} employers")
    print(f"    with a live board    {ats_with_board:4d}   ({len(ats_roles)} open roles)")
    print(
        f"    unresolved           {len(sheet_employers) - ats_with_board:4d}   see below"
    )
    if feed_employers:
        print(
            f"  from 80,000 Hours      {len(feed_employers):4d} organisations "
            f"({len(feed_roles)} open roles)"
        )
    print(
        f"  sources excluded       {len(sources):4d}   boards, agencies, investors, communities"
    )
    print(f"  unclassified           {len(unclassified):4d}   blank Type in the sheet")
    if evergreen:
        print(
            f"\n  {evergreen} talent-pool posting(s) set aside as not real vacancies"
        )


def _changes_section(run_id: int, previous: Optional[int]) -> None:
    if previous is None:
        print(_rule("Since last run"))
        print("  This is the first completed run -- it establishes the baseline,")
        print("  so there is nothing to compare against yet. Run again later.")
        return

    print(_rule(f"Since run {previous}"))
    counts = Counter(c["change_type"] for c in changes_for_run(run_id))
    if not counts:
        print("  No changes.")
        return
    for change_type in ChangeType:
        n = counts.get(change_type.value, 0)
        print(f"  {change_type.value:9} {n:4d}")

    for change_type, heading in (
        (ChangeType.APPEARED, "New roles"),
        (ChangeType.REOPENED, "Reopened"),
        (ChangeType.CLOSED, "Closed"),
    ):
        rows = changes_for_run(run_id, change_type)
        if not rows:
            continue
        print(f"\n  {heading} ({len(rows)})")
        by_company: Dict[str, List[dict]] = defaultdict(list)
        for row in rows:
            by_company[row["company_name"]].append(row)
        for company, items in sorted(by_company.items()):
            print(f"    {company}")
            for item in items[:10]:
                print(f"      - {item['title'][:72]}")
            if len(items) > 10:
                print(f"      ... and {len(items) - 10} more")

    changed = changes_for_run(run_id, ChangeType.CHANGED)
    if changed:
        print(f"\n  Edited ({len(changed)})")
        for item in changed[:15]:
            print(
                f"    {item['company_name']:12} {item['title'][:40]:42} "
                f"{item['field']}: {item['old_value']!r} -> {item['new_value']!r}"
            )
        if len(changed) > 15:
            print(f"    ... and {len(changed) - 15} more")


def _mix_section() -> None:
    """Per-employer department mix, first-party ATS roles only.

    Feed roles are excluded here and shown separately: their labels are
    multi-label skill tags, not a department partition, so putting the two under
    one heading would compare quantities that are not comparable.
    """
    roles = [
        r for r in open_roles() if not r.evergreen and r.platform != FEED_SOURCE
    ]
    if not roles:
        return
    print(_rule("What they are hiring for (share of open roles)"))
    print("  Shares, not counts: company size drives posting volume, so counts")
    print("  would compare headcount rather than focus.")
    by_company: Dict[str, List] = defaultdict(list)
    for role in roles:
        by_company[role.company_name].append(role)

    for company, items in sorted(by_company.items(), key=lambda kv: -len(kv[1])):
        print(f"\n  {company}  ({len(items)} open)")
        counts = Counter(r.department or "(unspecified)" for r in items)
        for name, n in counts.most_common(8):
            share = n / len(items)
            print(f"    {name[:34]:36} {share*100:5.1f}%  {_bar(share)}  {n:4d}")
        if len(counts) > 8:
            print(f"    ... and {len(counts) - 8} more department(s)")


def _feed_section() -> None:
    """80,000 Hours roles, grouped by their own skill tags."""
    roles = [
        r for r in open_roles() if not r.evergreen and r.platform == FEED_SOURCE
    ]
    if not roles:
        return
    orgs = {r.company_name for r in roles}
    print(_rule(f"80,000 Hours feed ({len(roles)} roles, {len(orgs)} organisations)"))
    print("  Roles carry MULTIPLE skill tags, so these shares do not sum to 100%")
    print("  and are not a partition -- unlike the department mix above.")
    print("  80k curates by cause area, so this reflects its editorial focus as")
    print("  much as the market's.")

    tag_counts = Counter(tag for r in roles for tag in r.tags)
    for name, n in tag_counts.most_common(12):
        share = n / len(roles)
        print(f"    {name[:34]:36} {share*100:5.1f}%  {_bar(share)}  {n:4d}")
    untagged = sum(1 for r in roles if not r.tags)
    if untagged:
        print(f"    ({untagged} role(s) carry no skill tag)")

    print("\n  Organisations posting most:")
    for org, n in Counter(r.company_name for r in roles).most_common(8):
        print(f"    {org[:40]:42} {n:4d}")


def _unresolved_section() -> None:
    from src.db.init import get_con

    rows = get_con().execute(
        "SELECT company_name, coalesce(reason, '-'), coalesce(platform, '-') "
        "FROM company_ats WHERE status <> 'resolved' ORDER BY company_name"
    ).fetchall()
    if not rows:
        return
    print(_rule(f"Employers Scout cannot see ({len(rows)})"))
    print("  Reported as a number, not hidden -- otherwise coverage looks better")
    print("  than it is. Feed-discovered organisations are not listed here: their")
    print("  roles arrive directly, so an absent board URL is not a gap for them.")
    for name, reason, platform in rows:
        detail = f"  [{platform}]" if platform != "-" else ""
        print(f"    {name:24} {reason}{detail}")


def cmd_report(_args) -> int:
    init_tables()
    run_id = latest_completed_run()
    if run_id is None:
        print("No completed runs yet. Run `scout snapshot` first.")
        return 1

    summary = run_summary(run_id) or {}
    previous = previous_completed_run(run_id)
    print(f"Scout report -- run {run_id} ({summary.get('finished_at')})")
    print(f"  database: {db_path()} (schema v{schema_version()})")
    if summary.get("failed"):
        print(
            f"  WARNING: {summary['failed']} board(s) failed this run; their roles "
            f"were left untouched rather than closed"
        )

    _coverage_section()
    _changes_section(run_id, previous)
    _mix_section()
    _feed_section()
    _unresolved_section()
    return 0


# --- all ----------------------------------------------------------------------


def cmd_run(args) -> int:
    code = cmd_sync(args)
    if code:
        return code
    code = cmd_snapshot(args)
    if code:
        return code
    print()
    return cmd_report(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scout", description="Company hiring intelligence")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("sync", help="sync the sheet and resolve employer boards")
    sub.add_parser("snapshot", help="fetch roles and record a snapshot")
    sub.add_parser("report", help="print the report for the latest run")
    sub.add_parser("run", help="sync, snapshot, then report")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "sync": cmd_sync,
        "snapshot": cmd_snapshot,
        "report": cmd_report,
        "run": cmd_run,
        None: cmd_run,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
