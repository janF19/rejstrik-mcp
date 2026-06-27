# Adapted from cz-agents-mcp (MIT) (c) Martin Havel. See LICENSES/cz-agents-mcp-LICENSE.
import httpx
from pydantic import BaseModel

from rejstrik.core.http import make_client

BASE = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-vr"


class Officer(BaseModel):
    name: str
    role: str | None = None
    since: str | None = None


def parse_statutory_bodies(payload: dict) -> list[Officer]:
    officers: list[Officer] = []
    for record in _active_records(payload):
        for organ in record.get("statutarniOrgany") or []:
            if organ.get("datumVymazu"):
                continue
            role = organ.get("nazevOrganu") or organ.get("typOrganu")
            for member in organ.get("clenoveOrganu") or []:
                if member.get("datumVymazu"):
                    continue
                name = _member_name(member)
                if name:
                    officers.append(
                        Officer(
                            name=name,
                            role=_member_role(member) or role,
                            since=member.get("datumZapisu"),
                        )
                    )
    return officers


def get_statutory_bodies(
    ico: str,
    client: httpx.Client | None = None,
) -> list[Officer]:
    ico = ico.strip().zfill(8)
    owns = client is None
    client = client or make_client()
    try:
        response = client.get(f"{BASE}/{ico}")
        response.raise_for_status()
        return parse_statutory_bodies(response.json())
    except (httpx.HTTPError, ValueError, KeyError):
        return []
    finally:
        if owns:
            client.close()


def _active_records(payload: dict) -> list[dict]:
    records = payload.get("zaznamy") or []
    active = [record for record in records if record.get("stavSubjektu") == "AKTIVNI"]
    return active or records[:1]


def _member_name(member: dict) -> str | None:
    person = member.get("fyzickaOsoba") or (member.get("osoba") or {}).get(
        "fyzickaOsoba"
    )
    if person:
        parts = [
            person.get("titulPredJmenem"),
            person.get("jmeno"),
            person.get("prijmeni"),
            person.get("titulZaJmenem"),
        ]
        full = " ".join(str(part).strip() for part in parts if part).strip()
        return full or None

    legal = member.get("pravnickaOsoba") or (member.get("osoba") or {}).get(
        "pravnickaOsoba"
    )
    if legal:
        return legal.get("obchodniJmeno") or legal.get("nazev")
    return None


def _member_role(member: dict) -> str | None:
    membership = member.get("clenstvi") or {}
    function = member.get("funkce") or membership.get("funkce") or {}
    return function.get("nazev") or member.get("nazevAngazma")
