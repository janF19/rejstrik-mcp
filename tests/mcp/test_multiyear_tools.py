import inspect

from rejstrik.mcp import server


def test_extract_financials_has_year_params():
    sig = inspect.signature(server.extract_financials)
    assert "year" in sig.parameters and "filing_id" in sig.parameters


def test_ask_filing_has_year_params():
    sig = inspect.signature(server.ask_filing)
    assert "year" in sig.parameters and "filing_id" in sig.parameters


def test_analyze_company_financials_has_years():
    sig = inspect.signature(server.analyze_company_financials)
    assert sig.parameters["years"].default == 1
