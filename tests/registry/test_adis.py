from pathlib import Path

import httpx
import respx

from rejstrik.registry.adis import (
    UnreliablePayer,
    check_unreliable_payer,
    parse_unreliable,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "adis" / "reliable_00514152.xml"
ENDPOINT = "https://adisrws.mfcr.cz/adistc/axis2/services/rozhraniCRPDPH.rozhraniCRPDPHSOAP"


def test_parse_unreliable_reliable_payer():
    status = parse_unreliable("00514152", FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(status, UnreliablePayer)
    assert status.dic == "00514152"
    assert status.status == "reliable"


def test_parse_unreliable_handles_ano_and_nenalezen():
    ano = '<x nespolehlivyPlatce="ANO" dic="123"/>'
    nen = '<x nespolehlivyPlatce="NENALEZEN" dic="123"/>'
    assert parse_unreliable("123", ano).status == "unreliable"
    assert parse_unreliable("123", nen).status == "not_found"


@respx.mock
def test_check_unreliable_strips_cz_prefix_and_handles_error():
    respx.post(ENDPOINT).mock(return_value=httpx.Response(500))
    status = check_unreliable_payer("CZ00514152")
    assert status.dic == "00514152"
    assert status.status == "unknown"
