# Threads

Open questions. A thread is a line of inquiry; a ticket is a unit of work.
See "Research Thread Tracking" in the global template.

### T-001 · Is "open postings" a usable proxy for company direction?

**Status:** parked
**Parent:** —
**Opened:** 2026-09-08
**Question:** Scout's value claim rests on postings revealing what a company is
building. But postings can be aspirational, backfill, stale, or reposted. What
would it take to distinguish "hiring signal" from "strategic direction" — or is
the honest answer that Scout only ever reports the former? Currently conceded in
plan.md lens 5, not investigated.
**Answer:** —

### T-002 · What refresh cadence makes diffs informative rather than noisy?

**Status:** open
**Parent:** T-001
**Opened:** 2026-09-08
**Question:** Daily runs will mostly show churn; monthly may miss short-lived
postings. The null outcome in plan.md lens 4 is "pipeline works but nothing
interesting changes week to week", which is a cadence problem masquerading as a
signal problem. Needs a few months of collected history to answer empirically —
cannot be answered by reasoning now.
**Answer:** —

### T-003 · How should company↔competitor sets be defined?

**Status:** open
**Parent:** —
**Opened:** 2026-09-08
**Question:** The competitor-intelligence use case ("what is my employer's
competitive set building") needs a notion of peer group. Manual tagging? Shared
investors? Overlapping role titles? Manual is trivial and probably correct for
v1, but the question is unexamined and no ticket covers it.
**Answer:** —

### T-004 · What does "aligned with me" reduce to, mechanically?

**Status:** open
**Parent:** —
**Opened:** 2026-09-08
**Question:** The original motivation was finding companies that align. v1
deliberately ships no scoring. When it does: title matching? JD keyword overlap
against `meta/you.json`? Embedding similarity? Each has a different failure mode,
and picking one before the role corpus exists would be designing against
imagined data.
**Answer:** —

### T-005 · Do ATS APIs expose full JD text, and is it worth storing?

**Status:** answered
**Parent:** T-004
**Opened:** 2026-09-08
**Question:** Greenhouse `?content=true` returns JD HTML. Storing it enables
T-004's keyword/embedding approaches and "what profiles are they hiring for" at
depth, but multiplies storage and needs HTML cleaning. E-003 retains `raw` JSON,
which partially hedges this.
**Answer:** Yes, and it arrives whether or not we want it. E-003 established
that Greenhouse only returns `departments[]` under `?content=true`, which also
carries the JD HTML — so the department data the report needs comes bundled with
the text. `roles.raw` retains the whole payload, so JD text is already stored
for every role at no extra request. Cost measured: ~5.4MB per run across three
boards. The remaining question is only whether to *parse* it (keyword/embedding
work), which belongs with T-004.

---

Threads
- answered→ T-005 · JD text — available, and already stored in roles.raw
- parked  → T-001 · postings as proxy for direction (conceded in design, not investigated)
- opened  → T-002 · refresh cadence vs. diff noise  ← now answerable, history is accumulating
            T-003 · defining competitor/peer sets
            T-004 · mechanics of "alignment"
            T-006 · harvesting sources for companies

### T-006 · Should sources be harvested for companies automatically?

**Status:** open
**Parent:** —
**Opened:** 2026-09-08
**Question:** E-010 establishes that ~16 rows are *sources* — job boards, VCs,
agencies, communities that yield companies. v1 records them and excludes them
from role tracking. The obvious next step is harvesting them: scrape
foundrgroup's portfolio page, or honeypot's company list, to discover employers
automatically. That is how the original motivation ("many companies went
unnoticed by me") actually gets solved — but it is a distinct capability with its
own per-source scraping burden, and it should not be smuggled into v1.
**Answer:** —
