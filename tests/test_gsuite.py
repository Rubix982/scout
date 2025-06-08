from src.clients import gsuite


def test_get_gsheet_client():
    client = gsuite.get_gsheet_client()
    assert client is not None


def test_get_processed_companies():
    data = gsuite.get_processed_companies()
    assert isinstance(data, list)
    if data:
        assert isinstance(data[0], dict)


def test_get_company_research():
    data = gsuite.get_company_research()
    assert isinstance(data, list)
    if data:
        assert isinstance(data[0], dict)
