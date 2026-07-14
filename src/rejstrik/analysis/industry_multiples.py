from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data" / "industry_multiples.json"
FALLBACK_INDUSTRY_KEY = "total_market_ex_financials"
INDUSTRY_KEY_ALIASES = {
    "photonics_optoelectronics": "electronics_general",
}


@dataclass(frozen=True)
class IndustryMultiple:
    industry_key: str
    source_industry: str
    ev_ebitda: float
    firms: int
    source: str
    source_url: str
    as_of: str
    region: str


@lru_cache(maxsize=1)
def load_industry_multiples() -> dict:
    with DATA_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def get_industry_multiple(industry_key: str | None) -> IndustryMultiple:
    data = load_industry_multiples()
    requested = (industry_key or "").strip() or FALLBACK_INDUSTRY_KEY
    requested = INDUSTRY_KEY_ALIASES.get(requested, requested)
    rows = {row["industry_key"]: row for row in data["rows"]}
    row = rows.get(requested) or rows[FALLBACK_INDUSTRY_KEY]
    return IndustryMultiple(
        industry_key=row["industry_key"],
        source_industry=row["source_industry"],
        ev_ebitda=float(row["ev_ebitda"]),
        firms=int(row["firms"]),
        source=data["source"],
        source_url=data["source_url"],
        as_of=data["as_of"],
        region=data["region"],
    )
