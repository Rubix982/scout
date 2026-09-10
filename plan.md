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

## Design re-pass — 2026-09-08 (R-002)

**Phase 2 is halted.** Not blocked on a ticket — halted on a failed
falsification test, per design rule 2 (the WHY gate is a stop condition) and
rule 6 (a wrong design decision is revisited, not buried).

**What broke:** lens 4 set the bar at "fails if resolution lands under ~50% even
with link-seeding." R-002 measured **7/36 = 19%** across the full sheet.
Link-seeding contributed **0**, retracting a claim R-001 had extrapolated from
three hand-picked examples.

**Why it broke — two independent causes, neither sufficient alone:**

1. *Mis-specified denominator (my error, lens 3).* ~16 of 36 rows are job
   boards, talent marketplaces, recruiting agencies, VCs or communities — not
   employers. No ATS can resolve them *in principle*. The sheet's own Comments
   column says so ("They are VCs. Visit their site to find companies"). Lens 3
   asked which sibling questions must hold for the answer to be believed, and
   "are these all even employers?" was not among them. It should have been.
2. *Genuine coverage limit.* Of 18 plausible employers, **13 run career pages
   with no ATS signature at all**. The 4 detectable ones sit mostly outside v1
   scope (JazzHR, Rippling, SmartRecruiters/Workday); only `ada engage`
   (Greenhouse) was an in-scope miss, and only because its token is neither
   `ada` nor `adaengage`.

Corrected ceiling: ~11/36 (31%), or ~52% of actual employers, and only after
adding three platforms. **Fixing the denominator alone would not have saved the
criterion** — this is not a metric dispute resolved in the design's favour.

**What survives:** ATS is still the right *source* where it applies —
authoritative, free, structured, timestamped, 540 real roles retrieved across 7
companies. What fails is the assumption that token resolution can be
*automatic*. Manual entry for ~20 employers is a one-time task of minutes.

**Structural finding, larger than the metric:** the sheet holds two different
kinds of thing. An *employer* yields roles to track. A *source* (job board, VC,
agency, community) yields **companies** to add. Scout currently models only the
first, and silently treats the second as a broken instance of it. Until the data
model distinguishes them, every coverage number measured is against the wrong
population.

**Resolution (chosen 2026-09-08):** model employers and sources as distinct
entity kinds; make user-supplied board URLs the primary resolution path. See
`agents/shared/decisions.md` → "[O-003]". Lenses re-passed:

- **3 Completeness** — now includes "is this row even an employer?" as a sibling
  question that must hold before any coverage number means anything.
- **4 Falsification** — new criterion: the design fails if, *with board URLs
  supplied*, fewer than ~80% of rows typed `employer` resolve. Manual entry
  should approach total coverage; if it does not, the source itself is wrong.
- **5 Method** — ATS retained as the source. Automatic resolution demoted from
  mechanism to assist. Platform support becomes demand-driven rather than
  speculative.
- **8 Scope** — v1 adds entity typing and manual board URLs; automatic
  resolution and source harvesting (T-006) move out.
- **9 Deliverable** — the report must state the excluded-source count and the
  unresolved-employer count with reasons, so coverage is never overstated.

## Design pass — 80,000 Hours as a role feed (2026-09-10, R-003)

Saif's reason for wanting this board is that its jobs are ones he actually wants.
That inverts my initial framing: I filed 80k's curation under *cost* ("a filtered
view, not a neutral census"). For a personal instrument the filter is the
feature — a set weighted toward work he cares about beats a complete one. Lens 1
re-passed accordingly.

**Chosen shape: role feed, not company discovery.** Both were live after R-003.
Company discovery would add ~19 trackable employers and remain governed by the
same 7–31% resolution ceiling R-002 measured. The role feed needs **no token
resolution at all** — the 937 roles are already in the index — taking Scout from
477 roles / 5 companies to ~1,400 / ~390. It sidesteps the single constraint that
has capped this project since R-002. Company discovery (T-006) stays deferred.

**Lens 5b, construct validity — the one real problem.** `tags_skill` covers
936/937 roles with 13 clean values (Research 397, Software engineering 236,
Operations 186, Policy 179, Information security 161), which is a *better*
grouping than ATS `departments[]`. The temptation is to map it onto `department`
and reuse the existing mix section. **That would be wrong:** 53% of roles carry
more than one skill tag. ATS department mix is a *partition* — one department per
role, shares sum to 1. Skill tags are *multi-label* — shares do not sum to 1 and
taking `tags_skill[0]` would be arbitrary for half the corpus.

Resolution: do not coerce tags into `department`. Store them, and label
source-fed groupings explicitly as non-partitioning. Comparing a partition to a
multi-label distribution under one heading is exactly the "measuring the wrong
thing precisely" failure.

**Lens 6, confounds.** 80k curates toward AI safety & policy (605 of 937 roles),
so its skill distribution describes *80k's editorial focus* as much as the
market's. Any cross-company comparison drawn from source-fed roles inherits that
bias. The report must attribute roles to their source so the bias is visible
rather than baked in.

**Lens 4, falsification.** Fails if source-fed roles cannot be distinguished from
first-party ATS roles in storage or in the report — at which point provenance is
lost and every aggregate silently mixes a census with a curated slice.

