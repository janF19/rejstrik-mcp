import json
from pathlib import Path

import httpx
import respx

from rejstrik.registry.ares import parse_detail, get_company, CompanyNotFound
import pytest

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
