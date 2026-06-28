from xml.etree import ElementTree

import httpx
from pydantic import BaseModel

from rejstrik.core.http import make_client

ADIS_ENDPOINT = (
    "https://adisrws.mfcr.cz/adistc/axis2/services/rozhraniCRPDPH.rozhraniCRPDPHSOAP"
)
_NS = "http://adis.mfcr.cz/rozhraniCRPDPH/"
_STATUS_MAP = {"NE": "reliable", "ANO": "unreliable", "NENALEZEN": "not_found"}


class UnreliablePayer(BaseModel):
    dic: str
    status: str


def parse_unreliable(dic: str, xml: str) -> UnreliablePayer:
    root = ElementTree.fromstring(xml)
    for element in root.iter():
        raw = element.attrib.get("nespolehlivyPlatce")
        if raw is not None:
            return UnreliablePayer(dic=dic, status=_STATUS_MAP.get(raw, "unknown"))
    return UnreliablePayer(dic=dic, status="unknown")


def _build_envelope(dic: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:r="{_NS}">
  <soapenv:Body>
    <r:StatusNespolehlivyPlatceRequest>
      <r:dic>{dic}</r:dic>
    </r:StatusNespolehlivyPlatceRequest>
  </soapenv:Body>
</soapenv:Envelope>"""


def _normalize_dic(dic: str) -> str:
    dic = dic.strip()
    if dic.lower().startswith("cz"):
        return dic[2:]
    return dic


def check_unreliable_payer(
    dic: str, client: httpx.Client | None = None
) -> UnreliablePayer:
    dic = _normalize_dic(dic)
    owns_client = client is None
    client = client or make_client()
    try:
        response = client.post(
            ADIS_ENDPOINT,
            content=_build_envelope(dic),
            headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'},
        )
        response.raise_for_status()
        return parse_unreliable(dic, response.text)
    except (httpx.HTTPError, ElementTree.ParseError, ValueError):
        return UnreliablePayer(dic=dic, status="unknown")
    finally:
        if owns_client:
            client.close()
