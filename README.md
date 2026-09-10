# Scout

Tracks what companies are actually hiring for.

You keep a list of companies in a Google Sheet. Scout resolves each one's job
board, pulls every open role into a local DuckDB, and diffs it run over run — so
new, closed and reopened roles surface on their own instead of you re-reading a
spreadsheet that quietly went stale.

It also ingests the [80,000 Hours job board](https://jobs.80000hours.org/) as a
curated feed — ~937 roles across ~386 organisations, weighted toward AI safety,
policy and biosecurity.

It also tells you what it *cannot* see, which matters more than it sounds.

---

## What it produces

```
Scout report -- run 4 (2026-09-08 15:54:45)
  database: ~/.scout/scout.db (schema v5)

Coverage
--------
  from the sheet           13 employers
    with a live board       5   (460 open roles)
    unresolved              8   see below
  from 80,000 Hours       386 organisations (907 open roles)
  sources excluded         13   boards, agencies, investors, communities
  unclassified             10   blank Type in the sheet

  31 talent-pool posting(s) set aside as not real vacancies

Since run 3
-----------
  appeared     0
  changed      0
  closed       5
  reopened     0

  Closed (5)
    wolt
      - Operations Associate, Courier Onboarding
      - Partnership Manager
      - Senior Account Manager, Restaurant
      - Staff Software Engineer, iOS
      - Support Associate (English speaking)

What they are hiring for (share of open roles)
----------------------------------------------
  affirm  (205 open)
    Consumer Engineering                  14.6%  ####....................    30
    Financial Platforms - Engineering     14.6%  ####....................    30
    Infrastructure Platform Eng           13.2%  ###.....................    27
    Checkout                               8.3%  ##......................    17

  wolt  (242 open)
    Order Fulfillment                     21.5%  #####...................    52
    Merchant acquisition SMB              11.2%  ###.....................    27
    Country Support                        7.4%  ##......................    18

80,000 Hours feed (907 roles, 367 organisations)
------------------------------------------------
  Roles carry MULTIPLE skill tags, so these shares do not sum to 100%
  and are not a partition -- unlike the department mix above.
    Research                              41.3%  ##########..............   375
    Software engineering                  25.7%  ######..................   233
    Operations                            19.2%  #####...................   174
    Information security                  17.6%  ####....................   160

  Organisations posting most:
    Anthropic                                    39
    OpenAI                                       27

Employers Scout cannot see (8)
------------------------------
    Clari                    no_board_url
    ada engage               no_board_url
    ...
```

That last section is deliberate. Affirm is ~42% engineering across three
engineering orgs; wolt is operations-led with engineering barely present. Those
are different companies to approach differently — and you can only trust that
comparison if you also know how much of the list is missing.

---

## Quickstart

Requires Python 3.11+ (developed on 3.14) and a Google Cloud project.

```bash
git clone git@github.com:Rubix982/scout.git
cd scout
make venv            # creates .venv and installs pinned deps
```

### 1. Google credentials

Scout reads one Google Sheet, read-only. Follow
[`docs/google_auth_setup.md`](docs/google_auth_setup.md), then:

```bash
# place the downloaded service-account JSON here (git-ignored)
cp ~/Downloads/your-key.json secrets/gcp/gcloud_service_account.json

# create secrets/gcp/.env (git-ignored)
echo 'SHEET_URL=https://docs.google.com/spreadsheets/d/<your-id>/edit' > secrets/gcp/.env
```

Then **share the sheet with the service account's `client_email`** as Viewer.
Missing this step produces a `SpreadsheetNotFound` that reads like a bad URL.

You must also enable the **Google Sheets API** on the project. Scout does not use
the Drive API, and its OAuth scope is a single read-only Sheets scope — it can
never modify your data.

### 2. The sheet

One worksheet (default `Sheet1`) with these columns:

| Column | Required | Meaning |
| :-- | :-- | :-- |
| `Company Name` | yes | Primary key. Anything else is ignored if this is blank. |
| `Comments` | no | Free text, carried through untouched. |
| `Link` | no | Whatever link you had. Not used for resolution. |
| `Type` | no | `employer` · `board` · `agency` · `investor` · `community`. Blank ⇒ `unknown`. |
| `Board URL` | no | The employer's job-board **root**, e.g. `https://boards.greenhouse.io/wolt`. |

`Type` is the important one. See [Employers vs sources](#employers-vs-sources).

### 3. Run

```bash
make run        # sync sheet -> resolve boards -> snapshot roles -> report
make report     # re-print the last report without re-fetching
```

---

## Commands

| | |
| :-- | :-- |
| `make run` | full pipeline: sync, resolve, snapshot, report |
| `make sync` | read the sheet, resolve employer boards |
| `make snapshot` | fetch roles, record a snapshot, diff against the previous run |
| `make report` | print the report for the latest completed run |
| `make compass AREA=security` | print roles in an area with their stated requirements |
| `make tests` | pytest with coverage |
| `make lock` | re-resolve `requirements.in` and re-pin `requirements.txt` |

Equivalent to `python -m src.cli <sync|snapshot|report|run>`.

---

## Employers vs sources

The central concept, and the thing that took the longest to get right.

A list of "companies I'm interested in" is usually two different kinds of thing:

- an **employer** yields *roles* — track its board
- a **source** yields *companies* — a job board, recruiting agency, VC portfolio,
  or community

Scout originally treated everything as an employer, which is why an early
measurement of board-resolution rate came out at 19%: roughly 16 of 36 rows were
sources that no ATS could ever resolve. Worse, two of the apparent "successes"
were wrong in a way that corrupts analysis — a recruiting agency contributed 47
of its *clients'* roles, and Greenhouse-the-vendor contributed its own 18.

So `Type` gates everything. Only `employer` rows are resolved and tracked.
Everything else is recorded and visibly excluded, with the exclusion reported as
a count.

A blank `Type` becomes `unknown`, never `employer`. That is on purpose: guessing
`employer` would put an untriaged row into the tracked set, where a failure to
resolve is indistinguishable from a genuine coverage gap. An *unrecognised*
value fails the sync loudly, naming the row — a typo must not silently become
`unknown` either.

---

## How resolution works

Scout needs a platform and a board token per employer, e.g.
`greenhouse` + `wolt`. It gets them by parsing the `Board URL` you supply.

**Manual entry is the primary path, not a fallback.** Automatic resolution was
measured at 7 of 36 rows (19%), with a ceiling around 31% even after adding three
more platforms — 13 of 18 employers run career pages with no ATS signature at
all, and board tokens are neither derivable from company names nor present in
careers-page HTML (pages ship an empty `<div>` and inject the token via
JavaScript). Pasting a board root is one click from a careers page.

Supported for fetching: **Greenhouse** (US and EU — separate tenancies, a token
valid on one 404s on the other), **Lever**, **Ashby**.

Recognised but not yet fetchable: Workable, SmartRecruiters, JazzHR, Rippling,
Workday, Teamtailor, Personio, Recruitee. Recognising more than we can read is
deliberate — it lets an employer be reported `platform_unsupported` ("we know
what they use, we can't read it yet") rather than the useless `token_not_found`.

Every employer gets a `company_ats` row whether or not it resolved, with a
reason: `no_board_url`, `unrecognised_url`, `no_token_in_url`,
`platform_unsupported`, `board_unreachable`, `board_empty`. Nothing is silently
absent.

Validation is **content-based, never status-code-based**: SmartRecruiters returns
HTTP 200 with `totalFound: 0` for companies that do not exist, so a 200 alone
proves nothing.

---

## Heading-checks

```bash
make compass AREA=security
```

Prints up to 8 roles — one per organisation, ranked by how much each actually
*states* about the area — with the requirements pulled from their job
descriptions, and the URL to read further.

This exists to serve a habit, not to replace it: fetch 5–10 relevant job
descriptions so the question *"which of these stated needs does my current work
produce evidence for?"* can be asked against real text. Scout does not answer
that question. It does not score alignment, keep heading-check history, or
suggest what to work on next — that judgment needs to know the work being
checked, which a corpus cannot see, and automating it would be the trap rather
than the tool.

Every run prints the corpus composition first, because absence is easy to
misread. With 67% of roles currently coming from a board curated for AI safety
and policy, a term returning nothing says something about the corpus, not about
demand.

## The 80,000 Hours feed

A second source, and a different shape. Where an ATS board must be *resolved*
per employer, this one arrives whole: 937 roles across 386 organisations from a
single request against the board's public Algolia index (search-only credentials,
published in the board's own page source; `robots.txt` is fully permissive).

That matters because it sidesteps the constraint everything else here runs into.
Board-token resolution tops out around 31%; the feed needs none, and roughly
triples the corpus.

Three things are modelled deliberately:

- **Provenance is kept.** Feed roles are stored under `platform="80000hours"`, so
  they can never collide with a first-party ATS role and the report can attribute
  them. 80k *curates* — 605 of 937 roles are tagged "AI safety & policy" — so its
  distribution reflects its editorial focus as much as the market's. Pooling it
  with first-party data would hide that.
- **Tags are not departments.** 80k labels roles with `tags_skill` (Research,
  Software engineering, Information security, …), which covers 100% of roles and
  is cleaner than ATS departments. But 53% of roles carry *more than one* tag,
  while a department partitions. They get their own `tags` column and their own
  report section, labelled as non-partitioning, rather than being coerced into
  `department`.
- **Its evergreen flag is authoritative.** 80k marks talent-pool postings itself
  (30 of 937). Where a source states it, Scout believes it and does not guess
  from the title.

Discovered organisations are written with `source = '80000hours'`, which keeps
them out of two things they do not belong in: the sheet's delta sync, which
deletes rows absent from the sheet, and ATS resolution, since their roles already
arrive and an absent board URL is not a coverage gap for them.

A failed feed request closes nothing — the same guardrail the ATS path uses. A
*successful* fetch that omits a role does close it, because the whole feed is
fetched at once and absence is then real information.

## How diffing works

Roles are keyed on `(platform, token, external_id)` — the ATS's own id, **never
the title**. Real data forces this: wolt lists "Grocery Associate" 14 times under
distinct ids, "Sales Manager" 7 times; affirm lists "Analyst II, Full Stack
(Revenue Analytics)" twice. Title-keying would collapse them and churn every run.
A rename is recorded as `changed`, not as one role closing and another appearing.

Change detection compares normalised **content**, not timestamps. Only Greenhouse
reports `updated_at`; Lever and Ashby expose creation time only, so a
timestamp-based design would silently never detect changes on two of three
platforms.

**A failed fetch closes nothing.** Roles are only closed for a company whose
fetch actually succeeded, so one network blip cannot mark an entire company's
roles as closed and report it to you as a hiring freeze. "Fetched, zero roles"
and "fetch failed" are kept strictly apart.

Evergreen postings — "Don't see the role you're looking for? Join our Talent
Community!" — are real board entries that are not vacancies. Scout flags them by
title heuristic, excludes them from counts, **and reports how many it set aside**,
since the heuristic runs on free text. "Talent Acquisition Partner" and
"Community Manager" are real jobs and are not flagged.

---

## Data

Everything lands in `~/.scout/scout.db` (DuckDB), outside the repo. Override with
`SCOUT_DB_PATH`.

| Table | |
| :-- | :-- |
| `companies` | name, comments, link, `entity_type`, `board_url`, `source` (`sheet` or a feed) |
| `company_ats` | resolved platform/token per employer, with status and reason |
| `roles` | one row per role, with `first_seen` / `last_seen` / `closed_at`, `tags`, and the raw payload |
| `role_changes` | append-only audit trail: appeared / changed / closed / reopened |
| `runs` | one row per snapshot, including how many boards failed |
| `schema_version` | applied migrations |

Schema changes go through ordered, transactional migrations in
`src/db/migrations.py`. Append a `Migration`; never edit one that has shipped.
The five outreach-era tables (`email_drafts`, `company_contacts`, …) remain from
the original design — nothing reads or writes them.

The database is rebuildable from the sheet in one `make run`, with one exception:
**accumulated run history cannot be re-fetched.** If you wipe it you lose the
diffs.

---

## What Scout deliberately does not do

- **No trend claims.** With little history, "they're investing in X" fails
  against the null hypothesis that a big company simply posts a lot of
  everything. The report states shares and deltas; it does not editorialise.
  A test asserts the output contains no trend language.
- **No alignment scoring.** Ranking roles against your profile needs the role
  corpus to exist first. Tracked as thread `T-004`.
- **No LLM enrichment.** The original design asked GPT-4o "any recent news about
  {company}?" with no web access, intending to "simulate web-like search." A
  model answering from training data cannot be the freshness mechanism for a
  system whose purpose is staying current. See decision `O-001`.
- **No writes to your sheet.** The sheet is input; everything derived lives in
  DuckDB. Keeps the data flow one-directional and the credential harmless.
- **No outreach.** No contact discovery, no email drafting, no sending. The
  original design for all of it is archived at
  [`docs/outreach-design-archive.md`](docs/outreach-design-archive.md) — kept as
  a record, not a roadmap.

---

## Repo conventions

| | |
| :-- | :-- |
| `plan.md` | objective, phase, ticket ledger, design re-passes |
| `threads.md` | open research questions (`T-` ids), tree-structured |
| `CHANGELOG.md` | one line per closed ticket |
| `agents/shared/findings.md` | measurements, with confidence levels |
| `agents/shared/decisions.md` | engineering decisions, with what would make us revisit |
| `agents/*/tickets.md` | tickets by role — `O-` orchestrator, `R-` researcher, `E-` engineer, `D-` documentor |

Findings and decisions are append-only. If you want to know *why* something is
shaped the way it is, those two files are the answer — including the cases where
a measurement falsified the design and it had to change.

Nothing here is committed to the database or the sheet; it is all plain markdown.

---

## Status

v1 works end to end, over two sources: **1,398 open roles** — 460 from 5
first-party ATS boards, 937 from the 80,000 Hours feed.

Sheet coverage is **5 of 13 employers** with a board URL. Raising that is data
entry, not engineering — add `Board URL` values to the sheet.

Deferred and tracked: automatic token resolution as an assist (`E-004`), refresh
cadence versus diff noise (`T-002`), competitor/peer set definition (`T-003`),
alignment mechanics (`T-004`), harvesting sources to discover companies
(`T-006`).
