from pathlib import Path

import httpx
import respx

from rejstrik.registry.isir import InsolvencyStatus, check_insolvency, parse_insolvency

FIXTURE = Path(__file__).parent.parent / "fixtures" / "isir" / "clean_00006947.xml"


def test_parse_insolvency_clean_record():
    payload = {"stav": {"kodChyba": "WS2"}, "data": []}
    status = parse_insolvency("00006947", payload)
    assert isinstance(status, InsolvencyStatus)
    assert status.ico == "00006947"
    assert status.checked is True
    assert status.in_insolvency is False
    assert status.cases == []


def test_parse_insolvency_positive_record():
    payload = {
        "data": [
            {
                "cisloSenatu": 60,
                "druhVec": "INS",
                "bcVec": 999,
                "rocnik": 2025,
                "druhStavKonkursu": "konkurs",
            }
        ]
    }
    status = parse_insolvency("1234567", payload)
    assert status.ico == "01234567"
    assert status.checked is True
    assert status.in_insolvency is True
    assert len(status.cases) == 1
    assert status.cases[0].case_number == "60 INS 999/2025"
    assert status.cases[0].state == "konkurs"


@respx.mock
def test_check_insolvency_parses_soap_empty_response():
    xml = FIXTURE.read_text(encoding="utf-8")
    respx.post("https://isir.justice.cz:8443/isir_cuzk_ws/IsirWsCuzkService").mock(
        return_value=httpx.Response(200, text=xml)
    )

    status = check_insolvency("00006947")

    assert status.checked is True
    assert status.in_insolvency is False


@respx.mock
def test_check_insolvency_returns_unknown_on_transport_error():
    respx.post("https://isir.justice.cz:8443/isir_cuzk_ws/IsirWsCuzkService").mock(
        return_value=httpx.Response(500)
    )
    status = check_insolvency("00006947")
    assert status.checked is False
    assert status.in_insolvency is False
