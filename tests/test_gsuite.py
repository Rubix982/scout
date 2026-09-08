"""Google Sheets client tests.

These hit the real API, so they skip when credentials are absent. A missing local
secret is an environment condition, not a code defect -- previously the whole
module raised `FileNotFoundError` at import and took the rest of the suite with
it (E-001).
"""

from src.clients import gsuite

from .conftest import requires_gcp_secrets


@requires_gcp_secrets
def test_get_gsheet_client():
    assert gsuite.get_gsheet_client() is not None


@requires_gcp_secrets
def test_get_processed_companies():
    data = gsuite.get_processed_companies()
    assert isinstance(data, list)
    if data:
        assert isinstance(data[0], dict)


@requires_gcp_secrets
def test_get_company_research():
    data = gsuite.get_company_research()
    assert isinstance(data, list)
    if data:
        assert isinstance(data[0], dict)
