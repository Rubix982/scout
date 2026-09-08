# Decisions

Owned by: **Engineer**. Append-only.

## [O-001] Decision: Public ATS APIs replace LLM enrichment as the freshness mechanism

_Date: 2026-09-08_

**Decision:** Ground-truth role data comes from unauthenticated public ATS
job-board APIs (Greenhouse incl. EU, Lever, Ashby in v1). The existing
`src/clients/openai.py` enrichment pipeline is removed from the critical path.

**Rationale:** The pipeline asked `gpt-4o` "Any recent news about {company}?"
with no web access — the README's stated intent was to "simulate web-like search
by asking multi-turn prompts". That cannot work: the model answers from training
data behind a cutoff, so the freshness mechanism of a
stay-up-to-date system was a model's recollection, unverifiable and
indistinguishable from invention. ATS endpoints are authoritative, structured,
free, timestamped, and verified working (R-001).

**Alternatives rejected:** careers-page HTML scraping (JS-rendered, brittle,
per-site work — R-001 got 0/10 tokens by regex); LLM with real web search
(per-company cost, still unverifiable on specifics, deferred to v2 for soft
signals only); paid aggregator APIs (cost, ToS).

**Revisit if:** R-002 measures resolution under ~50% across the full company
list — at which point ATS-only is falsified and the design is re-passed, not
patched.

---

## [O-001] Decision: Outreach functionality deferred, not deleted

_Date: 2026-09-08_

**Decision:** `email_drafts`, `company_contacts`, `contact_profiles`,
`replies_log`, and `send_log` remain in `src/db/init.py`. No code is written
against them and no outreach ticket is open.

**Rationale:** The schema is already designed and costs nothing to keep. Deleting
it would discard real design work for no benefit, while building on it would
commit the project to the direction it just moved away from.

**Revisit if:** the tracker is working and outreach becomes the next useful brick
— and then only with real contact data, never LLM-guessed addresses.

---

## [E-007] Decision: Two-file dependency management (`requirements.in` → `requirements.txt`)

_Date: 2026-09-08_

**Decision:** `requirements.in` holds direct dependencies with lower bounds;
`requirements.txt` remains the fully-pinned resolved set used for installs,
regenerated via `pip install -r requirements.in && pip freeze > requirements.txt`
(exposed as `make lock`).

**Rationale:** The single flat `pip freeze` file made the project uninstallable.
37 exact pins with no direct/transitive distinction meant that when `duckdb==1.3.0`
turned out to have no cp314 wheel, the resolver had no freedom to move — and the
pinned transitives would have blocked it even if the direct pin were relaxed.
Recording *intent* (direct deps, lower bounds) separately from the *lock*
(everything, exact) is what makes the set re-resolvable on a new interpreter.
This keeps the global convention of pinning immediately, while making the pins
regenerable rather than archaeological.

**Result:** installs clean on Python 3.14 — duckdb 1.5.5, 24 pins down from 37.
Dropping `openai` removed `anyio`, `distro`, `httpx`, `httpcore`, `h11`, `jiter`,
`sniffio`, `tqdm`, and `pydantic` from the tree.

**Alternatives rejected:** `uv`/`poetry`/`pip-tools` (adds a toolchain
dependency for a single-developer project; the two-file pattern gets the same
property with stock pip); unpinned `requirements.txt` only (loses reproducibility).

**Revisit if:** the project gains contributors or CI, where a real lockfile with
hashes starts earning its keep.

---

## [O-003] Decision: Model employers and sources as distinct entity kinds

_Date: 2026-09-08_

**Decision:** Every row in the company list carries an `entity_type`. Only
`employer` rows get roles tracked. `board`, `agency`, `investor` and `community`
rows are *sources* — things that yield companies — and are explicitly excluded
from role tracking rather than attempted and silently failing.

Board tokens come primarily from a **user-maintained `Board URL` column** in the
sheet, parsed into platform + token. Automatic resolution is demoted from the
mechanism to an assist.

**Rationale:** R-002 measured 19% resolution against the falsification bar of
50%. Two causes: ~16 of 36 rows are not employers and cannot be resolved in
principle, and 13 of 18 actual employers run career pages with no ATS signature.
Fixing only the denominator would not have cleared the bar, so automatic
resolution cannot carry the design.

