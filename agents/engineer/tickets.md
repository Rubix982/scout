# Engineer Tickets

### E-001 · Repair bootstrap: imports, lazy config, single DB connection

**Status:** closed
**Type:** implement
**Priority:** high
**Created:** 2026-09-08
**Updated:** 2026-09-08
**Estimated:** 1h

**Description:**
Nothing in the repo currently executes. Three defects, all in the import path:

1. `src/main.py:2` is `from db.init import init_tables` while `:3` is
   `from src.db.insert import ...`. Mixed package roots — neither resolves under
   `make run` (`python3 src/main.py`). Normalize every internal import to the
   `src.*` root and run as a module (`python3 -m src.main`); update the Makefile
   `run` target to match.
2. `src/clients/gsuite.py:21-34` raises `FileNotFoundError` at **module import
   time** when `secrets/gcp/.env` or the service-account JSON is absent. This
   makes the module unimportable and takes the whole test suite down with it.
   Make importing the module side-effect free; the validation itself is
   redesigned in E-008, so here just stop it happening at import.
3. `src/db/init.py:14`, `src/db/insert.py:9`, and `src/clients/openai.py:11` each
   call `duckdb.connect()` at module scope against the same file. Replace with a
   single accessor (`src/db/init.py::get_con()`) returning a module-level
   singleton, created on first use rather than at import.

Also: `pytest.ini` sets `pythonpath = src`, but tests import `src.clients` /
`src.db`, which needs the project *root* on the path. Change to `pythonpath = .`.

Env-file naming and loading are E-008's scope, not this ticket's.

**Acceptance:**
- `python3 -c "import src.clients.gsuite"` succeeds with no secrets present.
- `make run` reaches `init_tables()` and creates `~/.scout/scout.db`.
- `make tests` collects and runs without import errors.

**Scope added during execution** (all the same defect class — import-time side
effects and module-scope globals — so handled here rather than split out):
- `src/db/init.py:8` called `SCOUT_DIR.mkdir()` at import, creating `~/.scout`
  in the developer's home merely by importing the module. Now lazy via `db_path()`.
- `src/log/config.py:14` called `DEFAULT_LOG_DIR.mkdir()` at import, creating
  `logs/` in the cwd. Now created on first logger construction.
- `src/log/__init__.py` logged a banner at import, which combined with the single
  `_logger` global in `config.py` meant the first logger built was always named
  `src.log` and **every** module's log output was attributed to it — the `name`
  argument was silently inert. Now cached per name.
- `src/clients/openai.py` moved to `agents/engineer/workspace/deferred/` — E-007
  dropped the `openai` dependency, leaving it unimportable inside `src/`.
- `tests/conftest.py` hand-inserted `../src` into `sys.path`; removed in favour of
  `pythonpath = .`. Credential-dependent tests now skip rather than fail.

**Result:** `make tests` → 7 passed, 3 skipped. `make run` creates all 8 tables
and then fails with a legible `Missing required env file: secrets/gcp/.env`
instead of an import crash. Regression tests in `tests/test_bootstrap.py` assert
each invariant, checking import purity in a fresh subprocess.

**Blockers:** E-007
**Artifacts:** `src/main.py`, `src/clients/gsuite.py`, `src/clients/__init__.py`,
`src/db/init.py`, `src/db/__init__.py`, `src/db/insert.py`, `src/log/config.py`,
`src/log/__init__.py`, `pytest.ini`, `Makefile`, `tests/conftest.py`,
`tests/test_bootstrap.py`, `tests/test_gsuite.py`,
`agents/engineer/workspace/deferred/`
**Closed:** 2026-09-08

---

### E-002 · Reconcile Sheets ingest with the actual sheet

**Status:** closed
**Type:** implement
**Priority:** high
**Created:** 2026-09-08
**Updated:** 2026-09-08
**Estimated:** 2h

**Description:**
The code and the real sheet disagree, so sync cannot succeed even with valid
credentials.

Code expects two worksheets — `"Company Research"` (`company`, `company_info`,
`contact_info`) and `"Processed Companies"` (18 columns) — keyed on a header
literal `Company` (`src/db/insert.py:71`).

The real sheet ("Companies hiring worldwide") has **one** tab, `Sheet1`, with
three columns: `Company Name`, `Comments`, `Link`.

Work:
- Introduce a `companies` source table matching the real sheet:
  `company_name` (PK), `comments`, `link`, `synced_at`.
- Make worksheet name and column→field mapping configuration, not literals, so a
  sheet reshape does not require a code change.
- `prettify_column_names()` (`src/common/utils.py`) reverses snake_case into
  Title Case to match sheet headers. That coupling is why a header rename breaks
  the insert silently. Replace with an explicit mapping dict.
- Fix the delta-comparison type bug: sheet booleans arrive as strings (`"TRUE"`)
  and are compared against DuckDB `BOOLEAN`, so
  `compute_delta_rows` (`src/db/insert.py:147`) flags every row as changed on
  every run. Normalize types before comparison.

Keep the existing delta-sync structure — fetch/diff/insert/delete is sound and
worth preserving.

**Updated 2026-09-08** — sheet access is now verified live: one worksheet
`Sheet1`, headers `Company Name | Comments | Link`, 36 data rows, no blanks, no
duplicates, 25 rows carrying a link. Two concrete findings for this ticket:

- `get_all_records()` returns a **phantom fourth key** `''` in every record
  (`{'Company Name': 'wolt', ..., '': ''}`) because the grid is 1001x27 and
  header inference picks up a trailing empty column. Strip it; do not let it
  reach the insert mapping.
