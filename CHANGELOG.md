# Changelog

## 2026-09-10 · Session 2

- [E-013] `scout compass AREA=x` — reading material for the global Compass heading-check, with a corpus-bias banner. Deliberately does not score alignment or keep history; pointer added to `~/.agent-memory/research/scout-role-corpus.md`
- [E-012] 80,000 Hours role feed live — 937 roles across 386 organisations, corpus 477 → 1,398. Migration 006 adds `companies.source`, `roles.tags`, `roles.is_evergreen`. Caught two correctness bugs (sheet sync would have deleted all discovered companies; feed orgs were being ATS-resolved) and one self-inflicted regression (tests hitting the live API, 77s → 6s)
- [D-001] README rewritten against the shipped system — 32KB → 12KB; outreach design archived to `docs/outreach-design-archive.md`; claims verified against the code
- [R-003] 80,000 Hours assessed — no API at either cited URL; the job board runs a public Algolia index (937 jobs, 386 companies, zero overlap with the sheet). Findings in `agents/shared/findings.md`
- [O-004] Sheet stays read-only, OAuth narrowed to one scope — ticket opened retroactively, rule-7 break recorded on the ticket

## 2026-09-08 · Session 1 (revival)

- [R-001] ATS endpoint feasibility measured — findings in `agents/shared/findings.md`, probe scripts in `agents/researcher/findings/`
- [E-006] Report live — **v1 deliverable met**. Coverage, changes-since-last-run, department mix as shares, and unresolved employers with reasons. Detected 5 real wolt closures on its first unattended run. Evergreen talent-pool postings flagged and set aside. **Phase 2 complete.**
- [E-005] Snapshots + run-over-run diffing live — 477 roles tracked; closed/reopened verified against real boards. A failed fetch closes nothing; identity keyed on ATS id (wolt lists "Grocery Associate" 14 times)
- [E-003] ATS adapters live — 477/477 roles normalised across Greenhouse, Lever and Ashby. `content=true` proved necessary for department coverage (44% → 100%); only Greenhouse reports `updated_at`, so E-005 must diff on content
- [E-011] Board resolution live — 5/13 employers resolved from user-supplied URLs, 477 roles visible; all 8 unresolved recorded with reasons. Platform scope for E-003 now settled by data: Greenhouse, Ashby, Lever
- [E-010] Entity taxonomy live — employers separated from sources; 13 employers, 13 sources, 10 unclassified. Migration 003 reshapes a populated table; converge test strengthened to column level
- [E-002] Single-sheet ingest against the live sheet — 36 companies, second run reports 0 changes; declarative `SheetTable` mapping, type-coercion fix, phantom-column stripping, gspread error unmasking. **Phase 1 complete.**
- [R-002] ATS resolution measured at 19% across all 36 rows — falsification criterion failed; link-seeding contributed 0
- [O-003] Design re-pass — employers vs sources as distinct entity kinds; opened E-010, E-011, T-006; re-scoped E-002/E-003/E-004
- [O-004] Sheet is input-only; Scout stays read-only, OAuth narrowed to a single `spreadsheets.readonly` scope
- [E-007] Dependency set rebuilt against Python 3.14 — `requirements.in` + locked `requirements.txt`; project was uninstallable (`duckdb==1.3.0`, no cp314 wheel)
- [E-001] Bootstrap repaired — `src/` import roots, import-time side effects eliminated, single DB connection, per-name logger cache; regression tests in `tests/test_bootstrap.py`
- [E-008] Config layer — `src/config.py`; `secrets/gcp/common.env` was validated but never loaded, so two settings silently never applied; regression test in `tests/test_config.py`
- [E-009] Versioned migrations — `src/db/migrations.py` + `schema_version`; test suite no longer mutates `~/.scout/scout.db`
- [O-002] Phase 1 redefined as infrastructure coherence; opened E-007, E-008, E-009; rescoped E-001, re-blocked E-002
- [O-001] Reframed Scout from cold-outreach engine to intelligence tracker; dropped LLM-as-search; opened E-001…E-006 and R-002; initialized `plan.md`, `threads.md`, `agents/` structure
