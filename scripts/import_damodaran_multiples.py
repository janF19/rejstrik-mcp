"""Manual importer for Damodaran Europe EV/EBITDA industry multiples.

Network-using manual tooling like scripts/smoke.py — NEVER run in CI or tests.
Tests read only the committed JSON. Requires xlrd:  pip install xlrd

Usage:  python scripts/import_damodaran_multiples.py [--as-of YYYY-MM-DD]
Writes: src/rejstrik/analysis/data/industry_multiples.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import httpx
import xlrd

SOURCE_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/vebitdaEurope.xls"
SOURCE = "Damodaran Europe industry EV/EBITDA"
REGION = "Europe"
METRIC = "EV/EBITDA for positive EBITDA firms"
DEFAULT_AS_OF = "2026-01-05"
OUTPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "rejstrik"
    / "analysis"
    / "data"
    / "industry_multiples.json"
)
SHEET_NAME = "Industry Averages"
TOTAL_MARKET_EX_FINANCIALS_ALIAS = {
    "total_market_without_financials": "total_market_ex_financials",
}


def slugify_industry(name: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", name.lower()).strip("_")
    return TOTAL_MARKET_EX_FINANCIALS_ALIAS.get(slug, slug)


def _cell_text(value: Any) -> str:
    return str(value).strip()


def _find_header_row(sheet: xlrd.sheet.Sheet) -> int:
    for row_idx in range(sheet.nrows):
        values = [
            _cell_text(sheet.cell_value(row_idx, col_idx))
            for col_idx in range(sheet.ncols)
        ]
        if (
            "Industry Name" in values
            and "Number of firms" in values
            and "EV/EBITDA" in values
        ):
            return row_idx
    raise RuntimeError("Could not find Damodaran industry-average header row")


def _column_index(headers: list[str], header: str, *, occurrence: int = 1) -> int:
    matches = [idx for idx, value in enumerate(headers) if value == header]
    if len(matches) < occurrence:
        raise RuntimeError(f"Could not find header {header!r} occurrence {occurrence}")
    return matches[occurrence - 1]


def _positive_number(value: Any) -> float | None:
    if isinstance(value, str):
        value = value.strip()
        if not value or value.upper() in {"NA", "N/A", "NM"}:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _firm_count(value: Any) -> int:
    try:
        firms = int(float(value))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid firm count {value!r}") from exc
    if firms < 0:
        raise RuntimeError(f"Invalid negative firm count {firms}")
    return firms


def parse_multiples(workbook_bytes: bytes, *, as_of: str) -> dict[str, Any]:
    workbook = xlrd.open_workbook(file_contents=workbook_bytes)
    sheet = workbook.sheet_by_name(SHEET_NAME)
    header_row = _find_header_row(sheet)
    headers = [
        _cell_text(sheet.cell_value(header_row, col_idx))
        for col_idx in range(sheet.ncols)
    ]
    industry_col = _column_index(headers, "Industry Name")
    firms_col = _column_index(headers, "Number of firms")
    ev_ebitda_col = _column_index(headers, "EV/EBITDA", occurrence=1)

    rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for row_idx in range(header_row + 1, sheet.nrows):
        source_industry = _cell_text(sheet.cell_value(row_idx, industry_col))
        if not source_industry:
            continue
        ev_ebitda = _positive_number(sheet.cell_value(row_idx, ev_ebitda_col))
        if ev_ebitda is None:
            continue
        industry_key = slugify_industry(source_industry)
        if industry_key in seen_keys:
            raise RuntimeError(f"Duplicate industry key {industry_key!r}")
        seen_keys.add(industry_key)
        rows.append(
            {
                "industry_key": industry_key,
                "source_industry": source_industry,
                "firms": _firm_count(sheet.cell_value(row_idx, firms_col)),
                "ev_ebitda": ev_ebitda,
            }
        )

    if len(rows) < 60:
        raise RuntimeError(
            f"Expected at least 60 positive EV/EBITDA rows, got {len(rows)}"
        )
    if "total_market_ex_financials" not in seen_keys:
        raise RuntimeError("Missing total_market_ex_financials fallback row")

    return {
        "source": SOURCE,
        "source_url": SOURCE_URL,
        "as_of": as_of,
        "region": REGION,
        "metric": METRIC,
        "rows": rows,
    }


def download_workbook(url: str) -> bytes:
    response = httpx.get(url, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    return response.content


def write_dataset(dataset: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dataset, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Damodaran Europe EV/EBITDA industry multiples."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--source-url", default=SOURCE_URL)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    dataset = parse_multiples(download_workbook(args.source_url), as_of=args.as_of)
    write_dataset(dataset, args.output)
    print(f"Wrote {len(dataset['rows'])} rows to {args.output}")


if __name__ == "__main__":
    main()
