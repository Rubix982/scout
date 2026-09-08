# Findings

Owned by: **Researcher**. Append-only.

## [R-001] Finding: Public ATS endpoints are viable but token resolution is the hard part

_Date: 2026-09-08_

Public ATS job-board APIs return authoritative, structured, timestamped role data
with no auth and no scraping. The endpoints work. The problem is not fetching the
data — it is knowing *which board token* belongs to a company. Tokens are not
derivable from company names, and are **not present in careers-page HTML**.

Probe scripts preserved in `agents/researcher/findings/` (`probe.py`,
`falsify.py`, `discover.py`, `resolve.py`) — all numbers below are measured, not
estimated.

### Verified working endpoints (no auth)

| Platform | Endpoint | Bad-token behaviour |
| :-- | :-- | :-- |
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{t}/jobs?content=true` | 404 — status is trustworthy |
| Greenhouse EU | `boards-api.eu.greenhouse.io/v1/boards/{t}/jobs` | 404 — separate host, distinct tenancy |
| Lever | `api.lever.co/v0/postings/{t}?mode=json` | 404 — trustworthy |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{t}` | 404 — trustworthy |
| Workable | `apply.workable.com/api/v1/widget/accounts/{t}?details=true` | 404 — trustworthy |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/{t}/postings` | **200 + `totalFound:0`** |

**Gotcha (high confidence):** SmartRecruiters returns HTTP 200 with an empty
result set for a company that does not exist. Adapters must validate on
*response content*, never on status code alone, or every company will appear to
"resolve" to SmartRecruiters with zero roles.

### Payload quality — Greenhouse/affirm, 205 roles

Per-role fields: `id`, `title`, `absolute_url`, `location.name`, `updated_at`,
`first_published`, `requisition_id`, `metadata[]` (carries External Department,
e.g. `Engineering`). `updated_at` + `first_published` are what make longitudinal
diffing possible — this is the mechanism for "what changed since last week".

Note: `departments[]` and `offices[]` are empty unless `?content=true` is passed;
department must otherwise be read out of `metadata[]`.

### Token resolution hit rate — 4/10 measured

Candidate generation (company name, domain stem, de-spaced, hyphenated) validated
against every platform endpoint:

| Company | Result |
| :-- | :-- |
| Affirm | greenhouse/`affirm` — 205 roles |
| Wolt | greenhouse/`wolt` — 240 roles |
| Fingerprint | greenhouse/`fingerprint` — 23 roles |
| Checkly | ashby/`checkly` — 4 roles |
| Cherry Ventures, Clari, Medable, Strapi, Everli, Honeypot | unresolved |

**~40% auto-resolution.** Tokens are case-insensitive on Greenhouse and Ashby.
Guessing plausible-looking tokens fails often: `fingerprintjs` 404s where
`fingerprint` succeeds; `checklyhq` (the actual domain stem) 404s where `checkly`
succeeds. Confidence: high (small n, but the failures are structural, not noise).

### Careers-page discovery: platform yes, token no

Checkly's careers page (202KB, HTTP 200) contains `ashby_embed`,
`data-slice-type="ashby_embed"`, `section-ashby-embed` — the *platform* is
plainly detectable. The markup is `<div id="ashby_embed"></div>`: the token is
injected at runtime by a JS bundle and appears **nowhere** in the static HTML.
Zero of 10 careers pages yielded a token by regex.

Implication: HTML detection narrows the search to one platform, which makes
candidate generation cheap and accurate, but cannot replace it. Confidence: high.

### The sheet's `Link` column is a token seed

The existing sheet already contains board URLs with tokens embedded:
`jobs.lever.co/strapi` (row 28), `boards.eu.greenhouse.io/cherryventures`
(row 25), `fingerprint.com/careers/jobs/apply/?gh_jid=` (row 37). Parsing that
column recovers tokens that candidate generation misses — including the EU
Greenhouse tenancy, which the US endpoint 404s on.

### The links are already stale — which is the point

`jobs.lever.co/strapi` is in the sheet, but `api.lever.co/v0/postings/strapi`
now 404s: Strapi has left Lever since the row was written. A hand-maintained
sheet decays silently. This is direct evidence for the project's premise, and it
also means link-seeded tokens must be re-validated, never trusted permanently.
Confidence: high.

### Coverage ceiling — honest bound

ATS APIs cover companies *on* those platforms. Companies on custom career pages,
BambooHR, JazzHR, or bespoke systems will not resolve. Expect roughly half of any
given list to need link-seeding or manual entry. ATS-only is authoritative where
it hits and silent where it does not — it is not a complete-coverage strategy,
and the design must show which companies are unresolved rather than quietly
omitting them.
