# src/db/migrations.py
"""Versioned, idempotent schema migrations.

`init.py` previously used only `CREATE TABLE IF NOT EXISTS`. That is correct on a
fresh database and silently wrong on an existing one: any change to an existing
table's *shape* never applies, and the code then runs against a schema that does
not match its expectations, with no error to say so.

Each migration applies exactly once, inside a transaction, and is recorded in
`schema_version`. Adding a table means appending a `Migration` -- never editing
one that has already shipped, since an applied migration will not re-run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

import duckdb

from src.log import get_logger

logger = get_logger("migrations")

SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: Tuple[str, ...]


# --- 001: baseline -----------------------------------------------------------
# The schema as it stood before migrations existed: eight tables, one sequence,
# three indexes. Captured verbatim so that a database created by the old
# `init_tables()` and a freshly-migrated one converge on the same shape.
#
# The outreach tables (company_contacts, contact_profiles, email_drafts,
# replies_log, send_log) are deferred by decision O-001, not deleted -- they cost
# nothing and deleting them would discard real design work.
_BASELINE = (
    """
    CREATE TABLE IF NOT EXISTS company_research (
      company TEXT PRIMARY KEY,
      company_info TEXT,
      contact_info TEXT,
      last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS processed_companies (
      company TEXT PRIMARY KEY,
      summary TEXT,
      product TEXT,
      tags TEXT,
      investors TEXT,
      ideal_roles TEXT,
      recent_news TEXT,
      tone_advice TEXT,
      alignment_reason TEXT,
      suggested_opener TEXT,
      funding_stage TEXT,
      technologies_used TEXT,
      website_url TEXT,
      industry TEXT,
      linkedin_company_url TEXT,
      linkedin_search_links TEXT,
      company_processed BOOLEAN DEFAULT FALSE,
      last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      email_generated BOOLEAN DEFAULT FALSE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS company_contacts (
      company TEXT,
      contact_name TEXT,
      contact_email TEXT PRIMARY KEY,
      contact_linkedin_url TEXT,
      title TEXT,
      note TEXT,
      added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_company_contacts ON company_contacts(company);",
    """
    CREATE TABLE IF NOT EXISTS contact_profiles (
      contact_email TEXT PRIMARY KEY,
      linkedin_headline TEXT,
      bio_summary TEXT,
      recent_posts TEXT,
      focus_areas TEXT,
      enriched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    "CREATE SEQUENCE IF NOT EXISTS email_drafts_seq START 1;",
    """
    CREATE TABLE IF NOT EXISTS email_drafts (
      id BIGINT PRIMARY KEY DEFAULT nextval('email_drafts_seq'),
      company TEXT,
      contact_name TEXT,
      contact_email TEXT,
      draft_version INTEGER,
      tone TEXT,
      draft_content TEXT,
      intent TEXT DEFAULT 'networking',
      status TEXT DEFAULT 'pending_review',
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_drafts_contact_version
    ON email_drafts(contact_email, draft_version);
    """,
    """
    CREATE TABLE IF NOT EXISTS replies_log (
      contact_email TEXT,
      company TEXT,
      reply_type TEXT,
      reply_text TEXT,
      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS api_errors_log (
      stage TEXT,
      company TEXT,
      contact_email TEXT,
      error_message TEXT,
      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS send_log (
      draft_id INTEGER,
      contact_email TEXT,
      company TEXT,
      sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      delivery_status TEXT
    );
    """,
)

# --- 002: companies (E-002) ---------------------------------------------------
# The real sheet: one worksheet, columns `Company Name | Comments | Link`.
# The legacy `company_research` / `processed_companies` tables in migration 001
# modelled two worksheets that were never built; they are left in place
# (decision O-001) but nothing syncs into them any more.
#
# `entity_type` and `board_url` are deliberately NOT here -- they arrive in
# migration 003 (E-010/E-011) once the sheet actually has those columns.
_COMPANIES = (
    """
    CREATE TABLE IF NOT EXISTS companies (
      company_name TEXT PRIMARY KEY,
      comments TEXT,
      link TEXT,
      synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
)

# --- 003: entity_type (E-010) -------------------------------------------------
# The first migration that reshapes an EXISTING table, which is exactly what
# `CREATE TABLE IF NOT EXISTS` could never do: on a database already holding the
# 36 synced companies, the old approach would silently skip this and leave the
# code reading a column that does not exist.
#
# Default is 'unknown', never 'employer' -- see src/common/entities.py::parse.
_ENTITY_TYPE = (
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS entity_type TEXT DEFAULT 'unknown';",
)

# --- 004: board_url + company_ats (E-011) -------------------------------------
# User-supplied board URLs are the PRIMARY resolution path, not a fallback:
# R-002 measured automatic resolution at 19% with a ~31% ceiling, and 13 of 18
# employers have no ATS signature at all.
#
# `status`/`reason` exist so an unresolved employer is recorded with a cause
# rather than being silently absent -- overstating coverage is the failure mode
# this whole re-pass exists to prevent.
_BOARD_URL_AND_ATS = (
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS board_url TEXT DEFAULT '';",
    """
    CREATE TABLE IF NOT EXISTS company_ats (
      company_name TEXT PRIMARY KEY,
      platform TEXT,
      token TEXT,
      resolution_method TEXT,
      status TEXT,
      reason TEXT,
      last_role_count INTEGER,
      resolved_at TIMESTAMP,
      last_validated_at TIMESTAMP
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_company_ats_status ON company_ats(status);",
)

# --- 005: roles + runs + role_changes (E-005) ---------------------------------
# `roles` is keyed on (platform, token, external_id) -- the stable ATS id, never
# the title. R-002 noted reposts and title churn; keying on title would
# manufacture phantom "new role" events.
#
# `runs` exists so a diff is always *between two runs*, and so a partial or
# failed run cannot corrupt `closed_at`: roles are only closed for companies
# that were successfully fetched in that run.
#
# `role_changes` is the audit trail. Because `roles` rows are updated in place,
# a field-level history is the only way to answer "what changed since last
# week" -- and E-003 established that two of three platforms report no
# `updated_at`, so change detection compares content rather than timestamps.
_ROLES_AND_RUNS = (
    "CREATE SEQUENCE IF NOT EXISTS runs_seq START 1;",
    """
    CREATE TABLE IF NOT EXISTS runs (
      run_id BIGINT PRIMARY KEY DEFAULT nextval('runs_seq'),
      started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      finished_at TIMESTAMP,
      companies_attempted INTEGER DEFAULT 0,
      companies_fetched INTEGER DEFAULT 0,
      companies_failed INTEGER DEFAULT 0,
      roles_seen INTEGER DEFAULT 0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS roles (
      platform TEXT,
      token TEXT,
      external_id TEXT,
      company_name TEXT,
      title TEXT,
      location TEXT,
      department TEXT,
      url TEXT,
      first_published TEXT,
      updated_at TEXT,
      raw TEXT,
      first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      closed_at TIMESTAMP,
      first_seen_run BIGINT,
      last_seen_run BIGINT,
      PRIMARY KEY (platform, token, external_id)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_roles_company ON roles(company_name);",
    "CREATE INDEX IF NOT EXISTS idx_roles_open ON roles(closed_at);",
    """
    CREATE TABLE IF NOT EXISTS role_changes (
      run_id BIGINT,
      platform TEXT,
      token TEXT,
      external_id TEXT,
      company_name TEXT,
      title TEXT,
      change_type TEXT,
      field TEXT,
      old_value TEXT,
      new_value TEXT,
      changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_role_changes_run ON role_changes(run_id);",
)

# --- 006: multi-source support (E-012) ----------------------------------------
# `companies.source` is a CORRECTNESS requirement, not bookkeeping. The sheet
# delta sync deletes any `companies` row absent from the incoming sheet, so a
# company discovered from a feed would be silently destroyed on the next
# `make sync`. The sync now scopes its delete to `source = 'sheet'`.
#
# `roles.tags` holds a source's own labels. They are deliberately NOT written to
# `department`: ATS departments partition (one per role, shares sum to 1) while
# skill tags are multi-label (53% of 80k roles carry more than one). Coercing
# them would make the two incomparable under one heading.
#
# `roles.is_evergreen` is nullable on purpose: NULL means "unknown, fall back to
# the title heuristic", true/false means the source stated it. 80,000 Hours
# flags 30 of 937 roles evergreen authoritatively.
_MULTI_SOURCE = (
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'sheet';",
    "ALTER TABLE roles ADD COLUMN IF NOT EXISTS tags TEXT;",
    "ALTER TABLE roles ADD COLUMN IF NOT EXISTS is_evergreen BOOLEAN;",
    "CREATE INDEX IF NOT EXISTS idx_companies_source ON companies(source);",
)

MIGRATIONS: Tuple[Migration, ...] = (
    Migration(version=1, name="baseline", statements=_BASELINE),
    Migration(version=2, name="companies", statements=_COMPANIES),
    Migration(version=3, name="entity_type", statements=_ENTITY_TYPE),
    Migration(version=4, name="board_url_and_ats", statements=_BOARD_URL_AND_ATS),
    Migration(version=5, name="roles_and_runs", statements=_ROLES_AND_RUNS),
    Migration(version=6, name="multi_source", statements=_MULTI_SOURCE),
)


def current_version(con: duckdb.DuckDBPyConnection) -> int:
    con.execute(SCHEMA_VERSION_TABLE)
    row = con.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()
    return int(row[0]) if row else 0


def pending(con: duckdb.DuckDBPyConnection) -> List[Migration]:
    version = current_version(con)
    return [m for m in sorted(MIGRATIONS, key=lambda m: m.version) if m.version > version]


def apply_pending(con: duckdb.DuckDBPyConnection) -> List[Migration]:
    """Apply every unapplied migration in order. Returns those applied."""
    applied: List[Migration] = []
    for migration in pending(con):
        con.execute("BEGIN TRANSACTION")
        try:
            for statement in migration.statements:
                con.execute(statement)
            con.execute(
                "INSERT INTO schema_version (version, name) VALUES (?, ?)",
                [migration.version, migration.name],
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            logger.exception(
                "[MIGRATE] %03d %s failed and was rolled back",
                migration.version,
                migration.name,
            )
            raise
        logger.info("[MIGRATE] applied %03d %s", migration.version, migration.name)
        applied.append(migration)
    if not applied:
        logger.info("[MIGRATE] schema up to date at version %d", current_version(con))
    return applied
