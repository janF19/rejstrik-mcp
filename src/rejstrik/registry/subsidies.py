import httpx
from pydantic import BaseModel

from rejstrik.core.http import make_client

_LOGIN = "https://red.fs.gov.cz/api/account/login"
_RECIPIENTS = "https://red.fs.gov.cz/api/prijemci"
_SUBSIDIES = "https://red.fs.gov.cz/api/dotace"


class Subsidy(BaseModel):
    project_number: str | None = None
    project_name: str | None = None
    provider: str | None = None
    amount: float | None = None


class SubsidyReport(BaseModel):
    ico: str
    recipient_name: str | None = None
    total_amount: float = 0.0
    count: int = 0
    subsidies: list[Subsidy] = []
    checked: bool = True


def parse_recipient(payload: list) -> tuple[str | None, str | None, float]:
    if not payload:
        return None, None, 0.0
    first = payload[0]
    return first.get("id"), first.get("prijemce"), float(first.get("castka") or 0.0)


def parse_subsidies(payload: list) -> list[Subsidy]:
    return [
        Subsidy(
            project_number=item.get("cisloProjektu"),
            project_name=item.get("nazevProjektu") or None,
            provider=item.get("poskytovatelDotace"),
            amount=(float(item["castka"]) if item.get("castka") is not None else None),
        )
        for item in payload
    ]


def _token(client: httpx.Client) -> str:
    resp = client.post(_LOGIN, json={"key": ""})
    resp.raise_for_status()
    return resp.json()["token"]


def get_subsidies(ico: str, client: httpx.Client | None = None) -> SubsidyReport:
    ico = ico.strip().zfill(8)
    owns = client is None
    client = client or make_client()
    try:
        headers = {"Authorization": f"Bearer {_token(client)}"}
        recipients = client.post(
            _RECIPIENTS,
            headers=headers,
            json={"skip": 0, "take": 10, "where": [{"field": "search", "value": ico}]},
        )
        recipients.raise_for_status()
        rid, name, total = parse_recipient(recipients.json())
        if rid is None:
            return SubsidyReport(ico=ico, count=0)
        detail = client.post(
            _SUBSIDIES,
            headers=headers,
            json={
                "skip": 0,
                "take": 50,
                "where": [{"field": "prijemceId", "value": rid}],
            },
        )
        detail.raise_for_status()
        subsidies = parse_subsidies(detail.json())
        return SubsidyReport(
            ico=ico,
            recipient_name=name,
            total_amount=total,
            count=len(subsidies),
            subsidies=subsidies,
        )
    except (httpx.HTTPError, ValueError, KeyError):
        return SubsidyReport(ico=ico, checked=False)
    finally:
        if owns:
            client.close()
