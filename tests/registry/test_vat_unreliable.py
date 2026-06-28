import json
from pathlib import Path

import httpx
import respx

from rejstrik.registry.adis import UnreliablePayer
from rejstrik.registry.vat import check_vat

DETAIL = Path(__file__).parent.parent / "fixtures" / "ares" / "detail_00006947.json"
ARES = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/00006947"


@respx.mock
def test_check_vat_sets_is_unreliable_from_adis():
    payload = json.loads(DETAIL.read_text(encoding="utf-8"))
    respx.get(ARES).mock(return_value=httpx.Response(200, json=payload))
    calls = []

    def fake_adis(dic, client=None):
        calls.append(dic)
        return UnreliablePayer(dic=dic, status="unreliable")

    status = check_vat("00006947", unreliable_check=fake_adis)
    assert status.is_unreliable is True
    assert calls == ["CZ00006947"]


@respx.mock
def test_check_vat_no_dic_skips_adis():
    respx.get(
        "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/00000000"
    ).mock(return_value=httpx.Response(200, json={"ico": "00000000"}))
    called = []
    status = check_vat("00000000", unreliable_check=lambda d, client=None: called.append(d))
    assert status.is_unreliable is None
    assert called == []
