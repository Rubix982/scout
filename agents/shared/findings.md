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

---

## [R-002] Finding: ATS-only resolution measures 19% — falsification criterion FAILED

_Date: 2026-09-08_

Ran token resolution across all 36 rows of the real sheet (326 probes, 6
platforms, content-based validation). Script: `agents/researcher/findings/sweep.py`,
raw output: `sweep_results.json`.

**Result: 7/36 resolved (19%).** `plan.md` lens 4 set the falsification
criterion at "fails if resolution lands under ~50% even with link-seeding."
**The test failed as specified.** Confidence: high — this is the full population,
not a sample.

| Company | Platform | Token | Roles |
| :-- | :-- | :-- | --: |
| wolt | greenhouse | `wolt` | 240 |
| affirm | greenhouse | `affirm` | 205 |
| OnHires/482 Solutions | ashby | `onhires` | 47 |
| fingerprint | greenhouse | `fingerprint` | 23 |
| Greenhouse | greenhouse | `greenhouse` | 18 |
| Checkly | ashby | `checkly` | 4 |
| Swissborg | lever | `swissborg` | 3 |

540 roles total. By method: **generated 7, link_seed 0.**

### Link-seeding contributed nothing — prior claim retracted

R-001 asserted the `Link` column would recover what candidate generation
misses. Measured: **zero.** Of 25 rows with links, only 3 contain a board
token, and all 3 fail — `strapi`'s Lever board is dead, `fingerprint`'s URL
carries a `gh_jid` marker but no token (and it resolved by generation anyway),
and `cherryventures` on Greenhouse EU returns no open roles. Most links point
at individual postings, aggregators, or homepages. The R-001 claim was
extrapolated from three hand-picked examples and did not survive the full
population.

### Root cause is twofold, and neither alone rescues the design

**(a) The denominator is wrong — my design error.** The sheet conflates three
kinds of entity, and only the first is ATS-resolvable *even in principle*:

- **Employers** (~20): track their roles. wolt, affirm, everli, medable, Clari, billie…
- **Job boards / talent marketplaces / agencies** (~13): honeypot, web3 careers,
  landing jobs, remotely works, vanhack, x-team, piper companies,
  Turn block Talent, workwithscout, join, skipp, buildspace.co, Greenhouse (an
  ATS vendor). These are *sources that yield companies*, not companies whose
  roles you track.
- **Investors / communities** (~3): foundrgroup, Sams social, joi.studio.

The sheet says this itself. `foundrgroup`'s Comment reads *"They are VCs. Visit
their site to find companies"*; `Sams social`'s reads *"find companies from here
and apply separately"*. Measuring ATS coverage against ~16 non-employers is a
category error, and lens 3 (Completeness) should have caught it before the
sweep ran.

**(b) Coverage is genuinely limited too.** Platform detection across 18
plausible employers (`scratchpad/detect.py`):

| Detected ATS | Companies |
| :-- | :-- |
| jazzhr | everli |
| smartrecruiters / workday | medable |
| rippling | fabric |
| greenhouse | ada engage (**token is not `ada`/`adaengage` — missed by generation**) |
| **no ATS marker at all** | **13 of 18** — Tendermint, moralis, Clari, flydevs, skipp, strapi, billie, sideos, soar, amondo, joi.studio, e-farm, x-team |

So 13 of 18 employers run custom career pages with no ATS signature. Only
`ada engage` is an in-scope platform we simply failed to tokenize.

### Corrected estimate, and why it still does not clear the bar

Realistic ceiling: 7 today + ~1 (fix `ada`) + ~3 (add Rippling, JazzHR,
SmartRecruiters) ≈ **11/36 (31%)**, or ~**52% of the ~20 actual employers**.

Even on the corrected denominator this only just reaches the threshold, and
only after adding three platforms. **Automatic resolution cannot be the primary
mechanism.** That conclusion stands on the measurement, not on the metric
dispute — fixing the denominator alone would not have saved it.

### What this does not overturn

