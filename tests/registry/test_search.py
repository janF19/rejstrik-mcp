import json
from pathlib import Path

import httpx
import pytest
import respx

from rejstrik.registry.ares import search_by_name, find_company, CompanyNotFound

FX = Path(__file__).parent.parent / "fixtures" / "ares"


@respx.mock
def test_search_by_name_returns_companies():
    payload = json.loads((FX / "search_budvar.json").read_text(encoding="utf-8"))
    respx.post(
        "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/vyhledat"
    ).mock(return_value=httpx.Response(200, json=payload))
    results = search_by_name("Budvar")
    assert len(results) >= 1
    assert all(len(c.ico) == 8 for c in results)


@respx.mock
def test_find_company_numeric_query_uses_detail():
    detail = json.loads((FX / "detail_00006947.json").read_text(encoding="utf-8"))
    route = respx.get(
        "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/00006947"
    ).mock(return_value=httpx.Response(200, json=detail))
    company = find_company("6947")
    assert route.called
    assert company.ico == "00006947"


@respx.mock
def test_find_company_empty_search_raises():
    respx.post(
        "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/vyhledat"
    ).mock(return_value=httpx.Response(200, json={"ekonomickeSubjekty": []}))
    with pytest.raises(CompanyNotFound):
        find_company("NoSuchCompanyXYZ")
