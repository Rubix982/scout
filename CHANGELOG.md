# Changelog

## 2026-09-08 · Session 1 (revival)

- [R-001] ATS endpoint feasibility measured — findings in `agents/shared/findings.md`, probe scripts in `agents/researcher/findings/`
- [E-007] Dependency set rebuilt against Python 3.14 — `requirements.in` + locked `requirements.txt`; project was uninstallable (`duckdb==1.3.0`, no cp314 wheel)
- [E-001] Bootstrap repaired — `src/` import roots, import-time side effects eliminated, single DB connection, per-name logger cache; regression tests in `tests/test_bootstrap.py`
- [E-008] Config layer — `src/config.py`; `secrets/gcp/common.env` was validated but never loaded, so two settings silently never applied; regression test in `tests/test_config.py`
- [E-009] Versioned migrations — `src/db/migrations.py` + `schema_version`; test suite no longer mutates `~/.scout/scout.db`
- [O-002] Phase 1 redefined as infrastructure coherence; opened E-007, E-008, E-009; rescoped E-001, re-blocked E-002
- [O-001] Reframed Scout from cold-outreach engine to intelligence tracker; dropped LLM-as-search; opened E-001…E-006 and R-002; initialized `plan.md`, `threads.md`, `agents/` structure
