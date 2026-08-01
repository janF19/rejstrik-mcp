from pathlib import Path

import httpx
import pytest
import respx

from rejstrik.filings.justice import clear_filings_cache, list_filings

FIXTURES = Path(__file__).parent.parent / "fixtures" / "justice"
SEARCH_HTML = (FIXTURES / "legacy_search_00514152.html").read_text(encoding="utf-8")
DEEDS_HTML = (FIXTURES / "legacy_deeds_00514152.html").read_text(encoding="utf-8")

_NEW_FILINGS_URL = (
    "https://verejnerejstriky.msp.gov.cz/api/sbirka-listin/subjekty/514152"
)

_API_JSON = {
    "status": "OK",
    "vysledekdetail": {
        "prehledlistin": [
            {
                "typlistiny": "účetní závěrka [2024]",
                "detail": [{"obsah": {"digitalnipodoba": {"documentid": "1"}}}],
            }
        ]
    },
}


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_filings_cache()
    yield
    clear_filings_cache()


@respx.mock
def test_second_call_within_ttl_hits_network_once(monkeypatch):
    monkeypatch.setenv("REJSTRIK_FILINGS_TTL_SECONDS", "900")
    route = respx.get(_NEW_FILINGS_URL).mock(
        return_value=httpx.Response(200, json=_API_JSON)
    )
    now = [1000.0]
    clock = lambda: now[0]

    first = list_filings("00514152", clock=clock)
    now[0] += 60.0  # still within TTL
    second = list_filings("00514152", clock=clock)

    assert route.call_count == 1
    assert [f.title for f in first] == [f.title for f in second]


@respx.mock
def test_call_after_ttl_expiry_refetches(monkeypatch):
    monkeypatch.setenv("REJSTRIK_FILINGS_TTL_SECONDS", "900")
    route = respx.get(_NEW_FILINGS_URL).mock(
        return_value=httpx.Response(200, json=_API_JSON)
    )
    now = [1000.0]
    clock = lambda: now[0]

    list_filings("00514152", clock=clock)
    now[0] += 901.0  # past TTL
    list_filings("00514152", clock=clock)

    assert route.call_count == 2


@respx.mock
def test_ttl_zero_disables_cache(monkeypatch):
    monkeypatch.setenv("REJSTRIK_FILINGS_TTL_SECONDS", "0")
    route = respx.get(_NEW_FILINGS_URL).mock(
        return_value=httpx.Response(200, json=_API_JSON)
    )
    list_filings("00514152")
    list_filings("00514152")
    assert route.call_count == 2
