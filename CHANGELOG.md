# Changelog

## 2026-09-08 · Session 1 (revival)

- [R-001] ATS endpoint feasibility measured — findings in `agents/shared/findings.md`, probe scripts in `agents/researcher/findings/`
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
