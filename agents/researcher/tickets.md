# Researcher Tickets

### R-001 · ATS endpoint feasibility

**Status:** closed
**Type:** research
**Priority:** high
**Created:** 2026-09-08
**Updated:** 2026-09-08

**Description:**
Establish whether public ATS job-board APIs can serve as the freshness mechanism
for Scout: which platforms expose unauthenticated structured role data, whether
board tokens are derivable or discoverable, and what coverage to expect over a
curated company list.

**Artifacts:**
- `agents/shared/findings.md` → "[R-001] Public ATS endpoints are viable but token resolution is the hard part"
- `agents/researcher/findings/probe.py` — multi-platform endpoint probe
- `agents/researcher/findings/falsify.py` — nonsense-token control (found the SmartRecruiters false positive)
- `agents/researcher/findings/discover.py` — careers-page token discovery (negative result)
- `agents/researcher/findings/resolve.py` — candidate-generation resolution, 4/10

**Closed:** 2026-09-08

---

### R-002 · Measure resolution rate over the full company list

**Status:** closed
**Type:** research
**Priority:** medium
**Created:** 2026-09-08
**Updated:** 2026-09-08
**Estimated:** 2h

**Description:**
R-001 measured token resolution on n=10, hand-picked. That is enough to justify
building E-003/E-004 but not enough to trust the ~40% figure. Once E-004 lands,
run resolution across every company in the sheet (~36 rows) and record:

- share resolved by each method (link_seed / detected / generated / manual)
- share unresolved, and *why* — no ATS in use, platform outside v1 scope
  (Workable, SmartRecruiters, BambooHR, custom), or company defunct
- whether the unresolved set is dominated by one platform, which would tell us
  what to add in v2

This is the evidence for the falsification criterion in plan.md lens 4: if
resolution lands under ~50% even with link-seeding, the ATS-only strategy fails
and the design must be re-passed rather than pushed forward.

Confidence must be stated on the resulting finding. Do not open v2 platform
tickets before this closes — otherwise we are guessing which platforms matter.

**Note on sequencing:** ran ahead of E-004 rather than after it. The ticket was
blocked on E-004 on the assumption that resolution needed the production
implementation, but R-001's probe scripts were enough to answer it — and the
answer gates E-003/E-004, so measuring first avoided building on a false premise.

**Result: 7/36 (19%). Falsification criterion FAILED** (`plan.md` lens 4 set the
bar at 50%). Link-seeding contributed **0**, retracting an R-001 claim. Root
cause is both a mis-specified denominator (~16 of 36 rows are job boards,
agencies or VCs, not employers) and genuine coverage limits (13 of 18 employers
run career pages with no ATS signature at all).

**Blockers:** E-004 (removed — ran with R-001 tooling instead)
**Artifacts:** `agents/shared/findings.md` → "[R-002] ATS-only resolution
measures 19%", `agents/researcher/findings/sweep.py`, `sweep_results.json`
**Closed:** 2026-09-08
