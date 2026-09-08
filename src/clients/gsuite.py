# src/clients/gsuite.py
"""Google Sheets read client.

Importing this module has no side effects. All configuration goes through
`src.config`, which owns env-file loading and precedence (E-008).
"""

from __future__ import annotations

from typing import Dict, List, Union

import gspread
from google.oauth2.service_account import Credentials

from src import config

# Least privilege: read-only, and only Sheets. `drive.readonly` was requested but
# never used -- nothing here calls Drive (open_by_url resolves via the Sheets API
# alone), and the Drive API is not even enabled on the project. Scout never
# writes to the sheet; see decisions.md -> "[O-004] The sheet is input-only".
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

SheetRow = Dict[str, Union[int, float, str]]


def get_gsheet_client() -> gspread.Client:
    credentials: Credentials = Credentials.from_service_account_file(
        str(config.service_account_path()), scopes=SCOPES
    )
    return gspread.authorize(credentials)


def get_sheet_data(sheet_url: str, sheet_name: str) -> List[SheetRow]:
    client = get_gsheet_client()
    worksheet = client.open_by_url(sheet_url).worksheet(sheet_name)
    return worksheet.get_all_records()


def get_processed_companies() -> List[SheetRow]:
    return get_sheet_data(
        config.sheet_url(), config.get(config.PROCESSED_COMPANIES_SHEET_NAME)
    )


def get_company_research() -> List[SheetRow]:
    return get_sheet_data(
        config.sheet_url(), config.get(config.COMPANY_RESEARCH_SHEET_NAME)
    )
