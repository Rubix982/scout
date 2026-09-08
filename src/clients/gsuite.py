# src/clients/gsuite.py
"""Google Sheets read client.

Importing this module has no side effects. All configuration goes through
`src.config` (E-008). Read-only by design: the sheet is a user-maintained input
and Scout never writes to it (decision O-004).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import gspread
from google.oauth2.service_account import Credentials

from src import config
from src.clients.errors import SheetAccessError, describe

# Least privilege: read-only, and only Sheets. `drive.readonly` was requested but
# never used -- nothing here calls Drive (open_by_url resolves via the Sheets API
# alone), and the Drive API is not even enabled on the project. Scout never
# writes to the sheet; see decisions.md -> "[O-004] The sheet is input-only".
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

SheetRow = Dict[str, Any]


def _service_account_email() -> str:
    """Read the service account address, for error messages only."""
    try:
        with open(config.service_account_path()) as f:
            return json.load(f).get("client_email", "(unknown)")
    except Exception:
        return "(unknown)"


def get_gsheet_client() -> gspread.Client:
    credentials: Credentials = Credentials.from_service_account_file(
        str(config.service_account_path()), scopes=SCOPES
    )
    return gspread.authorize(credentials)


def _strip_phantom_columns(records: List[SheetRow]) -> List[SheetRow]:
    """Drop keys produced by unnamed columns.

    The grid is 1001x27 while only three columns are used, so gspread's header
    inference yields a trailing empty header and every record comes back with a
    phantom `''` key: {'Company Name': 'wolt', ..., '': ''}. Left alone it flows
    straight into the insert mapping.
    """
    return [{k: v for k, v in row.items() if k.strip()} for row in records]


def get_worksheet_records(worksheet_name: str) -> List[SheetRow]:
    """Read one worksheet as a list of dicts, keyed by header.

    Any failure is re-raised as `SheetAccessError` carrying a message that names
    the real cause -- gspread discards it otherwise (see `errors.py`).
    """
    sheet_url = config.sheet_url()
    try:
        client = get_gsheet_client()
        worksheet = client.open_by_url(sheet_url).worksheet(worksheet_name)
        records = worksheet.get_all_records()
    except Exception as exc:
        raise SheetAccessError(
            describe(
                exc, sheet_url=sheet_url, service_account=_service_account_email()
            )
        ) from exc
    return _strip_phantom_columns(records)


def get_companies() -> List[SheetRow]:
    """Read the company list from the configured worksheet.

    Replaces `get_processed_companies()` / `get_company_research()`, which asked
    for two worksheets ("Processed Companies", "Company Research") that do not
    exist -- the two-sheet model was designed but never built. Confirmed live:
    one worksheet, `Sheet1`, columns `Company Name | Comments | Link`.
    """
    return get_worksheet_records(config.get(config.COMPANIES_SHEET_NAME))
