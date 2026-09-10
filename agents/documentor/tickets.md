# Documentor Tickets

### D-001 · Rewrite README against the shipped system

**Status:** closed
**Type:** document
**Priority:** high
**Created:** 2026-09-10
**Updated:** 2026-09-10
**Estimated:** 2h

**Description:**
`README.md` is 32KB documenting Scout as a cold-outreach engine: eight steps
covering metadata enrichment, contact discovery, email draft generation, a review
interface, Gmail sending and reply logging. None of that exists, and decisions
O-001/O-003 retargeted the project to hiring intelligence.

It is now the most misleading artifact in the repo — a second engineer reading it
would build the wrong system, and it contradicts the GitHub description.

Rewrite to document **what runs**, not what was once intended:

- what Scout produces (real report output, not a description of one)
- quickstart: venv, credentials, the sheet contract, first run
- the employer/source entity model (E-010) — the central concept
- resolution via user-supplied board URLs (E-011) and its honest ceiling
- the schema and migration story
- commands
- what it deliberately does not do, and why
- repo conventions (`plan.md`, `threads.md`, `agents/`)

Constraints:
- No aspirational features. If it is deferred, say so and say where it is tracked.
- State coverage honestly (5 of 13 employers), since understating it is the one
  failure mode the whole R-002 re-pass exists to prevent.
- Preserve the outreach design's existence as history without implying it works.

**Acceptance:** a reader who has never seen the repo can install, configure and
run Scout from the README alone, and can state correctly what it does and does
not do.

**Result:** README rewritten, **32,123 -> 12,098 bytes**. Documents what runs:
sample report output, quickstart through to first run, the sheet contract as a
table, the employer/source model, resolution and its measured ceiling, the
schema, commands, and an explicit "what Scout deliberately does not do" section.

The old README is preserved at `docs/outreach-design-archive.md` with a header
stating it describes a system that was never built and pointing at O-001/O-003 —
kept as a design record, not deleted (consistent with O-001's treatment of the
outreach tables).

**Verified against the code, not from memory.** A check script asserts the README
names every `Reason` value, every entity type, every supported and recognised
platform, every `make` target, every table, and `SCOUT_DB_PATH`. No mismatches.
All eight internal links resolve.

Coverage is stated as 5 of 13 employers rather than rounded up, and the
"deliberately does not do" section names the deferred items with their thread
ids, so a reader cannot mistake absence for oversight.

**Blockers:** —
**Artifacts:** `README.md`, `docs/outreach-design-archive.md`
**Closed:** 2026-09-10
