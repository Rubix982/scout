# Employers still needing a Board URL

_8 of 13 employers. E-011 reads column E; without a URL a row is
recorded `unresolved` with a reason rather than silently missing._

| Company | What R-002 detected |
| :-- | :-- |
| everli | JazzHR detected on careers page |
| moralis.io | no ATS marker found |
| medable | SmartRecruiters + Workday detected |
| Clari | no ATS marker found |
| fabric | Rippling detected |
| ada engage | Greenhouse detected -- token is NOT `ada`/`adaengage`, highest value |
| strapi | no ATS marker (left Lever) |
| billie | no ATS marker found |

Paste the board **root** URL, e.g. `https://boards.greenhouse.io/wolt`
or `https://jobs.ashbyhq.com/checkly` — not an individual posting.

Four rows with no ATS marker may have no public board at all; leave them
blank and they will be reported as `unresolved / no_ats_detected`.

_Note: the `fabric` cell has a trailing space in the sheet. Harmless —
`normalize()` strips it, so the stored key is `fabric`._
