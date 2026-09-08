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

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

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
