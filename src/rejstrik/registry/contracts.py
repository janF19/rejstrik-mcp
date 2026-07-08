import re

import httpx
from pydantic import BaseModel
from selectolax.parser import HTMLParser

from rejstrik.core.http import make_client

_SEARCH = "https://smlouvy.gov.cz/vyhledavani"
_BASE = "https://smlouvy.gov.cz"
_NUM_RE = re.compile(r"[\d\s.,]+")


class Contract(BaseModel):
    subject: str | None = None
    date: str | None = None
    value: float | None = None
    detail_url: str | None = None


class ContractReport(BaseModel):
    ico: str
    count: int = 0
    total_value: float = 0.0
    contracts: list[Contract] = []
    checked: bool = True


def _to_amount(text: str) -> float | None:
    cleaned = text.strip().replace("\xa0", " ")
    if not cleaned or not any(ch.isdigit() for ch in cleaned):
        return None
    digits = cleaned.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(digits)
    except ValueError:
        return None


def parse_contracts(html: str) -> list[Contract]:
    tree = HTMLParser(html)
    contracts: list[Contract] = []
    for link in tree.css("a[href^='/smlouva/']"):
        row = link.parent
        while row is not None and row.tag != "tr":
            row = row.parent
        if row is None:
            continue
        cells = row.css("td")
        subject = cells[1].text(strip=True) if len(cells) > 1 else None
        date = cells[3].text(strip=True) if len(cells) > 3 else None
        value = _to_amount(cells[4].text(strip=True)) if len(cells) > 4 else None
        href = link.attributes.get("href") or ""
        contracts.append(
            Contract(
                subject=subject or None,
                date=date or None,
                value=value,
                detail_url=_BASE + href if href.startswith("/") else href,
            )
        )
    return contracts


def get_contracts(ico: str, client: httpx.Client | None = None) -> ContractReport:
    ico = ico.strip().zfill(8)
    owns = client is None
    client = client or make_client()
    try:
        resp = client.get(_SEARCH, params={"q": ico})
        resp.raise_for_status()
        contracts = parse_contracts(resp.text)
        total = sum(c.value for c in contracts if c.value)
        return ContractReport(
            ico=ico, count=len(contracts), total_value=total, contracts=contracts
        )
    except (httpx.HTTPError, ValueError):
        return ContractReport(ico=ico, checked=False)
    finally:
        if owns:
            client.close()
