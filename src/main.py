# src/main.py
from db.init import init_tables
from src.db.insert import sync_table
from src.constants.tables import TABLE_PROCESSED_COMPANIES, TABLE_COMPANY_RESEARCH


def sync_google_sheets_to_duckdb() -> None:
    [
        sync_table(table_name=table_name)
        for table_name in [TABLE_PROCESSED_COMPANIES, TABLE_COMPANY_RESEARCH]
    ]


if __name__ == "__main__":
    init_tables()
    sync_google_sheets_to_duckdb()
