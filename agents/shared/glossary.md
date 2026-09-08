# Glossary

Append-only. All agents may add; prior entries are never edited.

- **ATS**: Applicant Tracking System — the platform hosting a company's job board (Greenhouse, Lever, Ashby, Workable, SmartRecruiters).
- **Board token**: the per-company identifier in an ATS API path, e.g. `affirm` in `boards-api.greenhouse.io/v1/boards/affirm/jobs`. Not derivable from company name; see [R-001].
- **Link seed**: recovering a board token by parsing a job-board URL already present in the source sheet's `Link` column. Highest-precision resolution method.
- **Candidate generation**: producing plausible board tokens from a company name and domain, then validating each against the live API. ~40% hit rate (R-001).
- **Role snapshot**: the set of open roles captured for a company in one run; diffing consecutive snapshots yields new/closed roles.
- **Stale token**: a board token that previously resolved and now 404s, meaning the company changed ATS. Must trigger re-resolution, not silent omission.
- **Greenhouse EU**: `boards-api.eu.greenhouse.io` — separate host and separate tenancy from the US board API. A token valid on one 404s on the other.
