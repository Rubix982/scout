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

MIGRATIONS: Tuple[Migration, ...] = (
    Migration(version=1, name="baseline", statements=_BASELINE),
    # Tracker tables are added by their owning tickets:
    #   002 companies    (E-002)
    #   003 company_ats  (E-004)
    #   004 roles + runs (E-005)
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
