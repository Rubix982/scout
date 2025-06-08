import duckdb
from pathlib import Path
from src.db.init import init_tables

DB_PATH = Path.home() / ".scout" / "scout.db"

EXPECTED_TABLES = {
    "processed_companies",
    "company_contacts",
    "contact_profiles",
    "email_drafts",
    "replies_log",
    "api_errors_log",
    "send_log",
}


init_tables()  # Ensure tables are initialized before tests


def test_db_file_exists():
    assert DB_PATH.exists(), f"Database file not found at {DB_PATH}"


def test_tables_exist():
    con: duckdb.DuckDBPyConnection = duckdb.connect(str(DB_PATH))  # type: ignore
    result = con.execute("SHOW TABLES").fetchall()
    table_names = {row[0] for row in result}

    missing = EXPECTED_TABLES - table_names
    assert not missing, f"Missing tables: {missing}"
