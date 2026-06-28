from collections.abc import Callable

import httpx
from pydantic import BaseModel

from rejstrik.core.http import make_client
from rejstrik.registry.adis import UnreliablePayer, check_unreliable_payer

BASE = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty"


class VatStatus(BaseModel):
    ico: str
    dic: str | None = None
    is_vat_payer: bool = False
    is_unreliable: bool | None = None


def parse_vat(ico: str, payload: dict) -> VatStatus:
    dic = payload.get("dic")
    registrations = payload.get("seznamRegistraci") or {}
    active_vat = registrations.get("stavZdrojeDph") == "AKTIVNI"
    return VatStatus(
        ico=ico.strip().zfill(8),
        dic=dic,
        is_vat_payer=bool(dic) or active_vat,
    )


def check_vat(
    ico: str,
    client: httpx.Client | None = None,
    unreliable_check: Callable[[str], UnreliablePayer] | None = None,
) -> VatStatus:
    unreliable_check = unreliable_check or check_unreliable_payer
    ico = ico.strip().zfill(8)
    owns = client is None
    client = client or make_client()
    try:
        response = client.get(f"{BASE}/{ico}")
        response.raise_for_status()
        status = parse_vat(ico, response.json())
    except (httpx.HTTPError, ValueError, KeyError):
        return VatStatus(ico=ico, dic=None, is_vat_payer=False)
    finally:
        if owns:
            client.close()

    if status.dic:
        result = unreliable_check(status.dic)
        if result.status in ("reliable", "unreliable"):
            status.is_unreliable = result.status == "unreliable"
    return status
