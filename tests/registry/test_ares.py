import json
from pathlib import Path

import httpx
import pytest
import respx

from rejstrik.registry.ares import CompanyNotFound, get_company, parse_detail

FIXTURE = Path(__file__).parent.parent / "fixtures" / "ares" / "detail_00006947.json"


def test_parse_detail_maps_core_fields():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    company = parse_detail(payload)
    assert company.ico == "00006947"
    assert company.name  # non-empty
    assert isinstance(company.name, str)


@respx.mock
def test_get_company_uses_detail_endpoint():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    route = respx.get(
        "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/00006947"
    ).mock(return_value=httpx.Response(200, json=payload))
    company = get_company("6947")  # unpadded on purpose
    assert route.called
    assert company.ico == "00006947"


@respx.mock
def test_get_company_raises_on_404():
    respx.get(
        "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/00000000"
    ).mock(return_value=httpx.Response(404))
    with pytest.raises(CompanyNotFound):
        get_company("00000000")


def test_parse_detail_extracts_nace_codes():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    company = parse_detail(payload)
    assert company.nace_codes == ["84110"]


def test_parse_detail_missing_nace_defaults_empty():
    company = parse_detail({"ico": "12345678", "obchodniJmeno": "X"})
    assert company.nace_codes == []
