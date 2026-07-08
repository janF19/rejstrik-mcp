import json
from pathlib import Path

import httpx
import respx

from rejstrik.registry.subsidies import (
    get_subsidies,
    parse_recipient,
    parse_subsidies,
)

_FIX = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def test_parse_recipient():
    rid, name, total = parse_recipient(_load("red_prijemci.json"))
    assert rid == "f7adf274-6635-4dc9-8edc-0693bbaa9ef2"
    assert "Budvar" in name
    assert total == 19536923.41


def test_parse_recipient_empty():
    assert parse_recipient([]) == (None, None, 0.0)


def test_parse_subsidies():
    subs = parse_subsidies(_load("red_dotace.json"))
    assert len(subs) == 2
    assert subs[0].provider.startswith("329")
    assert subs[0].amount == 191244


@respx.mock
def test_get_subsidies_full_flow():
    respx.post("https://red.fs.gov.cz/api/account/login").mock(
        return_value=httpx.Response(200, json={"token": "jwt"})
    )
    respx.post("https://red.fs.gov.cz/api/prijemci").mock(
        return_value=httpx.Response(200, json=_load("red_prijemci.json"))
    )
    respx.post("https://red.fs.gov.cz/api/dotace").mock(
        return_value=httpx.Response(200, json=_load("red_dotace.json"))
    )
    report = get_subsidies("00514152")
    assert report.ico == "00514152"
    assert report.count == 2
    assert report.total_amount == 19536923.41
    assert report.checked is True


@respx.mock
def test_get_subsidies_no_recipient_is_unchecked_empty():
    respx.post("https://red.fs.gov.cz/api/account/login").mock(
        return_value=httpx.Response(200, json={"token": "jwt"})
    )
    respx.post("https://red.fs.gov.cz/api/prijemci").mock(
        return_value=httpx.Response(200, json=[])
    )
    report = get_subsidies("99999999")
    assert report.count == 0 and report.subsidies == []


@respx.mock
def test_get_subsidies_http_error_degrades_gracefully():
    respx.post("https://red.fs.gov.cz/api/account/login").mock(
        return_value=httpx.Response(500)
    )
    report = get_subsidies("00514152")
    assert report.checked is False
