# Project: Scout

_Last updated: 2026-09-08 by O-001_

## Objective

A private, queryable corpus of companies and the roles they are actually hiring
for — refreshed on a schedule, diffable over time — so that "who is building what,
and what profiles do they want" is a query rather than a memory.

Done, for v1: point Scout at a list of companies; it resolves their job boards,
pulls every open role, and tells you what changed since last run.

## Reframe (2026-09-08)

Scout was built as a **cold-outreach engine** (enrich → find contacts → draft
emails → send via Gmail → log replies). Six of the README's eight steps serve
sending email. That is not the system needed. Scout is now an **intelligence
tracker**: know the landscape, not email it.

- **Kept:** DuckDB store, Sheets ingest, delta-sync logic.
- **Deferred indefinitely:** email drafts, Gmail send, contact discovery,
  `prompt_intents.json`, review UI. Tables stay in place; nothing is deleted.
- **Replaced:** LLM-as-search enrichment (see the WHY gate below).

## Design pass (lenses, compressed — see Research Design Protocol)

**1. Significance.** Confirmed → a standing answer to "which companies are hiring
for profiles like mine, and what is my employer's competitive set building?"
Denied (ATS coverage too thin) → falls back to a link-checker over a manual sheet,
which is worth much less and should be admitted as such. Honest positioning: this
is a personal instrument, not a contribution to a field. It passes the
"is it a toy?" test because it produces a real, decaying-if-untended dataset —
but it should not be dressed up as research.

**2. Prior art.** LinkedIn, Otta, Simplify, hnhiring, and a dozen job aggregators
already index postings, and several OSS ATS-scraper libraries exist. Scout differs
in one sentence: it tracks *a list I curate*, keeps *history* so I can diff role-mix
over time, and ranks by *my* criteria rather than an aggregator's engagement
objective. No scoop risk — nobody is competing for this.

**3. Completeness.** For the headline claim to be believed, also needed: what
fraction of a curated list resolves at all (R-001: ~40% auto, more via link seed),
and whether unresolved companies are visibly flagged rather than silently dropped.

**4. Falsification.** The design fails if: token resolution lands under ~50% even
with link-seeding, OR diffs prove too noisy to read (reposts and title churn
swamping real signal). Null outcome: resolution works but nothing interesting
changes week to week, i.e. the refresh cadence is wrong, not the pipeline.

**5. Method & construct validity.** Chosen: public ATS JSON APIs. Deferred, with
reasons — HTML scraping of careers pages (brittle, JS-rendered, per-site work);
LLM-with-web-search (unverifiable specifics, per-company cost); paid aggregator
APIs (cost, ToS). Construct caveat: **open postings are a proxy for company
direction, not a measurement of it.** A posting can be aspirational, stale, or
backfill. Claims must stay at "hiring signal", never "strategy".

**6. Confounds & controls.** Company headcount co-varies with posting volume —
compare role *mix* (share by department) not absolute counts. Seasonal hiring
cycles co-vary with "new roles this week" — needs several months of history before
trend claims are allowed. Reposted roles inflate "new" — key on stable ATS role
`id`, not title.

**7. Baseline.** The dumbest explanation for "company X is investing in Y" is that
X is simply large and posts a lot of everything. Any signal must beat "share of
postings unchanged from last period".

**8. Scope & feasibility.** IN v1: Greenhouse (+EU), Lever, Ashby; token
resolution with cache; role snapshots with diffing; a CLI report. DEFERRED to v2:
Workable/SmartRecruiters, JD text analysis, alignment scoring, competitor
dashboards. Feasible: no auth, no rate-limit issues observed, ~10 companies
probed live at no cost.

**9. Deliverable.** One CLI report: *"Since last run: N new roles across M
companies; here are the ones matching your profile; here are K companies I still
cannot resolve."* Everything in v1 serves producing that.

**10. Adversary.** Anticipated attacks and pre-emptions: *"your coverage is
cherry-picked"* → unresolved companies are reported as a first-class number, not
hidden. *"200 OK means nothing on SmartRecruiters"* → content-based validation
(R-001). *"your tokens rot"* → re-validation on every run, resolution method
recorded per company. *"postings ≠ strategy"* → conceded explicitly in lens 5.

## Current Phase

Phase 1 — **Infrastructure coherence.** No connector work begins until ingestion,
config, and storage cooperate. Rationale: the repo currently cannot even be
installed (E-007), nothing imports (E-001), one env file is loaded nowhere
(E-008), and schema changes silently do not apply (E-009). Writing ATS adapters
on top of that would mean debugging fetch logic and broken plumbing at the same
time, with no way to tell which layer failed.

Phase 2 — ATS ingestion core (E-003 → E-006), unblocked only once Phase 1 closes.

## Active Tickets

Execution order, not ID order.

| # | ID    | Agent      | Title                                        | Status | Phase |
| - | ----- | ---------- | -------------------------------------------- | ------ | ----- |
| 1 | E-007 | Engineer   | Rebuild dependency set (Python 3.14)         | closed | 1 |
| 2 | E-001 | Engineer   | Repair bootstrap: imports, DB connection     | closed | 1 |
| 3 | E-008 | Engineer   | Single config layer                          | closed | 1 |
| 4 | E-009 | Engineer   | Storage schema coherence + migrations        | closed | 1 |
| 5 | E-002 | Engineer   | Reconcile Sheets ingest with the real sheet  | open   | 1 |
| 6 | E-003 | Engineer   | ATS adapters: Greenhouse/EU, Lever, Ashby    | open   | 2 |
| 7 | E-004 | Engineer   | Board-token resolution + cache               | open   | 2 |
| 8 | E-005 | Engineer   | Role snapshots + run-over-run diffing        | open   | 2 |
| 9 | E-006 | Engineer   | `scout report` CLI                           | open   | 2 |
| — | R-002 | Researcher | Measure resolution rate over the full sheet  | open   | 2 |

## Blocked

| ID    | Blocked By                                      |
| ----- | ----------------------------------------------- |
| E-002 | — (unblocked; live acceptance needs Sheets creds) |
| E-003 | E-002                                           |
| E-004 | E-003          |
| E-005 | E-004          |
| E-006 | E-005          |
| R-002 | E-004          |

## Completed This Session

- R-001 · ATS endpoint feasibility, measured — `agents/shared/findings.md`
- O-001 · Reframe from outreach engine to intelligence tracker; project structure initialized
- O-002 · Phase 1 restructured as infrastructure coherence; opened E-007, E-008, E-009
- E-007 · Dependency set rebuilt — installs clean on Python 3.14 (duckdb 1.5.5, 24 pins)
- E-001 · Bootstrap repaired — imports, import-time side effects, shared DB connection, logger attribution
- E-008 · Config layer — `src/config.py`; fixed `common.env` being validated but never loaded
- E-009 · Migrations — `schema_version` + transactional ordered migrations; tests isolated from the real DB

## Next Orchestrator Action

E-002 is the last Phase 1 ticket and is unblocked. Its unit-level acceptance can
be met with fixtures; its live acceptance ("a second consecutive sync reports 0
changes") needs Google Sheets credentials in `secrets/gcp/.env`, which are not
present in the working tree. Implement against fixtures, then close only once a
live run confirms it.

Hold all of Phase 2 until E-002 closes: an adapter that cannot be run against
real storage is an adapter that has not been tested.