ATS remains the right *source* where it applies: authoritative, free,
structured, timestamped, 540 real roles retrieved. What fails is the assumption
that resolution can be automatic. Manual token entry for ~20 employers is a
one-time task of minutes and yields near-total coverage of what actually
matters — auto-resolution belongs as an assist for when the list grows, not as
the mechanism the design depends on.

---

## [R-003] Finding: 80,000 Hours has no API, but its job board has a rich public search index

_Date: 2026-09-10_

### The two cited URLs are dead ends

Both are catalog entries, not APIs. Confidence: high — both state it outright.

- `apis.io/providers/80-000-hours/` lists **0 APIs** and says 80,000 Hours "is a
  content and career-advice organization rather than an API producer; no public
  developer API is published."
- `github.com/api-evangelist/80-000-hours` is a third-party API Evangelist
  profile holding `apis.yml` / `provenance.yml` metadata. It states "This
  repository contains no software" and calls itself "a lead awaiting the
  enrichment pipeline." No OpenAPI spec, no endpoints.

### The board itself is a different story

`jobs.80000hours.org` is a Nuxt app backed by an **Algolia** index, with
search-only credentials in the page source (public by construction for
InstantSearch — not a leaked secret). Also present: `apiBase:
https://backend.eawork.org/api` (the eawork backend, unexplored).

```
app id   W6KM1UDIB3
key      d1d7f2c8696e7b36837d5ed337c4a319   (search-only, from page source)
indices  jobs_prod, companies_prod, tags_prod,
         jobs_prod_strict, jobs_prod_super_ranked,
         jobs_prod_closing_date, collections_prod
POST     https://W6KM1UDIB3-dsn.algolia.net/1/indexes/{index}/query
```

`robots.txt` is `User-agent: * / Disallow:` — nothing disallowed.

### Measured contents

| | |
| :-- | --: |
| `jobs_prod` | **937 jobs** |
| distinct companies in those jobs | **386** |
| `companies_prod` (curated/highlighted orgs only) | 54 |
| `tags_prod` | 1001 |
| jobs flagged `evergreen` by 80k | 30 |
| jobs flagged `repost` by 80k | 58 |

Per-job fields are richer than any ATS we read: `post_pk`/`objectID`, `title`,
`url_external`, `posted_at`, `created_at`, `updated_at`, `closes_at`, `salary`
(+`salary_limit`), `company_name`, `company_id`, `company_url`,
`company_career_page_url`, and tag arrays — `tags_area` ("AI safety & policy"),
`tags_skill`, `tags_country`, `tags_city`, `tags_role_type`,
`tags_exp_required`, `tags_degree_required`.

**`evergreen` and `repost` are authoritative flags.** E-006 currently infers
evergreen from title text; for these roles 80k states it. Their own data also
confirms the phenomenon is real and worth modelling (30 of 937).

### Zero overlap with the current sheet

386 companies in the index; 36 rows in the sheet; **overlap: none.** Every one is
a company Scout does not currently know about. Confidence: high (exact string
comparison, so near-misses on naming may exist, but no exact matches at all is
decisive enough).

### ATS resolution is still the bottleneck — the same wall as R-002

`company_career_page_url` parses to a recognisable ATS board for only
**26 of 386 companies (7%)**, of which **19 are on v1-supported platforms**
(ashby 9, greenhouse 7, lever 3). Non-v1: workday 4, jazzhr 2, recruitee 1.

So harvesting 80k for *companies to track via their own ATS* would add ~19
trackable employers — better than the current 5, but still governed by the same
7-31% resolution ceiling R-002 measured.

### The consequence that matters

**The roles are already in the index.** Ingesting 80k as a *role feed* needs no
board-token resolution at all: 937 roles arrive with title, company, dates,
tags, salary and URL. That sidesteps the single constraint that has capped this
project since R-002, and would take Scout from 477 roles / 5 companies to
~1400 roles / ~390 companies.

The cost is provenance: an aggregator-sourced role is second-hand. 80k curates,
so its set is a *filtered* view (heavily AI-safety / policy weighted), not the
neutral census an employer's own board gives. Duplicates become possible where a
company is tracked both ways. Neither is disqualifying, but both need modelling
rather than assuming.
