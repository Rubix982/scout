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

**Status:** open
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

**Blockers:** E-011
**Artifacts:** `src/sources/ats/` (`base.py`, `greenhouse.py`, `lever.py`, `ashby.py`)
**Closed:** —

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

**Status:** open
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

**Blockers:** E-004
**Artifacts:** `src/db/roles.py`, `src/db/init.py`
**Closed:** —

---

### E-006 · `scout report` CLI

**Status:** open
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

**Blockers:** E-005
**Artifacts:** `src/cli.py`
**Closed:** —

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
