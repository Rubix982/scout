# Proposed entity classification — 36 rows

_Prepared 2026-09-08 for E-010. **A proposal, not a fact** — Saif owns this list
and should correct it. Rows marked ⚠ are ones I am genuinely unsure about._

Paste the `Type` column into the sheet. Blank ⇒ `unknown`, which is reported as a
count rather than defaulted to `employer`.

| Company Name | Type | Basis |
| :-- | :-- | :-- |
| wolt | employer | resolved, greenhouse/`wolt`, 240 roles |
| everli | employer | jazzhr detected on careers page |
| affirm | employer | resolved, greenhouse/`affirm`, 205 roles |
| x-team | agency ⚠ | dev talent network — supplies people, not a hirer |
| Tendermint | employer ⚠ | likely defunct/merged; careers page 9KB, no ATS |
| Swissborg | employer | resolved, lever/`swissborg`, 3 roles |
| Turn block Talent | agency | name states it |
| Checkly | employer | resolved, ashby/`checkly`, 4 roles |
| moralis.io | employer | web3 infra; no ATS marker |
| medable | employer | smartrecruiters + workday detected |
| Clari | employer | revenue ops; no ATS marker |
| piper companies | agency | staffing firm |
| fabric | employer | rippling detected |
| foundrgroup | investor | **your comment:** "They are VCs. Visit their site to find companies" |
| vanhack | board | talent marketplace |
| buildspace.co | community | accelerator / cohort programme |
| flydevs | agency ⚠ | appears to be a dev shop |
| ada engage | employer | greenhouse detected — token is NOT `ada`/`adaengage`, needs the board URL |
| web3 careers | board | job board |
| OnHires/482 Solutions | agency | resolved ashby/`onhires` 47 roles — but those are *client* roles, not theirs |
| landing jobs | board | job board |
| skipp | agency ⚠ | marketing/design marketplace |
| join | board | join.com is a hiring platform |
| Greenhouse | board ⚠ | your link was `boards.eu.greenhouse.io/cherryventures` — you meant the ATS as a *source*. Auto-resolution wrongly matched Greenhouse's own 18 roles |
| remotely works | board | job board |
| honeypot | board | job board |
| strapi | employer | OSS CMS; left Lever, no ATS marker now |
| e farm | employer ⚠ | agri marketplace |
| billie | employer | fintech; no ATS marker |
| workwithscout | agency ⚠ | appears to be recruiting |
| sideos | employer ⚠ | small identity/SSI startup |
| soar | employer ⚠ | uncertain what this is |
| amondo | employer ⚠ | creator tech |
| joi.studio | agency ⚠ | studio |
| Sams social | community | **your comment:** "find companies from here and apply separately" |
| fingerprint | employer | resolved, greenhouse/`fingerprint`, 23 roles |

**Tally:** ~19 employer · ~7 board · ~7 agency · 1 investor · 2 community
(11 flagged uncertain)

Two rows the sweep got actively wrong, both fixed by classification:

- **Greenhouse** resolved to Greenhouse-the-vendor's own 18 roles. You listed it
  as a route to `cherryventures`. It is a source, not an employer.
- **OnHires/482 Solutions** contributed 47 roles that belong to its clients. As
  an agency its postings are other companies' jobs — counting them as its own
  role mix would corrupt any trend claim.

Both were inflating the 19% *upward*. True employer resolution is 5/19, not 7/36.
