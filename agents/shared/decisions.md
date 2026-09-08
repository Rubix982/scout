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
