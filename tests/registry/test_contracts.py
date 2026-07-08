from pathlib import Path

import httpx
import respx

from rejstrik.registry.contracts import get_contracts, parse_contracts

_FIX = Path(__file__).parent / "fixtures"


def test_parse_contracts_extracts_rows():
    html = (_FIX / "smlouvy_search.html").read_text(encoding="utf-8")
    contracts = parse_contracts(html)
    assert contracts, "expected at least one contract row"
    assert any(c.detail_url and "/smlouva/" in c.detail_url for c in contracts)


def test_parse_contracts_empty_html():
    assert parse_contracts("<html><body>Nenalezeno</body></html>") == []


@respx.mock
def test_get_contracts_success():
    html = (_FIX / "smlouvy_search.html").read_text(encoding="utf-8")
    respx.get("https://smlouvy.gov.cz/vyhledavani").mock(
        return_value=httpx.Response(200, text=html)
    )
    report = get_contracts("00514152")
    assert report.ico == "00514152"
    assert report.count == len(parse_contracts(html))
    assert report.checked is True


@respx.mock
def test_get_contracts_http_error_degrades():
    respx.get("https://smlouvy.gov.cz/vyhledavani").mock(
        return_value=httpx.Response(500)
    )
    report = get_contracts("00514152")
    assert report.checked is False and report.contracts == []
