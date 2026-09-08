# src/main.py
"""Entry point. Run with `python -m src.main` (or `make run`)."""

from src.constants.tables import TABLE_COMPANY_RESEARCH, TABLE_PROCESSED_COMPANIES
from src.db.init import init_tables
from src.db.insert import sync_table


def sync_google_sheets_to_duckdb() -> None:
    for table_name in (TABLE_PROCESSED_COMPANIES, TABLE_COMPANY_RESEARCH):
        sync_table(table_name=table_name)


def main() -> None:
    init_tables()
    sync_google_sheets_to_duckdb()


if __name__ == "__main__":
    main()
