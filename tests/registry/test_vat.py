import json
from pathlib import Path

import httpx
import respx

from rejstrik.registry.vat import VatStatus, check_vat, parse_vat

DETAIL = Path(__file__).parent.parent / "fixtures" / "ares" / "detail_00006947.json"


def test_parse_vat_reads_dic_from_detail():
    payload = json.loads(DETAIL.read_text(encoding="utf-8"))
    status = parse_vat("00006947", payload)
    assert isinstance(status, VatStatus)
    assert status.ico == "00006947"
    assert status.dic == "CZ00006947"
    assert status.is_vat_payer is True


def test_parse_vat_no_dic_is_not_payer():
    status = parse_vat("00000000", {"ico": "00000000"})
    assert status.dic is None
    assert status.is_vat_payer is False


@respx.mock
def test_check_vat_returns_not_payer_on_error():
    respx.get(
        "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/00006947"
    ).mock(return_value=httpx.Response(500))
    status = check_vat("00006947")
    assert status.is_vat_payer is False
