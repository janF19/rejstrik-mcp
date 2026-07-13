import httpx

from rejstrik.core.http import make_client
from rejstrik.registry.models import Company, legal_form_name

BASE = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty"


class CompanyNotFound(Exception):
    def __init__(self, ico: str) -> None:
        super().__init__(f"No company found for IČO {ico}")
        self.ico = ico


def parse_detail(payload: dict) -> Company:
    sidlo = payload.get("sidlo") or {}
    legal_form = payload.get("pravniForma")
    return Company(
        ico=str(payload["ico"]),
        name=payload.get("obchodniJmeno") or "",
        address=sidlo.get("textovaAdresa"),
        legal_form=legal_form,
        legal_form_name=legal_form_name(legal_form),
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


def search_by_name(
    name: str, limit: int = 10, client: httpx.Client | None = None
) -> list[Company]:
    owns = client is None
    client = client or make_client()
    try:
        resp = client.post(
            f"{BASE}/vyhledat",
            json={"obchodniJmeno": name, "start": 0, "pocet": limit},
        )
        resp.raise_for_status()
        items = resp.json().get("ekonomickeSubjekty") or []
        return [parse_detail(item) for item in items]
    finally:
        if owns:
            client.close()


def find_company(query: str, client: httpx.Client | None = None) -> Company:
    q = query.strip()
    if q.isdigit() and len(q) <= 8:
        return get_company(q, client=client)
    results = search_by_name(q, limit=1, client=client)
    if not results:
        raise CompanyNotFound(query)
    return results[0]
