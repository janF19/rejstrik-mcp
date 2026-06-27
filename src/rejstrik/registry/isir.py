# Adapted from cz-agents-mcp (MIT) (c) Martin Havel. See LICENSES/cz-agents-mcp-LICENSE.
from xml.etree import ElementTree

import httpx
from pydantic import BaseModel, Field

from rejstrik.core.http import make_client

ISIR_ENDPOINT = "https://isir.justice.cz:8443/isir_cuzk_ws/IsirWsCuzkService"


class InsolvencyCase(BaseModel):
    case_number: str | None = None
    state: str | None = None


class InsolvencyStatus(BaseModel):
    ico: str
    in_insolvency: bool
    cases: list[InsolvencyCase] = Field(default_factory=list)
    checked: bool = True


def parse_insolvency(ico: str, payload: dict) -> InsolvencyStatus:
    raw_cases = (
        payload.get("data") or payload.get("cases") or payload.get("events") or []
    )
    if isinstance(raw_cases, dict):
        raw_cases = [raw_cases]
    cases = [
        InsolvencyCase(
            case_number=_case_number(case),
            state=case.get("druhStavKonkursu") or case.get("state") or case.get("stav"),
        )
        for case in raw_cases
        if isinstance(case, dict)
    ]
    return InsolvencyStatus(
        ico=ico.strip().zfill(8),
        in_insolvency=bool(cases),
        cases=cases,
        checked=True,
    )


def check_insolvency(
    ico: str,
    client: httpx.Client | None = None,
) -> InsolvencyStatus:
    ico = ico.strip().zfill(8)
    owns = client is None
    client = client or make_client()
    try:
        response = client.post(
            ISIR_ENDPOINT,
            content=_build_envelope(ico),
            headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'},
        )
        response.raise_for_status()
        return parse_insolvency(ico, _parse_soap_response(response.text))
    except (httpx.HTTPError, ElementTree.ParseError, ValueError, KeyError):
        return InsolvencyStatus(
            ico=ico,
            in_insolvency=False,
            cases=[],
            checked=False,
        )
    finally:
        if owns:
            client.close()


def _case_number(case: dict) -> str | None:
    if case_number := case.get("caseNumber") or case.get("spisovaZnacka"):
        return str(case_number)
    senate = case.get("cisloSenatu")
    matter = case.get("druhVec")
    serial = case.get("bcVec")
    year = case.get("rocnik")
    if None in (senate, matter, serial, year):
        return None
    return f"{senate} {matter} {serial}/{year}"


def _build_envelope(ico: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <tns:getIsirWsCuzkDataRequest xmlns:tns="http://isirws.cca.cz/types/">
      <ic>{ico}</ic>
      <maxPocetVysledku>1</maxPocetVysledku>
      <filtrAktualniRizeni>T</filtrAktualniRizeni>
    </tns:getIsirWsCuzkDataRequest>
  </soap:Body>
</soap:Envelope>"""


def _parse_soap_response(xml: str) -> dict:
    root = ElementTree.fromstring(xml)
    response = _find_child(root, "getIsirWsCuzkDataResponse")
    if response is None:
        raise ValueError("No getIsirWsCuzkDataResponse in ISIR SOAP body")

    data = [
        _element_to_dict(item)
        for item in response.iter()
        if _local_name(item.tag) == "data"
    ]
    stav_el = _find_child(response, "stav")
    return {
        "data": data,
        "stav": _element_to_dict(stav_el) if stav_el is not None else {},
    }


def _find_child(element: ElementTree.Element, name: str) -> ElementTree.Element | None:
    for child in element.iter():
        if _local_name(child.tag) == name:
            return child
    return None


def _element_to_dict(element: ElementTree.Element) -> dict:
    result: dict[str, str] = {}
    for child in list(element):
        result[_local_name(child.tag)] = child.text or ""
    return result


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
