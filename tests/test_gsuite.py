"""Google Sheets client tests (E-002).

Live tests hit the real API and skip when credentials are absent -- a missing
local secret is an environment condition, not a code defect. The unit tests below
need no network.

The previous `xfail(strict=True)` markers are gone: they recorded that the code
asked for two worksheets ("Company Research", "Processed Companies") that do not
exist. E-002 replaced that with a single-sheet read, so the markers had to be
removed rather than left to rot -- which is what strict mode was for.
"""

from __future__ import annotations

import gspread
import pytest

from src.clients import errors, gsuite

from .conftest import requires_gcp_secrets


class _FakeResponse:
    """Minimal stand-in for requests.Response; APIError only needs .json()."""

    def __init__(self, payload):
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def _api_error(payload) -> gspread.exceptions.APIError:
    return gspread.exceptions.APIError(_FakeResponse(payload))


# --- unit: phantom column stripping ------------------------------------------


def test_strip_phantom_columns_removes_unnamed_keys():
    """The 1001x27 grid yields a trailing empty header and a phantom '' key."""
    rows = [{"Company Name": "wolt", "Comments": "", "Link": "", "": ""}]
    assert gsuite._strip_phantom_columns(rows) == [
        {"Company Name": "wolt", "Comments": "", "Link": ""}
    ]


def test_strip_phantom_columns_removes_whitespace_only_keys():
    rows = [{"Company Name": "wolt", "  ": "junk"}]
    assert gsuite._strip_phantom_columns(rows) == [{"Company Name": "wolt"}]


# --- unit: error unmasking ---------------------------------------------------


def test_disabled_api_is_not_reported_as_a_sharing_problem():
    """The regression this module exists for.

    gspread's open_by_key catches APIError and re-raises a bare PermissionError,
    discarding the message. During setup that made a disabled Sheets API read as
    "the sheet isn't shared", which sent the diagnosis the wrong way.
    """
    cause = _api_error(
        {
            "error": {
                "code": 403,
                "status": "PERMISSION_DENIED",
                "message": "Google Sheets API has not been used in project 1 before or it is disabled.",
                "details": [
                    {
                        "reason": "SERVICE_DISABLED",
                        "metadata": {"serviceTitle": "Google Sheets API"},
                    }
                ],
            }
        }
    )
    masked = PermissionError()
    masked.__cause__ = cause

    message = errors.describe(
        masked, sheet_url="https://example/sheet", service_account="svc@example.com"
    )
    assert "not enabled" in message
    assert "NOT a sharing problem" in message
    assert "Google Sheets API" in message


def test_genuine_permission_denied_names_the_service_account():
    cause = _api_error(
        {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "caller lacks permission"}}
    )
    masked = PermissionError()
    masked.__cause__ = cause

    message = errors.describe(
        masked, sheet_url="https://example/sheet", service_account="svc@example.com"
    )
    assert "Share it" in message
    assert "svc@example.com" in message


def test_not_found_points_at_sheet_url():
    cause = _api_error({"error": {"code": 404, "status": "NOT_FOUND", "message": "not found"}})
    message = errors.describe(
        cause, sheet_url="https://example/sheet", service_account="svc@example.com"
    )
    assert "SHEET_URL" in message


def test_unparseable_error_degrades_to_the_exception_itself():
    message = errors.describe(
        ValueError("boom"), sheet_url="u", service_account="s"
    )
    assert "ValueError" in message and "boom" in message


# --- live ---------------------------------------------------------------------


@requires_gcp_secrets
def test_get_gsheet_client():
    assert gsuite.get_gsheet_client() is not None


@requires_gcp_secrets
def test_get_companies_reads_the_real_sheet():
    rows = gsuite.get_companies()
    assert isinstance(rows, list) and rows
    assert set(rows[0]) == {"Company Name", "Comments", "Link"}, (
        "unexpected columns -- has the sheet gained Type/Board URL? that is E-010"
    )
    assert all(k.strip() for k in rows[0]), "phantom column leaked through"


@requires_gcp_secrets
def test_missing_worksheet_raises_sheet_access_error():
    with pytest.raises(gsuite.SheetAccessError) as exc:
        gsuite.get_worksheet_records("No Such Worksheet")
    assert "not found" in str(exc.value).lower()
