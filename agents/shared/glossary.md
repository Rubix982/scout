# Glossary

Append-only. All agents may add; prior entries are never edited.

- **ATS**: Applicant Tracking System — the platform hosting a company's job board (Greenhouse, Lever, Ashby, Workable, SmartRecruiters).
- **Board token**: the per-company identifier in an ATS API path, e.g. `affirm` in `boards-api.greenhouse.io/v1/boards/affirm/jobs`. Not derivable from company name; see [R-001].
- **Link seed**: recovering a board token by parsing a job-board URL already present in the source sheet's `Link` column. Highest-precision resolution method.
- **Candidate generation**: producing plausible board tokens from a company name and domain, then validating each against the live API. ~40% hit rate (R-001).
- **Role snapshot**: the set of open roles captured for a company in one run; diffing consecutive snapshots yields new/closed roles.
- **Stale token**: a board token that previously resolved and now 404s, meaning the company changed ATS. Must trigger re-resolution, not silent omission.
- **Greenhouse EU**: `boards-api.eu.greenhouse.io` — separate host and separate tenancy from the US board API. A token valid on one 404s on the other.
- **Role feed**: a source that returns roles directly, with no per-employer board resolution (80,000 Hours). Contrast with an ATS board, which must be resolved to a platform + token first.
- **First-party role**: a role read from the employer's own ATS board. A *source-fed* role comes via an aggregator and is second-hand.
- **Multi-label vs partition**: ATS `departments[]` gives one department per role (shares sum to 1); 80k `tags_skill` gives several (they do not). The two must not be presented under one heading.
- **Company source** (`companies.source`): which surface a company row came from — `sheet` or a feed id. Scopes the sheet delta sync so feed-discovered rows are not deleted as "absent from the sheet".
- **Resolution-eligible employer**: sheet-owned, or has a `Board URL`. Feed-discovered organisations are excluded, since their roles already arrive.
