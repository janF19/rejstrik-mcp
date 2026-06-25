import httpx

from rejstrik.core.http import make_client
from rejstrik.registry.models import Company

BASE = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty"


class CompanyNotFound(Exception):
    def __init__(self, ico: str) -> None:
        super().__init__(f"No company found for IČO {ico}")
        self.ico = ico


def parse_detail(payload: dict) -> Company:
    sidlo = payload.get("sidlo") or {}
    return Company(
        ico=str(payload["ico"]),
        name=payload.get("obchodniJmeno") or "",
        address=sidlo.get("textovaAdresa"),
        legal_form=payload.get("pravniForma"),
        founded=payload.get("datumVzniku"),
    )


def get_company(ico: str, client: httpx.Client | None = None) -> Company:
    ico = ico.strip().zfill(8)
    owns = client is None
    client = client or make_client()
    try:
        resp = client.get(f"{BASE}/{ico}")
        if resp.status_code == 404:
            raise CompanyNotFound(ico)
        resp.raise_for_status()
        return parse_detail(resp.json())
    finally:
        if owns:
            client.close()
