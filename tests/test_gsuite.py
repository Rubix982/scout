"""Google Sheets client tests.

These hit the real API, so they skip when credentials are absent. A missing local
secret is an environment condition, not a code defect -- previously the whole
module raised `FileNotFoundError` at import and took the rest of the suite with
it (E-001).
"""

import pytest

from src.clients import gsuite

from .conftest import requires_gcp_secrets

# The live sheet has ONE worksheet, `Sheet1`, with columns
# `Company Name | Comments | Link`. These two functions ask for worksheets named
# "Company Research" and "Processed Companies", which do not exist -- the
# two-sheet model was never built. Confirmed live: WorksheetNotFound.
#
# strict=True on purpose: when E-002 replaces these with a single-sheet ingest,
# an unexpected pass fails the suite and forces this marker to be removed rather
# than left to rot.
wrong_worksheet_model = pytest.mark.xfail(
    strict=True,
    raises=gsuite.gspread.exceptions.WorksheetNotFound,
    reason="E-002: code expects two worksheets; the real sheet has one (Sheet1)",
)


@requires_gcp_secrets
def test_get_gsheet_client():
    assert gsuite.get_gsheet_client() is not None


@requires_gcp_secrets
@wrong_worksheet_model
def test_get_processed_companies():
    data = gsuite.get_processed_companies()
    assert isinstance(data, list)
    if data:
        assert isinstance(data[0], dict)


@requires_gcp_secrets
@wrong_worksheet_model
def test_get_company_research():
    data = gsuite.get_company_research()
    assert isinstance(data, list)
    if data:
        assert isinstance(data[0], dict)
