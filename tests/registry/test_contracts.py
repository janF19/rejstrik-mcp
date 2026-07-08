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


def test_parse_contracts_numeric_value():
    html = '''
    <table class="searchResultList">
    <tbody>
    <tr>
        <td class="1">Party</td>
        <td class="2">Some subject</td>
        <td class="3">ano</td>
        <td class="4">01.01.2026</td>
        <td class="number nobr 5">1 234 567,89</td>
        <td class="6">Other party</td>
        <td class="btn no-sort"><a href="/smlouva/123?backlink=x">Detail</a></td>
    </tr>
    </tbody>
    </table>
    '''
    contracts = parse_contracts(html)
    assert len(contracts) == 1
    assert contracts[0].value == 1234567.89


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
