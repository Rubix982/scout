# Orchestrator Tickets

### O-001 · Reframe Scout from outreach engine to intelligence tracker

**Status:** closed
**Type:** coordinate
**Priority:** high
**Created:** 2026-09-08
**Updated:** 2026-09-08

**Description:**
Scout was abandoned ~6 months ago as a cold-outreach engine. On review, the built
system and the actual need had diverged: the README specs contact discovery, email
drafting, Gmail sending, and reply logging, while the need is knowing which
companies are hiring for which profiles, refreshed over time.

Additionally, the existing enrichment pipeline (`src/clients/openai.py`) issues
six `gpt-4o` chat completions per company asking questions like "Any recent news
about {company}?" with **no web access and no search tool** — the README states
the intent as "simulate web-like search by asking multi-turn prompts". A model
answering from training data behind a cutoff cannot be the freshness mechanism
for a system whose purpose is staying current; it produces stale or invented
funding rounds and news with no way to distinguish them. Step 4's request for
contact emails "if public or guessable" has the same defect and additionally
fabricates PII.

Decisions taken: retarget to intelligence tracking; adopt public ATS endpoints as
the ground-truth source; defer all outreach functionality without deleting its
tables; drop LLM-as-search entirely.

Opened R-001 (feasibility, since the whole plan rests on ATS being real), then
E-001…E-006 and R-002 once R-001 returned high-confidence results. Initialized
`plan.md`, `threads.md`, and the `agents/` structure.

**Artifacts:** `plan.md`, `threads.md`, `agents/shared/findings.md`,
`agents/shared/decisions.md`, `agents/engineer/tickets.md`,
`agents/researcher/tickets.md`, `CHANGELOG.md`

**Closed:** 2026-09-08

---

### O-002 · Restructure Phase 1 as infrastructure coherence

**Status:** closed
**Type:** coordinate
**Priority:** high
**Created:** 2026-09-08
**Updated:** 2026-09-08

**Description:**
E-001 and E-002 were originally scoped as two point fixes ahead of connector
work. Review found the problem is layer-wide rather than local: the project is
uninstallable on the current interpreter (`duckdb==1.3.0` has no cp314 wheel and
its sdist metadata is inconsistent), `secrets/gcp/common.env` is validated but
never loaded so two config values silently never apply, and `init.py` is
entirely `CREATE TABLE IF NOT EXISTS` so schema changes never reach an existing
database.

Building ATS adapters on that foundation would conflate fetch bugs with plumbing
bugs, with no way to attribute a failure to a layer. Phase 1 is therefore
redefined as infrastructure coherence — environment, config, storage, ingest —
and Phase 2 (connectors) is gated on it.

Opened E-007 (dependencies), E-008 (config layer), E-009 (migrations).
Rescoped E-001 to import/connection plumbing only, moving env validation to
E-008. Re-blocked E-002 behind E-008 and E-009, since the ingest contract depends
on both. Execution order is now E-007 → E-001 → E-008 → E-009 → E-002.

**Artifacts:** `plan.md`, `agents/engineer/tickets.md`

**Closed:** 2026-09-08