- gspread masks API errors: `client.py:173` catches the informative `APIError`
  and re-raises a bare `PermissionError`, discarding the message. This cost a
  wrong diagnosis during setup (a disabled Sheets API read as "sheet not
  shared"). Wrap sheet access so the underlying reason surfaces —
  `SERVICE_DISABLED` vs. genuinely-not-shared vs. bad URL.

Per the R-002 re-pass, the ingest also reads two new user-maintained columns,
`Type` (E-010) and `Board URL` (E-011).

**Acceptance:** a dry-run sync against the real sheet reports 0 changes on a
second consecutive run.

**Result — acceptance met against the live sheet:**

```
run 1:  +36 new, ~0 changed, -0 removed, =0  unchanged
run 2:  +0  new, ~0 changed, -0 removed, =36 unchanged
```

Database holds 36 companies, 25 with links, 2 with comments — matching the sheet
exactly. Schema at version 2.

- Migration 002 creates `companies`. `entity_type`/`board_url` deliberately
  deferred to migration 003, since the sheet does not have those columns yet.
- `src/db/insert.py` rewritten declaratively: a `SheetTable` carries the
  header→column mapping, replacing five parallel `if table_name == ...` dispatch
  functions. `test_declarative_spec_works_for_a_different_table` proves one code
  path serves any table.
- `prettify_column_names()` deleted. It rebuilt sheet headers by title-casing db
  columns, coupling the schema to the sheet's exact capitalisation.
- Type-coercion bug fixed via `normalize()`. Sheet cells arrive as `"TRUE"`/`""`,
  DuckDB returns `True`/`None`; compared raw, every row looked changed on every
  run and the delta never converged.
- Phantom `''` key stripped at the client boundary.
- `src/clients/errors.py` unmasks gspread's discarded `APIError` via `__cause__`
  and distinguishes `SERVICE_DISABLED` from genuinely-not-shared from bad URL —
  the exact confusion that misdirected setup diagnosis.
- The two `xfail(strict=True)` markers were removed, as strict mode intended.

**Two defects found in my own test code while closing this:**
- `test_fresh_and_preexisting_databases_converge` asserted `== [1]`, pinning it
  to the migration count; it broke the instant migration 002 existed. Now
  asserts against `MIGRATIONS`.
- `test_config.py`'s `env_sandbox` cleanup called `config.load(force=True)`
  *before* monkeypatch restored the patched `ENV_FILES`, so it re-read the temp
  files with `override=True` and pushed `COMPANIES_SHEET_NAME="from_secrets"`
  back into `os.environ` — where it leaked into the live sheet test, which then
  asked the API for a worksheet by that name. Passed in isolation, failed in the
  suite. Fixed by clearing `_loaded` instead, plus a guard test verified to fail
  when the leak is reintroduced.

**Suite:** 47 passed (was 18).

**Blockers:** E-008, E-009
**Artifacts:** `src/db/insert.py`, `src/db/migrations.py`, `src/clients/gsuite.py`,
`src/clients/errors.py`, `src/clients/__init__.py`, `src/main.py`,
`src/constants/tables.py`, `src/common/utils.py`, `tests/test_sync.py`,
`tests/test_gsuite.py`, `tests/test_config.py`, `tests/test_duckdb.py`
**Closed:** 2026-09-08

---

### E-003 · ATS adapters: Greenhouse (+EU), Lever, Ashby

**Status:** closed
**Type:** implement
**Priority:** high
**Created:** 2026-09-08
**Updated:** 2026-09-08
**Estimated:** 3h

**Description:**
One adapter per platform behind a common interface, normalizing to a single role
record. Endpoints are verified live in R-001 — use those exact URL forms.

Interface: `fetch(token) -> list[Role]`, where `Role` normalizes
`external_id`, `title`, `location`, `department`, `url`, `first_published`,
`updated_at`, and `raw` (original JSON, retained for reprocessing).

Platform notes from R-001, all measured:
- Greenhouse US and EU are **separate hosts with separate tenancy**; a token
  valid on one 404s on the other. Both must be tried.
- Pass `?content=true` on Greenhouse or `departments[]`/`offices[]` come back
  empty; otherwise read department out of `metadata[]` (`External Department`).
- Lever returns a bare JSON **array**, not an object.
- Ashby returns `{"jobs": [...], "apiVersion": ...}`.
- **Validate on response content, never status code.** SmartRecruiters (v2, not
  in this ticket) returns `200 {"totalFound":0,"content":[]}` for companies that
  do not exist. Bake content-validation into the interface now so v2 platforms
  cannot introduce false positives later.

Set a descriptive User-Agent, a per-request timeout, and retry with backoff on
5xx/429. Do not parallelize beyond ~8 concurrent requests per host.

**Acceptance:** `fetch("affirm")` on the Greenhouse adapter returns ≥200
normalized roles; `fetch("swissborg")` on Lever and `fetch("checkly")` on Ashby
each return the counts recorded in R-001.

**Re-scoped 2026-09-08 (R-002 re-pass):** v1 stays Greenhouse (+EU), Lever and
Ashby — these cover all 7 companies R-002 resolved plus `ada engage`. Further
platforms are **demand-driven, not speculative**: build what the `Board URL`
column actually contains (E-011). R-002 found JazzHR, Rippling and
SmartRecruiters/Workday among the employers, but adding them blind buys ~4
companies and leaves the real modelling problem untouched.

**Result:** **477/477 roles normalised** across all five resolved boards —
greenhouse (wolt 242, affirm 205, fingerprint 23), ashby (checkly 4),
lever (swissborg 3).

Field shapes were read off live responses rather than documentation, and the
three platforms disagree more than the original design assumed:

| field | Greenhouse | Lever | Ashby |
| :-- | :-- | :-- | :-- |
| id | int | uuid str | uuid str |
| title | `title` | **`text`** | `title` |
| location | `location.name` | `categories.location` | `location` |
| department | `departments[]` | `categories.department` | `department` |
| created | `first_published` | `createdAt` (**epoch ms**) | `publishedAt` |
| **updated** | `updated_at` | **absent** | **absent** |

**Two findings that changed the design** (recorded in decisions.md → "[E-003]"):

1. *`content=true` is not optional.* The first implementation skipped it to save
   15x payload and read department from `metadata` "External Department".
   Measured: **212/477 roles (44%)** got a department — affirm only. `metadata`
   keys are tenant-defined, not schema; wolt has three department-ish keys and
   fingerprint none. With `content=true`: **477/477 (100%)**. The cheaper
   request sacrificed exactly the field E-006's deliverable is built on.
2. *Only Greenhouse reports a modification time.* Lever and Ashby are
   creation-only, so E-005 cannot diff on `updated_at` — it must compare
   normalised fields, keyed on the stable ATS `id`.

**Scope note:** built Greenhouse, Greenhouse EU, Lever and Ashby. EU shares the
Greenhouse normaliser but is a distinct platform in `identity`, so the two
tenancies can never collide.

**Suite:** 155 passed.

**Blockers:** E-011
**Artifacts:** `src/sources/ats/roles.py`, `src/sources/ats/__init__.py`,
`tests/test_ats_roles.py`, `agents/shared/decisions.md`
**Closed:** 2026-09-08

---

### E-004 · Automatic token resolution (assist only)

**Status:** open
**Type:** implement
**Priority:** low
**Created:** 2026-09-08
**Updated:** 2026-09-08
**Estimated:** 4h

**Description:**
The core problem of the project: given a company name, find its board token.
R-001 established tokens are **not** derivable from names and **not** present in
careers-page HTML (Checkly ships `<div id="ashby_embed"></div>` — the token is
injected by JS). Auto-resolution measured at 4/10 by candidate generation alone.

Resolve in this order, cheapest and most reliable first:

1. **Link seed.** Parse the sheet's `Link` column for embedded tokens —
   `jobs.lever.co/{t}`, `boards.eu.greenhouse.io/{t}`, `?gh_jid=`. This is the
   only route that recovers EU-Greenhouse tenants and is highest-precision.
2. **Platform detection.** Fetch `/careers`, `/jobs`, `/`; regex for platform
   markers (`ashby_embed`, `data-slice-type="ashby_embed"`, greenhouse/lever
   embed markers). Yields the platform, never the token — its value is narrowing
   candidate generation to one endpoint.
3. **Candidate generation + live validation.** Try company name lowercased and
   de-spaced, domain stem, hyphenated form. Tokens are case-insensitive on
   Greenhouse and Ashby. Accept a candidate only when it returns >0 roles.
4. **Manual override.** A column in the sheet or a local file that pins
   `platform` + `token` for a company, always winning over auto-resolution.

Persist to a `company_ats` table: `company_name` (PK), `platform`, `token`,
`resolution_method` (link_seed | detected | generated | manual), `resolved_at`,
`last_validated_at`, `last_role_count`, `status`
(resolved | unresolved | stale).

Caching is mandatory — resolution is many HTTP requests per company, and tokens
change rarely. But re-validate on every run: R-001 found `jobs.lever.co/strapi`
in the sheet while `api.lever.co/v0/postings/strapi` now 404s, i.e. Strapi left
Lever. On a previously-resolved token going 404, mark `stale` and re-resolve —
do not silently drop the company.

**Acceptance:** Affirm, Wolt, Fingerprint, Checkly all resolve automatically;
Cherry Ventures resolves via link seed to Greenhouse EU; unresolved companies are
recorded with `status='unresolved'`, never omitted.

**Re-scoped 2026-09-08 (R-002 re-pass):** demoted from the primary mechanism to
an assist, and from high to low priority. Measured 7/36 (19%) across the full
sheet, with link-seeding contributing **0** — retracting the claim in this
ticket's original description that link seeding "is the only route that recovers
EU-Greenhouse tenants and is highest-precision." It recovers nothing on the real
data. Manual entry (E-011) is now the primary path; this ticket is worth doing
only as a convenience for when the list grows, and must never outrank
`resolution_method = 'manual'`.

**Blockers:** E-011
**Artifacts:** `src/sources/ats/resolve.py`, `src/db/migrations.py`
**Closed:** —

---

### E-005 · Role snapshots + run-over-run diffing

**Status:** closed
**Type:** implement
**Priority:** high
**Created:** 2026-09-08
**Updated:** 2026-09-08
**Estimated:** 3h

**Description:**
The feature that makes Scout more than a job board: history.

Append-only `roles` table keyed on `(company_name, platform, external_id)` with
`first_seen`, `last_seen`, `closed_at`, plus the normalized fields and `raw`.
Each run upserts: unseen id → insert with `first_seen`; seen id → bump
`last_seen`; previously-seen id absent from this run → set `closed_at`.

Never key on title. R-001 notes reposts and title churn; stable ATS `external_id`
is the only reliable identity, and keying on title would manufacture phantom
"new role" events (confound named in plan.md lens 6).

Record each run in a `runs` table (`run_id`, `started_at`, `finished_at`,
`companies_attempted`, `companies_resolved`, `roles_seen`) so a diff is always
"between two runs" and a partial/failed run cannot corrupt the `closed_at` logic
— only mark roles closed for companies that were **successfully fetched** in that
run. A company that errored must not have its whole role set marked closed.

**Acceptance:** two consecutive runs with no upstream change produce an empty
diff; a simulated removed role gets `closed_at` set; a simulated company fetch
failure closes nothing.

**Result — verified on live data:**

```
run 1: 5/5 boards fetched, 477 roles, all `appeared` (flagged as baseline)
run 2: 5/5 boards fetched, 477 roles, zero changes
drop one Checkly role  -> closed   (477 -> 476 open)
restore it             -> reopened (476 -> 477 open), NOT appeared
```

Migration 005 adds `roles`, `runs` and `role_changes`. Roles are keyed on
`(platform, token, external_id)`.

**Why identity is the ATS id, proven by the data:** wolt lists
"Grocery Associate" **14 times** under distinct ids, "Sales Manager" 7 times,
"Retail Grocery Assistant" 5 times. Affirm lists
"Analyst II, Full Stack (Revenue Analytics)" twice. Title-keying would collapse
those and churn on every run.

**The guardrail:** `snapshot_company()` is only called for a company whose fetch
*succeeded*. `src/sources/ats/snapshot.py` calls the fetcher directly rather
than via `fetch_roles()`, because `fetch_roles` returns `[]` on failure and that
collapses the one distinction that matters — "fetched, zero roles" (close
everything) versus "fetch failed" (close nothing). Three tests cover it: HTTP
500 closes nothing, a transport error closes nothing, and a *successful* empty
board does close everything. One company failing does not block the others.

Change detection compares content, not timestamps, per E-003: only Greenhouse
reports `updated_at`, so a timestamp design would silently never detect changes
on Lever or Ashby. `role_changes` is the audit trail, since `roles` rows are
updated in place.

`department_mix()` returns **shares, not counts** — company size co-varies with
posting volume, so counts compare headcount rather than focus (plan.md lens 6).

**Bug found by a test:** `role_changes` had no `title` column, so
`_record_change` silently dropped it and `changes_for_run` failed on a binder
error. Migration 005 was uncommitted and local-only, so it was amended rather
than patched by a 006 minutes later; the local database was rebuilt, which cost
nothing since it holds only derived data.

**Layering fix:** see decisions.md → "[E-005] `Role` is a domain model". The
snapshot runner exposed an inversion where storage imported from sources.

**Suite:** 179 passed (was 155). The import-purity guard now covers all 20
modules.

**Blockers:** E-004
**Artifacts:** `src/db/roles.py`, `src/db/migrations.py`, `src/common/models.py`,
`src/sources/ats/snapshot.py`, `src/sources/ats/roles.py`, `src/main.py`,
`tests/test_roles_snapshot.py`, `tests/test_bootstrap.py`
**Closed:** 2026-09-08

---

### E-006 · `scout report` CLI

**Status:** closed
**Type:** implement
**Priority:** medium
**Created:** 2026-09-08
**Updated:** 2026-09-08
**Estimated:** 2h

**Description:**
The v1 deliverable (plan.md lens 9). One command, one report:

- New roles since the previous run, grouped by company
- Roles closed since the previous run
- Companies that could not be resolved, with a count — reported as a
  first-class number, not hidden (pre-empts the cherry-picking objection)
- Role mix by department per company, as a **share** not a count (headcount
  confound, lens 6)

Plain text to stdout. No web UI, no LLM, no scoring in v1 — alignment scoring is
explicitly v2. Absolute-count trend claims stay out until several months of
history exist.

**Acceptance:** `scout report` runs against a populated DB and prints all four
sections, with unresolved companies visible.

**Result — the v1 deliverable, live.** `make report` prints four sections:
coverage, changes since the previous run, what each company is hiring for as
department **shares**, and the employers Scout cannot see with reasons.

**It caught real signal on its first unattended run.** Run 4 detected 5 wolt
roles closed since run 3 — genuine board changes, not simulated:

```
Closed (5)
  wolt
    - Operations Associate, Courier Onboarding
    - Partnership Manager
    - Senior Account Manager, Restaurant
    - Staff Software Engineer, iOS
    - Support Associate (English speaking)
```

The mix section answers the original question directly. affirm is ~42%
engineering across three eng departments (Consumer 14.6%, Financial Platforms
14.6%, Infrastructure 13.2%); wolt is operations-led (Order Fulfillment 21.5%,
merchant acquisition 11.2%) with engineering barely present. Those are different
companies to approach differently, which is the whole point.

**Evergreen postings.** Checkly's board leads with "Don't see the role you're
looking for? Join our Talent Community!" — a real board entry that is not a
vacancy. `is_evergreen()` flags these (1 of 477) and the report sets them aside
*and says so*, since the heuristic runs on free text. False-positive coverage
matters as much as true positives: "Talent Acquisition Partner", "Head of
Talent", "Community Manager" and "Application Security Engineer" are all
asserted **not** to be flagged.

**What the report deliberately does not say.** A test asserts the output
contains none of "trend", "growing", "increasing", "investing in" or "shifting
toward". With one run of history, any such claim would fail plan.md lens 7 —
the null hypothesis is that a company simply posts a lot of everything. Scoring
(T-004) is likewise out of v1.

CLI has `sync`, `snapshot`, `report` and `run` subcommands; `src/main.py` now
delegates so both module paths behave identically. `make sync/snapshot/report`
added.

**Suite:** 211 passed (was 179).

**Blockers:** E-005
**Artifacts:** `src/cli.py`, `src/main.py`, `src/common/models.py`,
`src/db/roles.py`, `Makefile`, `tests/test_cli_report.py`
**Closed:** 2026-09-08

---

### E-007 · Rebuild the dependency set against a current interpreter

**Status:** closed
**Type:** implement
**Priority:** high
**Created:** 2026-09-08
**Updated:** 2026-09-08
**Estimated:** 1h

**Description:**
The project is currently **uninstallable**. Measured on Python 3.14.0 in a fresh
`.venv`:

```
ERROR: No matching distribution found for duckdb==1.3.0
```

`duckdb==1.3.0` publishes no cp314 wheel, so pip falls back to the 11.6MB source
tarball, whose metadata self-reports `0.1.0.dev0` — the resolver rejects it for
inconsistent version and the whole install aborts. DuckDB is on 1.5.x. Every pin
in `requirements.txt` predates this interpreter by ~6 months.

Root cause is not the stale pin, it is the *shape* of the file: 37 flat pins with
no distinction between direct dependencies and transitives. A `pip freeze` dump
cannot be re-resolved on a new interpreter, because pinned transitives block the
resolver from picking versions that actually have wheels.

Work:
- Introduce `requirements.in` listing **direct** dependencies only, with lower
  bounds rather than exact pins.
- Regenerate `requirements.txt` as the fully-pinned resolved set (still the file
  used for installs, preserving the `pip freeze`-style workflow — see the
  decisions entry).
- Drop `openai` and its transitive-only deps (`anyio`, `distro`, `httpx`,
  `httpcore`, `h11`, `jiter`, `sniffio`, `tqdm`). Decision O-001 removed LLM
  enrichment from the critical path; carrying its dependency tree costs install
  time and CVE surface for code that no longer runs.
- Add an HTTP client for the ATS adapters (E-003). `requests` is already present
  transitively via `gspread` — depend on it explicitly rather than implicitly.
- Direct set should be roughly: `duckdb`, `gspread`, `google-auth`,
  `python-dotenv`, `requests`, `pytest`, `pytest-cov`.

Do not upgrade to a DuckDB `.dev` release; take the latest stable.

**Acceptance:**
- `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` succeeds
  from clean on Python 3.14.
- `.venv/bin/python -c "import duckdb, gspread, requests; print(duckdb.__version__)"`
  prints a 1.5.x version.
- `openai` is absent from the installed set.

**Blockers:** —
**Artifacts:** `requirements.in`, `requirements.txt`, `Makefile`,
`agents/shared/decisions.md` → "[E-007] Two-file dependency management"

**Result:** clean-room install verified on Python 3.14 — duckdb 1.5.5, 24 pins
(was 37). `openai` and its 9 transitive-only deps removed. `make lock` added.

**Closed:** 2026-09-08

---

### E-008 · Single config layer

**Status:** closed
**Type:** implement
**Priority:** high
**Created:** 2026-09-08
**Updated:** 2026-09-08
**Estimated:** 2h

**Description:**
Configuration is read ad-hoc from three places with no single owner, and one of
the env files is loaded nowhere at all.

Confirmed defect: `src/clients/gsuite.py:21-23` validates that
`secrets/gcp/common.env` **exists**, then `:26` calls
`load_dotenv(GCP_SECRETS_FILE)` only — `common.env` is never loaded. So
`COMPANY_RESEARCH_SHEET_NAME` and `PROCESSED_COMPANIES_SHEET_NAME`, which live in
that file, always fall through to their hardcoded defaults. The failure is
silent: validation passes, the values are simply ignored.

Related scatter:
- `os.getenv("SHEET_URL")` read at call time in two functions (`gsuite.py:53,61`)
- `os.getenv("LOG_LEVEL")`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT` read at import in
  `src/log/config.py:9-11`
- `global.env` exists at project root, is empty, and is loaded by nothing
- `secrets/gcp/.env` is the path the code reads, but `.gitignore:205` ignores
  `secrets/gcp/secrets.env` — the file the code actually wants is only ignored
  incidentally, by the bare `.env` rule on `.gitignore:132`

Work:
- One `src/config.py` that loads every env file in a defined precedence order
  (`common.env` → `.env` → real environment) and exposes typed, named accessors.
- Fail fast with a message naming the missing variable and the file it belongs
  in — never a bare `FileNotFoundError`, and never a silent default for a value
  that has no sensible default (e.g. `SHEET_URL`).
- Distinguish *required* from *defaulted* config explicitly.
- Settle the env-file naming in exactly one place and make sure that name is
  git-ignored on its own line, not by accident.
- Delete `global.env` or give it a documented purpose. Empty and unread is worse
  than absent.

**Acceptance:**
- Setting `COMPANY_RESEARCH_SHEET_NAME` in `common.env` demonstrably changes the
  worksheet the client opens (a regression test for the bug above).
- Importing any module with no config present raises nothing; requesting a
  missing required value raises a message naming the variable and its file.

**Result:** `src/config.py` owns all config. Env files load in documented
precedence (`common.env` → `.env` → process env) with `override=True`, since
python-dotenv defaults to `override=False`, which would have made `.env` unable
to override `common.env` — the reverse of the documented order.

Settings are declared as `Setting` records carrying the variable name, the file
it belongs in, and a default; absence of a default *is* the definition of
required. Missing required values raise `ConfigError` naming the variable and the
file, replacing a bare `FileNotFoundError`. Added `SCOUT_DB_PATH` so E-009 can
point tests away from the real database, and `config.describe()` for diagnostics
(never prints secret values).

**Why the bug survived 6 months:** `common.env`'s two values are byte-identical
to the hardcoded fallbacks, so never loading the file made no observable
difference. `tests/test_config.py` therefore asserts on a value that is
deliberately *not* the default — verified to fail against the reintroduced bug
(returns `Company Research` instead of the sentinel) and pass once fixed. A test
using the real values would have passed either way.

`global.env` deleted — empty, at project root, loaded by nothing.
`.gitignore` now lists `secrets/gcp/.env` explicitly (it was only ignored
incidentally by the bare `.env` rule) and drops the vestigial
`secrets/gcp/secrets.env` rule, which pointed at a filename the code never read.

**Blockers:** E-001
**Artifacts:** `src/config.py`, `src/clients/gsuite.py`, `src/log/config.py`,
`src/db/init.py`, `tests/test_config.py`, `.gitignore`, `global.env` (deleted)
**Closed:** 2026-09-08

---

### E-009 · Storage schema coherence + migrations

**Status:** closed
**Type:** implement
**Priority:** high
**Created:** 2026-09-08
**Updated:** 2026-09-08
**Estimated:** 2h

**Description:**
`src/db/init.py` is 100% `CREATE TABLE IF NOT EXISTS`. That is fine on a fresh
database and silently wrong on an existing one: any change to an existing table's
shape simply never applies, and the code then runs against a schema that does not
match its expectations. E-002, E-004, and E-005 all add or reshape tables, so
this has to be settled before any of them, not after.

Work:
- A `schema_version` table plus an ordered list of migrations, each applied once
  inside a transaction. Idempotent: re-running is a no-op.
- Move the existing eight `CREATE TABLE` statements (plus the `email_drafts_seq`
  sequence and three indexes) into migration 001 so the
  current schema is the baseline rather than an implicit starting point.
- Add the tracker tables as their own migrations (definitions belong to their
  owning tickets — this ticket provides the mechanism, not the schemas):
  `companies` (E-002), `company_ats` (E-004), `roles` + `runs` (E-005).
- Keep the deferred outreach tables in migration 001 untouched, per the
  decisions entry — they cost nothing and deleting them discards real design work.
- Fix the connection story alongside: after E-001 there is one connection
  accessor, so migrations run against it rather than opening a fourth handle.

Note `EXPECTED_TABLES` in `tests/test_duckdb.py` omits `company_research`, so the
existing test would pass against an incomplete schema. Also, that test calls
`init_tables()` at **import** time and writes to the developer's real
`~/.scout/scout.db`. Point tests at a temp database via the config layer (E-008)
so running the suite cannot mutate real data.

**Acceptance:**
- Running migrations twice in a row produces no error and no change.
- A fresh database and a migrated pre-existing database end at identical schemas.
- `make tests` does not create or modify `~/.scout/scout.db`.

**Result:** `src/db/migrations.py` holds an ordered `MIGRATIONS` tuple; each
applies once inside a transaction and is recorded in `schema_version`. Migration
001 captures the pre-existing schema verbatim (8 tables, 1 sequence, 3 indexes)
so legacy and fresh databases converge. `init_tables()` now delegates to
`apply_pending()` and returns what it applied. Tracker tables are left to their
owning tickets (002 → E-002, 003 → E-004, 004 → E-005).

Test isolation: a session-scoped autouse fixture in `conftest.py` sets
`SCOUT_DB_PATH` to a temp path before any test imports the storage layer.
Verified empirically — `~/.scout/scout.db` mtime and size are byte-identical
before and after a full run. Previously, merely *collecting* the suite mutated it,
because `test_duckdb.py` called `init_tables()` at import scope.

`EXPECTED_TABLES` now includes `company_research` (it was missing, so the old
test would have passed against an incomplete schema) and `schema_version`.
Added a rollback test asserting a failing migration leaves no partial schema.

**Suite:** 18 passed, 3 skipped.

**Blockers:** E-001, E-008
**Artifacts:** `src/db/migrations.py`, `src/db/init.py`, `src/db/__init__.py`,
`tests/test_duckdb.py`, `tests/conftest.py`
**Closed:** 2026-09-08

---

### E-010 · Entity taxonomy: separate employers from sources

**Status:** closed
**Type:** implement
**Priority:** high
**Created:** 2026-09-08
**Updated:** 2026-09-08
**Estimated:** 3h

**Description:**
Consequence of the R-002 design re-pass. The company list holds two different
kinds of thing and currently models only one:

- an **employer** yields *roles* to track
- a **source** (board / agency / investor / community) yields *companies* to add

Scout treats sources as employers and fails to resolve them, which is why the
19% figure was measured against the wrong population. ~16 of 36 rows are sources.

Work:
- Migration 002: `companies` table with `company_name` (PK), `entity_type`,
  `comments`, `link`, `board_url`, `synced_at`.
- `entity_type` ∈ {`employer`, `board`, `agency`, `investor`, `community`,
  `unknown`}. **Blank in the sheet maps to `unknown`, never to `employer`** —
  defaulting to employer would recreate the silent-failure mode this ticket
  exists to remove.
- Read the type from a new `Type` column in the sheet (user-maintained; see
  `agents/shared/entity_classification_proposal.md` for a pre-filled proposal
  covering all 36 rows).
- Role tracking selects `WHERE entity_type = 'employer'` only. Everything else
  is recorded and visibly excluded, with the exclusion reported as a count.
- Reject unknown `entity_type` values loudly at sync time rather than coercing
  them — a typo'd type must not silently become an untracked company.

Two rows the sweep actively got wrong, both fixed by this ticket: `Greenhouse`
resolved to the ATS vendor's own 18 roles when it was listed as a route to
`cherryventures`; `OnHires/482 Solutions` contributed 47 *client* roles that
would corrupt any role-mix trend. Both inflated the 19% upward — true employer
resolution is 5/19.

**Acceptance:**
- A sheet row typed `board` is stored and never attempted for role fetching.
- A row with a blank type is stored as `unknown` and appears in the excluded
  count, not in the employer set.
- An unrecognised type value fails the sync with a message naming the row.

**Result — live against the real sheet:**

```
run 1:  ~26 changed, =10 unchanged   (migration 003 applied to an EXISTING 36-row db)
run 2:  ~0  changed, =36 unchanged
  tracked as employers: 13
  excluded as sources:  13
  unclassified:         10  <- blank Type; not assumed to be employers
```

13 + 13 + 10 = 36. Migration 003 reshaping a populated table is precisely the
case `CREATE TABLE IF NOT EXISTS` would have silently skipped, which is why
E-009 came first.

- `src/common/entities.py` — `EntityType` with `is_source`. `parse()` maps blank
  to `unknown` and **raises** on an unrecognised value; a typo must not become
  `unknown` either, or the same silence returns by another route.
  `unknown` is deliberately *not* a source, so it stays visible in its own count
  rather than being absorbed into the excluded total.
- `SheetTable` gained a `validators` hook (db column → callable) applied inside
  `to_db_row`, so a bad value is rejected before it can reach storage. Validation
  runs during `compute_plan`, before `apply_plan`, so a rejected row leaves no
  partial write — asserted by `test_a_rejected_row_does_not_partially_write`.
- `src/db/companies.py` — `employers()` / `sources()` / `unclassified()`, with a
  test that the three buckets *partition* the list so no row can be silently
  dropped or double-counted.
- `main.py` states coverage explicitly. R-002's 19% was measured against a
  population that silently included 16 non-employers; the counts are now printed
  rather than implied.

**Test gap found and closed:** `test_fresh_and_preexisting_databases_converge`
compared table *names* only, so it would have passed even if migration 003's
`ALTER` never applied. Now compares `(table, column)` pairs — demonstrated that
with 003 skipped the table names stay identical while the column set differs by
exactly `('companies', 'entity_type')`.

**Suite:** 74 passed (was 47).

**Blockers:** E-002
**Artifacts:** `src/common/entities.py`, `src/db/migrations.py`,
`src/db/companies.py`, `src/db/insert.py`, `src/main.py`,
`tests/test_entities.py`, `tests/test_companies.py`, `tests/test_sync.py`,
`tests/test_duckdb.py`, `tests/test_gsuite.py`
**Closed:** 2026-09-08

---

### E-011 · Board URL as the primary resolution path

**Status:** closed
**Type:** implement
**Priority:** high
**Created:** 2026-09-08
**Updated:** 2026-09-08
**Estimated:** 3h

**Description:**
R-002 demoted automatic token resolution from the mechanism to an assist:
measured 19% overall, ~31% ceiling even after adding three platforms, and 13 of
18 employers have no ATS signature at all. Manual entry inverts the economics —
one click from a careers page, ~20 employers, minutes of one-time work.

Work:
- Read a `Board URL` column from the sheet and parse it into
  (`platform`, `token`). Reuse and extend the link patterns already validated in
  R-001/R-002 (`agents/researcher/findings/sweep.py`), including the Greenhouse
  EU host, which is a **separate tenancy** from the US one.
- Populate `company_ats` (migration 003) with
  `resolution_method = 'manual'`, which outranks every automatic method.
- Validate each parsed token against the live API on entry, content-based, and
  report the role count back so a typo is caught immediately rather than
  surfacing as "0 roles" weeks later.
- An employer with no `Board URL` and no automatic resolution is recorded with
  `status = 'unresolved'` **and a reason** (`no_ats_detected`,
  `platform_unsupported`, `token_not_found`). Never silently absent.
- Platform support is now demand-driven: once board URLs are entered we know
  exactly which platforms are needed. R-002 found JazzHR (everli), Rippling
  (fabric) and SmartRecruiters/Workday (medable) among the employers — do not
  build these speculatively, build what the entered URLs actually require.

**Acceptance:**
- Pasting `https://boards.greenhouse.io/wolt` resolves to
  greenhouse/`wolt` with a live role count.
- Pasting a malformed or dead board URL fails at entry with a message, not later.
- `ada engage` resolves once its board URL is supplied (R-002 confirmed
  Greenhouse but the token is neither `ada` nor `adaengage`).

**Result — live against the real sheet:**

```
ATS boards: 5/13 employers resolved
  wolt          greenhouse  wolt          242 roles
  affirm        greenhouse  affirm        205 roles
  fingerprint   greenhouse  fingerprint    23 roles
  Checkly       ashby       checkly         4 roles
  Swissborg     lever       swissborg       3 roles
                            total         477 roles

  unresolved (8) -- recorded with a reason, not omitted
```

All 13 employers have a `company_ats` row. Sync converges to 0 changes on the
second run.

**Observation worth keeping:** wolt returned **242** roles, where R-002 measured
240 about an hour earlier. The board drifted mid-session — first-hand evidence
for the premise that a hand-maintained sheet decays and that `updated_at`-based
diffing (E-005) is the point.

- `src/sources/ats/platforms.py` — endpoints, URL patterns and role counting,
  all verified in R-001/R-002. Greenhouse US and EU are modelled as **distinct
  platforms** because they are separate tenancies; a token valid on one 404s on
  the other.
- **Patterns recognise more platforms than adapters can fetch, deliberately.**
  `SUPPORTED_PLATFORMS` is a strict subset of `Platform`, which is what lets an
  employer be reported `platform_unsupported` ("we know what they use, we cannot
  read it yet") instead of the far less useful `token_not_found`.
- Validation is **content-based**: zero roles is a failure to resolve, not a
  successful empty board. A 200 alone proves nothing — SmartRecruiters answers
  200 with `totalFound: 0` for companies that do not exist.
- Six distinct `Reason` values, each with an explanation the user actually
  reads; a test asserts the two sets stay in step.
- `resolve_all_employers()` skips sources entirely — a test seeds a `board`-typed
  row with a valid Greenhouse URL and asserts it is never resolved, since a job
  board's postings are not its own roles.
- A board going dead flips `resolved` back to `unresolved`, so a stale row cannot
  persist (R-002 found strapi's Lever board dead within ~6 months).
- The fetcher is injected, so all 15 resolver tests run without network.

**Demand-driven platform scope now settled by data:** the resolved boards need
exactly Greenhouse, Ashby and Lever. Greenhouse EU is *not* needed for employers
— its only appearance (`cherryventures`) is on a row typed `board`. E-003 should
build those three and nothing more.

**Test-design fix:** the two `to_db_row` tests asserted exact literal dicts and
broke three times — once each for E-002, E-010 and E-011 — every time for a
reason unrelated to what they check. Rewritten to derive from
`COMPANIES.columns`, so adding a column no longer breaks them.

**Suite:** 125 passed (was 74).

**Blockers:** E-010
**Artifacts:** `src/sources/ats/platforms.py`, `src/sources/ats/resolve.py`,
`src/sources/ats/__init__.py`, `src/db/migrations.py`, `src/db/insert.py`,
`src/db/companies.py`, `src/main.py`, `tests/test_ats_platforms.py`,
`tests/test_ats_resolve.py`, `tests/test_sync.py`
**Closed:** 2026-09-08

---

### E-012 · 80,000 Hours role feed

**Status:** closed
**Type:** implement
**Priority:** high
**Created:** 2026-09-10
**Updated:** 2026-09-10
**Estimated:** 5h

**Description:**
Ingest the 80,000 Hours job board as a **role feed** — roles arrive directly, no
board-token resolution. See R-003 in `agents/shared/findings.md` for the measured
surface and `plan.md` → "Design pass — 80,000 Hours as a role feed".

Endpoint (public search-only credentials, from the board's page source):

```
POST https://W6KM1UDIB3-dsn.algolia.net/1/indexes/jobs_prod/query
headers  X-Algolia-Application-Id: W6KM1UDIB3
         X-Algolia-API-Key: d1d7f2c8696e7b36837d5ed337c4a319
body     {"params": "query=&hitsPerPage=1000&page=N"}
```

937 jobs, one page at `hitsPerPage=1000`; paginate on `nbPages` regardless.
`robots.txt` is fully permissive. Treat the key as public config, not a secret —
it belongs in code or config, not `secrets/`.

**Identity.** Reuse the existing `roles` primary key with
`platform="80000hours"`, `token=company_id`, `external_id=post_pk`. No change to
the identity scheme, and it keeps source-fed roles from ever colliding with
first-party ATS roles.

**Migration 006** — three additions:
- `companies.source TEXT DEFAULT 'sheet'`. **Required for correctness:**
  `compute_plan()` deletes any `companies` row absent from the incoming sheet, so
  a discovered company inserted without this would be silently deleted on the
  next `make sync`. Scope the sheet sync's delete to `source = 'sheet'`.
- `roles.tags TEXT` — JSON array of skill tags. Do **not** map these onto
  `department`; see the construct-validity note in the design pass.
- `roles.is_evergreen BOOLEAN` — nullable. NULL means "unknown, fall back to the
  title heuristic"; true/false means the source stated it. 80k flags 30 of 937
  `evergreen` and 58 `repost`, authoritatively.

**Field mapping** (read off live records):

| Role field | 80k field |
| :-- | :-- |
| `external_id` | `post_pk` |
| `title` | `title` |
| `location` | `card_locations` joined, else `tags_city` |
| `department` | **leave empty** — tags are not departments |
| `url` | `url_external` |
| `first_published` | `posted_at` (epoch seconds) |
| `updated_at` | `updated_at` (epoch seconds) |
| `tags` | `tags_skill` |
| `is_evergreen` | `evergreen` |

**Source-level closing.** The whole source is fetched in one request, so absence
is real information. After processing every company present in the response,
close roles for companies that previously had open `80000hours` roles and are
absent now — call the existing per-company snapshot with an empty list. The
"failed fetch closes nothing" guardrail still applies: if the Algolia request
fails, close nothing at all.

**Company rows.** Insert discovered companies with `entity_type='employer'`,
`source='80000hours'`, so the report's coverage counts stay coherent. They must
never be resolved against ATS boards — they have no `board_url` and their roles
already arrive.

**Report.** Source-fed roles appear attributed to 80,000 Hours, with the
skill-tag distribution labelled as non-partitioning ("roles carry multiple tags,
so these do not sum to 100%"). Do not disturb the existing per-employer
department mix.

**Acceptance:**
- A first run ingests ~937 roles across ~386 companies; a second identical run
  reports 0 changes.
- `make sync` after ingestion does **not** delete the discovered companies.
- A simulated Algolia failure closes nothing.
- A role removed from the feed is closed; restored, it reopens.
- 80k's `evergreen` flag overrides the title heuristic for its roles.
- The report distinguishes source-fed roles from first-party ATS roles.

**Result — live:**

```
run 7: 5/5 boards fetched, 1398 roles seen
  80,000 Hours feed: 937 roles across 386 organisations

from the sheet           13 employers
  with a live board       5   (460 open roles)
from 80,000 Hours       386 organisations (907 open roles)
```

937 roles, 386 organisations, **zero overlap** with the sheet. Second run
converges to 0 changes. Corpus roughly tripled — 477 → 1,398 roles — with no
token resolution involved.

The feed section reports what Saif actually wanted from this board:
Research 375, Software engineering 233, Operations 174, **Information security
160**; Anthropic 39 and OpenAI 27 posting most.

**Two correctness problems caught before they mattered:**

1. *The sheet sync would have deleted every discovered company.*
   `compute_plan()` deletes any `companies` row absent from the incoming sheet,
   so 386 rows would have vanished on the next `make sync`. Fixed with
   `companies.source` plus a `SheetTable.owns` clause scoping both the
   comparison and the delete. Two tests: discovered companies survive a sync,
   and the sync still deletes its *own* removed rows (an ownership guard that
   makes the sync inert is worse than the bug).
2. *Feed organisations were being run through ATS resolution* — 399 employers
   attempted, writing 386 `unresolved / no_board_url` rows that would have
   drowned the coverage report in false negatives. Resolution is now scoped to
   "sheet-owned **or** has a board URL", so a discovered company that later
   gains a `Board URL` becomes eligible rather than being permanently excluded.

**Regression I introduced and fixed:** `include_feed` briefly defaulted `True`,
and the test suite silently began hitting the live Algolia index — 937 real roles
into a temp database and **77s** of runtime. The default is now `False` and the
CLI opts in explicitly; reaching the network belongs at the edge, not in a
library default. A tripwire test replaces both real fetchers and asserts
`run_snapshot()` calls neither. Suite back to **6s**.

**Construct validity honoured, not worked around:** `tags_skill` covers 936/937
roles with 13 clean values — better than ATS departments — but 53% of roles carry
more than one, so it is multi-label where a department partitions. Tags went to
their own column and their own report section labelled non-partitioning, rather
than being coerced into `department` where the two would have looked comparable
and not been.

80k's `evergreen` flag now overrides the title heuristic for its roles (30 of
937, exactly matching their own count). Total set-aside rose 1 → 31.

**Deferred, documented:** cross-source deduplication. A company tracked both via
its own ATS and via the feed yields two rows with different identities; overlap
is currently 0 of 386, so it buys nothing today.

**Suite:** 236 passed (was 211).

**Blockers:** —
**Artifacts:** `src/sources/eighty_k/feed.py`, `src/sources/eighty_k/__init__.py`,
`src/db/migrations.py` (006), `src/db/insert.py`, `src/db/roles.py`,
`src/db/companies.py`, `src/sources/ats/resolve.py`, `src/sources/ats/snapshot.py`,
`src/common/models.py`, `src/cli.py`, `README.md`, `tests/test_eighty_k.py`
**Closed:** 2026-09-10

---

### E-013 · `scout compass` — supply reading material for the heading-check

**Status:** closed
**Type:** implement
**Priority:** medium
**Created:** 2026-09-10
**Updated:** 2026-09-10
**Estimated:** 2h

**Description:**
The global Compass prescribes a habit: *"every few weeks, read 5–10 job
descriptions in the target area and ask: which listed needs does my current work
produce evidence for?"* Scout already holds that reading material — Greenhouse
JDs run 6–13KB in `roles.raw.content`, and search across the corpus returns 443
roles mentioning security, 90 kubernetes, 39 observability.

**Scope is deliberately narrow.** The Compass says "a habit, not a system" and
warns that building a tracking system for it is itself the difficulty-trap. So
this command does the *mechanical* half only: find relevant roles, extract the
needs they state, print them. It must **not**:

- score alignment, or emit any percentage
- store heading-check history or trend anything over time
- recommend a "next brick"

The judgment — which needs the current work produces evidence for — requires
knowing that work and stays with Saif.

Work:
- `src/compass.py`: search open roles by term across title and stored JD text;
  extract stated requirements from the JD (strip HTML, keep bullet-like lines);
  return records for display.
- Sample **one role per company** rather than most-recent overall, so a
  prolific poster (wolt has 233 open roles) cannot crowd out breadth. Breadth is
  the point of a heading-check.
- `scout compass --area <term> [--limit N]`, default limit 8 (the Compass says
  5–10).
- **Print a corpus-composition banner every time.** 937 of 1,398 roles come from
  80,000 Hours, which curates for AI safety and policy, and only 5 companies are
  first-party. A heading-check read against that without the caveat would point
  at 80k's editorial priorities rather than the market. `DevSecOps` and `duckdb`
  currently return 0 roles, which reflects corpus composition, not demand — the
  banner must make that misreading hard.

**Acceptance:**
- `scout compass --area security` prints ≤8 roles from distinct companies with
  their stated requirements.
- A term with no matches says so plainly rather than printing an empty section.
- Output contains no score, percentage-alignment, or recommendation.
- The composition banner names the dominant source and its bias.

**Result:** `make compass AREA=security` prints up to 8 roles, one per
organisation, ranked by how much each *states* about the area, with requirements
lifted from the JD text and a corpus-composition banner first.

Live output leads with affirm's "Security Risk Management Specialist II"
(*"3+ years of experience in Information Security, Risk Management, Compliance"*,
*"familiarity with cloud environments and common cloud security concepts"*),
fingerprint's "Senior Engineering Manager, Security & IT", and OpenAI's
"Software Engineer, Infrastructure Security" — real stated needs, not summaries.

**Three iterations were needed to make the output honest:**

1. First pass padded results with legal boilerplate. *"you have read Affirm's
   Global Candidate Privacy Notice"* trips the "you have" requirement hint, so
   affirm's needs came back as privacy notices and pay grades. Added a
   boilerplate blocklist and stopped padding to `limit` — an honest "nothing
   stated" beats filler.
2. Second pass ranked by recency, so `--area security` returned thin 80k roles
   where the term appeared only in a company blurb. Added relevance scoring
   (title match, count of on-term requirement lines, tag match) so roles that
   *say* something about the area sort first.
3. `extract_needs()` silently degraded when handed raw HTML instead of plain
   text: `splitlines()` saw one long line, so a single boilerplate phrase
   anywhere in the markup discarded the whole description. Found by my own test
   making that mistake. Normalised inside the function rather than documenting
   the trap.

**Scope held deliberately narrow**, per the Compass's own warning that building a
tracking system for the heading-check is the difficulty-trap. A test asserts the
output contains no alignment score, percentage-fit, or "next brick"
recommendation, and that it says so explicitly. The judgment stays with Saif.

**Bias is surfaced, not buried.** The banner prints corpus composition every run
and adds an explicit caveat when a single source exceeds 40% — currently 67%
from 80,000 Hours. `DevSecOps` and `duckdb` return zero roles, and without the
caveat that reads as market signal when it is composition. A test covers the
caveat firing.

One role per organisation, because wolt alone has 233 open roles and breadth is
what a heading-check needs.

**Suite:** 255 passed (was 236).

**Blockers:** —
**Artifacts:** `src/compass.py`, `src/cli.py`, `Makefile`, `README.md`,
`tests/test_compass.py`, `~/.agent-memory/research/scout-role-corpus.md`
**Closed:** 2026-09-10