**Deferred, with reasons.** Cross-source deduplication: a company tracked both
via its own ATS and via 80k yields two rows with different identities. Overlap is
currently **zero of 386**, so this buys nothing today; documented, not built.
`backend.eawork.org/api` left unexplored — the Algolia index already answers the
question.

**Deliverable.** `make report` shows source-fed roles attributed to 80,000 Hours,
with their skill-tag distribution labelled as non-partitioning, without
disturbing the existing per-employer department mix.

## Current Phase

Phase 1 — **Infrastructure coherence** — **COMPLETE** (5/5 closed). No connector work begins until ingestion,
config, and storage cooperate. Rationale: the repo currently cannot even be
installed (E-007), nothing imports (E-001), one env file is loaded nowhere
(E-008), and schema changes silently do not apply (E-009). Writing ATS adapters
on top of that would mean debugging fetch logic and broken plumbing at the same
time, with no way to tell which layer failed.

Phase 2 — **Entity model + ingestion** — **COMPLETE**.
E-002 → E-010 → E-011 → E-003 → E-005 → E-006, all closed.

Phase 3 — Automatic resolution as a convenience (E-004), and source harvesting
(T-006). Both explicitly out of v1.

## Active Tickets

Execution order, not ID order.

| # | ID    | Agent      | Title                                        | Status | Phase |
| - | ----- | ---------- | -------------------------------------------- | ------ | ----- |
| 1 | E-007 | Engineer   | Rebuild dependency set (Python 3.14)         | closed | 1 |
| 2 | E-001 | Engineer   | Repair bootstrap: imports, DB connection     | closed | 1 |
| 3 | E-008 | Engineer   | Single config layer                          | closed | 1 |
| 4 | E-009 | Engineer   | Storage schema coherence + migrations        | closed | 1 |
| 5 | E-002 | Engineer   | Reconcile Sheets ingest with the real sheet  | closed | 1 |
| 6 | E-010 | Engineer   | Entity taxonomy: employers vs sources        | closed | 2 |
| 7 | E-011 | Engineer   | Board URL as primary resolution path         | closed | 2 |
| 8 | E-003 | Engineer   | ATS adapters: Greenhouse/EU, Lever, Ashby    | closed | 2 |
| 9 | E-005 | Engineer   | Role snapshots + run-over-run diffing        | closed | 2 |
| 10| E-006 | Engineer   | `scout report` CLI                           | closed | 2 |
| — | E-004 | Engineer   | Automatic resolution (assist, low priority)  | open   | 3 |
| — | R-002 | Researcher | Measure resolution rate over the full sheet  | closed | 2 |

## Blocked

| ID    | Blocked By                                        |
| ----- | ------------------------------------------------- |
| E-002 | — (unblocked; Sheets access now verified working) |
| —     | nothing blocked                                    |
| E-011 | E-010                                             |
| E-003 | E-011                                             |
| E-004 | E-011 (deferred to Phase 3 — assist only)         |
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
- R-002 · Full-sheet resolution measured at 19% — falsification criterion failed; Phase 2 halted pending re-pass
- O-003 · Design re-pass — employers vs sources; opened E-010, E-011, T-006
- O-004 · Sheet is input-only; Scout stays read-only, scopes narrowed to one
- E-002 · Single-sheet ingest live — 36 companies synced, second run reports 0 changes
- E-010 · Entity taxonomy live — 13 employers, 13 sources, 10 unclassified
- E-011 · Board resolution live — 5/13 employers resolved, 477 roles visible; 8 unresolved with reasons
- E-003 · Adapters live — 477/477 roles normalised across Greenhouse, Lever, Ashby
- E-005 · Snapshots + diffing live — 477 roles tracked, closed/reopened verified on real data
- E-006 · Report live — **v1 deliverable met**; caught 5 real wolt closures unprompted
- R-003 · 80,000 Hours assessed — no API at the cited URLs, but a public Algolia index with 937 jobs / 386 companies
- O-004 · Sheet stays read-only (ticket opened retroactively; rule-7 break recorded)
- D-001 · README rewritten against the shipped system — 32KB → 12KB, old design archived
- E-012 · 80,000 Hours role feed live — 937 roles / 386 organisations; corpus 477 → 1,398

## Next Orchestrator Action

Phase 1 is complete and the pipeline runs end-to-end against the live sheet.

**v1 is complete.** `make run` syncs the sheet, resolves boards, snapshots roles
and prints the report; `make report` re-prints without re-fetching.

Two things now compete for next:

1. **Coverage.** 5 of 13 employers have a board URL. Adding the rest (see
   `agents/shared/employers_needing_board_urls.md`) is Saif's input, not
   engineering work — `ada engage` is confirmed on Greenhouse and most valuable.
2. ~~**The README.**~~ Done — D-001. Rewritten against the shipped system;
   the outreach design is archived at `docs/outreach-design-archive.md`.
3. ~~**80,000 Hours as a source.**~~ Done — E-012. Shipped as a role feed;
   937 roles across 386 organisations, no token resolution needed.

Deferred by design: E-004 (automatic resolution, Phase 3), T-002 (refresh
cadence — now answerable as history accumulates), T-003, T-004, T-006.