Manual entry inverts the economics. Pasting a board URL is one click from a
careers page, ~20 employers is minutes of one-time work, and it yields near-total
coverage of the rows that matter — where auto-resolution caps around 31%. It also
degrades honestly: a company with no board URL and no ATS is *recorded as
unresolvable with a reason*, not missing.

**Alternatives rejected:** auto-classification of entity type (unreliable, and
the cost of a wrong classification is a silently untracked company); defaulting
blank types to `employer` (recreates the exact silent-failure mode this fixes —
blank defaults to `unknown` and is surfaced as a count); a local mapping file
instead of sheet columns (splits the source of truth away from the list the user
actually maintains).

**Revisit if:** the list grows past a few hundred rows, where manual entry stops
being trivial and auto-resolution earns its keep again.

---

## [O-004] Decision: The sheet is input-only; Scout stays read-only

_Date: 2026-09-08_

**Decision:** Scout never writes to the Google Sheet. The sheet is a
user-maintained *input*: company name, comments, link, `Type`, `Board URL`.
Everything derived — tokens, roles, snapshots, diffs, resolution status — lives
in DuckDB. Credentials remain read-only, and the `drive.readonly` scope is
dropped as unused, leaving a single scope: `spreadsheets.readonly`.

**Rationale:** Tracing the write use cases found only one — a one-time pre-fill
of 36 cells in two new columns. That is a paste. Against it: the service-account
key would gain the power to modify or clear six months of hand-curated data, in a
public repository, permanently, to save a single manual action. Detection of a
leaked key happens *after* exposure.

Keeping the sheet input-only also keeps the data flow one-directional, which
means there is no reconciliation question ("the sheet and DuckDB disagree — which
wins?") to answer later.

**Alternatives rejected:** write access with append-only discipline (the
discipline is in our code, the permission is not — a bug or a leaked key ignores
it); write access confined to a separate tab (Sheets permissions are
per-spreadsheet, not per-tab, so the isolation is convention rather than
enforcement).

**Revisit if:** T-006 (harvesting sources to discover companies) is built.
Appending newly-found employers to the sheet is a genuine write use case, and the
scope should be widened then — earned by a feature that needs it, not in advance.

---

## [E-003] Decision: Greenhouse requests `content=true`; diffing cannot rely on `updated_at`

_Date: 2026-09-08_

**Decision (a):** the Greenhouse adapter passes `?content=true` by default, and
department is read from `departments[]` with custom `metadata` as a courtesy
fallback only.

**Rationale:** an earlier version of this module did the opposite — avoided
`content=true` to save ~15x payload (155KB → 2.4MB for 205 roles) and read
department from `metadata` as "External Department". Measured against the five
live boards, that gave **212/477 roles with a department (44%)**: affirm alone.
`metadata` entries are *tenant-defined custom fields*, not a schema — affirm
happens to define "External Department", wolt defines three different
department-ish keys, fingerprint defines none. `departments[]` is the real field
and is empty without `content=true`. With it, coverage is **477/477 (100%)**.

Since the v1 deliverable is role mix *by department* (E-006), the cheaper
request sacrificed the field the report is built on. ~5.4MB per run across three
boards is a fine price for a tool running locally on a schedule, and it also
answers thread T-005 for free: JD text arrives in the same response.

**Decision (b):** run-over-run change detection compares normalised fields, not
timestamps.

**Rationale:** read off live responses, **only Greenhouse reports a modification
time.** Lever exposes `createdAt` (epoch milliseconds) and Ashby `publishedAt`,
both creation-only. A design keyed on `updated_at` would silently never detect
changes on 2 of the 3 platforms. E-005 must therefore diff on content, using the
stable ATS `id` for identity — never the title, since reposts and title churn
would manufacture phantom "new role" events.

**Alternatives rejected:** heuristic matching of any `metadata` key containing
"department" (wolt has three, with different meanings, so the heuristic picks
arbitrarily); fetching `content=true` only for boards whose department is empty
(two requests per board to save bandwidth that does not matter locally).

**Revisit if:** payload size starts to matter — e.g. many more boards, or running
somewhere metered. `include_content=False` remains available per call.
