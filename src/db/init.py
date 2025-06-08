# init.py

import duckdb
from pathlib import Path

# Create the ~/.scout directory
SCOUT_DIR = Path.home() / ".scout"
SCOUT_DIR.mkdir(parents=True, exist_ok=True)

# Path to the DuckDB database file
DB_PATH = SCOUT_DIR / "scout.db"

# Connect to the DuckDB database
con: duckdb.DuckDBPyConnection = duckdb.connect(str(DB_PATH))  # type: ignore


def init_tables():
    con.execute(
        """
    CREATE TABLE IF NOT EXISTS company_research (
      company TEXT PRIMARY KEY,
      company_info TEXT,
      contact_info TEXT,
      last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    )

    con.execute(
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
    """
    )

    con.execute(
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
    """
    )

    con.execute(
        """
    CREATE INDEX IF NOT EXISTS idx_company_contacts
    ON company_contacts(company);
    """
    )

    con.execute(
        """
    CREATE TABLE IF NOT EXISTS contact_profiles (
      contact_email TEXT PRIMARY KEY,
      linkedin_headline TEXT,
      bio_summary TEXT,
      recent_posts TEXT,
      focus_areas TEXT,
      enriched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    )

    # Ensure sequence exists
    con.execute("CREATE SEQUENCE IF NOT EXISTS email_drafts_seq START 1;")

    # Use the sequence for the default ID
    con.execute(
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
        """
    )

    con.execute(
        """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_drafts_contact_version
    ON email_drafts(contact_email, draft_version);
    """
    )

    con.execute(
        """
    CREATE TABLE IF NOT EXISTS replies_log (
      contact_email TEXT,
      company TEXT,
      reply_type TEXT,
      reply_text TEXT,
      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    )

    con.execute(
        """
    CREATE TABLE IF NOT EXISTS api_errors_log (
      stage TEXT,
      company TEXT,
      contact_email TEXT,
      error_message TEXT,
      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    )

    con.execute(
        """
    CREATE TABLE IF NOT EXISTS send_log (
      draft_id INTEGER,
      contact_email TEXT,
      company TEXT,
      sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      delivery_status TEXT
    );
    """
    )

    print("✅ All DuckDB tables initialized in:", DB_PATH)


if __name__ == "__main__":
    init_tables()
