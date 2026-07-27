#!/usr/bin/env python3
"""Render the Czech showcase card for the README.

Builds a real `analyze_financials` + `estimate_valuation` run on ROBE
lighting's filed 2023 figures (the same figures `scripts/demo_analyze.py`
replays) and renders it as a standalone HTML file, styled with the
product's own `_STYLE` from `rejstrik.mcp.card`, for screenshotting into
`docs/media/report-card.png`.

Usage:
    python scripts/render_showcase_card.py --out .showcase-card.html
"""

import argparse
import html

from rejstrik.analysis.industry_multiples import get_industry_multiple
from rejstrik.documents.schema import CanonicalFigures, FinancialStatement, Figure
from rejstrik.mcp.card import _STYLE
from rejstrik.mcp.server import analyze_financials, estimate_valuation

_RATIO_LABELS = (
    ("current_ratio", "Běžná likvidita", "ratio"),
    ("equity_ratio", "Kapitálová vybavenost", "pct"),
    ("debt_to_equity", "Zadluženost", "ratio"),
    ("net_margin", "Čistá marže", "pct"),
    ("return_on_equity", "ROE", "pct"),
    ("quick_ratio", "Rychlá likvidita", "ratio"),
    ("return_on_assets", "ROA", "pct"),
    ("asset_turnover", "Obrat aktiv", "times"),
    ("interest_coverage", "Úrokové krytí", "times"),
    ("operating_margin", "Provozní marže", "pct"),
    ("ocf_to_liabilities", "Provozní CF / závazky", "pct"),
)

_YEARLY_LABELS = (
    ("revenue", "Tržby"),
    ("net_profit", "Čistý zisk"),
    ("total_assets", "Aktiva celkem"),
    ("equity", "Vlastní kapitál"),
)

_STAGE_STYLE = """
body{margin:0;padding:40px 16px;background:#eef2f6;display:flex;justify-content:center}
.card{width:600px;background:#fff;border-radius:12px;box-shadow:0 10px 30px rgba(15,23,42,.14);overflow:hidden}
"""


def _esc(value: object) -> str:
    return html.escape(str(value))


def _czech_int(value: float) -> str:
    return f"{round(value):,}".replace(",", " ")


def _czech_dec(value: float, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def _fmt_ratio(value: float | None, kind: str) -> str:
    if value is None:
        return "-"
    if kind == "pct":
        return f"{_czech_dec(value * 100, 1)} %"
    if kind == "times":
        return f"{_czech_dec(value, 2)}×"
    return _czech_dec(value, 2)


def _fmt_mld(value_thousands_czk: float) -> str:
    return f"{_czech_dec(value_thousands_czk / 1_000_000, 1)} mld Kč"


def _build_statement() -> FinancialStatement:
    canon = CanonicalFigures(
        total_assets=Figure(label="Aktiva celkem", value=3_541_478),
        current_assets=Figure(label="Oběžná aktiva", value=2_415_279),
        equity=Figure(label="Vlastní kapitál", value=3_039_871),
        total_liabilities=Figure(label="Cizí zdroje", value=499_199),
        current_liabilities=Figure(label="Krátkodobé závazky", value=382_436),
        revenue=Figure(
            label="Tržby z prodeje výrobků, služeb a zboží", value=3_886_882
        ),
        operating_profit=Figure(label="Provozní výsledek hospodaření", value=903_044),
        net_profit=Figure(label="Výsledek hospodaření za účetní období", value=752_222),
        interest_expense=Figure(label="Nákladové úroky", value=0),
        cash=Figure(label="Peněžní prostředky", value=532_191),
        inventories=Figure(label="Zásoby", value=1_201_907),
        receivables=Figure(label="Pohledávky", value=681_181),
        operating_cash_flow=Figure(
            label="Čistý peněžní tok z provozní činnosti", value=362_734
        ),
        depreciation_amortization=Figure(label="Odpisy", value=62_144),
    )
    return FinancialStatement(
        company_name="ROBE lighting s.r.o.",
        ico="64088791",
        period_year=2023,
        unit="thousands_czk",
        canonical=canon,
    )


_CONFIDENCE_CZ = {"high": "vysoká", "medium": "střední", "low": "nízká"}


def render_card() -> str:
    statement = _build_statement()
    report = analyze_financials([statement])
    valuation = estimate_valuation([statement], industry_key="electrical_equipment")
    base = get_industry_multiple(valuation.industry_key)

    year = report.yearly[0]
    yearly_rows = "".join(
        f"<tr><td class='k'>{_esc(label)}</td>"
        f"<td>{_esc(_czech_int(getattr(year, attr)))}</td></tr>"
        for attr, label in _YEARLY_LABELS
    )
    yearly_html = (
        "<h2>Hodnoty po letech</h2>"
        f"<table><tr><th>Ukazatel</th><th>{_esc(report.period_year)}</th></tr>"
        f"{yearly_rows}</table>"
    )

    ratios = report.ratios.model_dump()
    ratio_rows = "".join(
        f"<tr><td class='k'>{_esc(label)}</td>"
        f"<td>{_esc(_fmt_ratio(ratios.get(key), kind))}</td></tr>"
        for key, label, kind in _RATIO_LABELS
    )
    ratios_html = f"<h2>Poměrové ukazatele</h2><table>{ratio_rows}</table>"

    correction = valuation.final_multiple / valuation.base_multiple
    valuation_html = f"""
      <h2>Orientační hodnota</h2>
      <div class="pm">
        <div style="font-size:22px;font-weight:600">{_esc(_fmt_mld(valuation.point_estimate))}</div>
        <div class="sub" style="margin:2px 0 8px">pásmo {_esc(_fmt_mld(valuation.value_low))} – {_esc(_fmt_mld(valuation.value_high))}</div>
        <div>{_esc(_czech_dec(valuation.final_multiple, 2))}× EBITDA — základ Damodaran Europe {_esc(_czech_dec(valuation.base_multiple, 2))}× × korekce {_esc(_czech_dec(correction, 2))}</div>
        <div class="blurb">spolehlivost: {_esc(_CONFIDENCE_CZ.get(valuation.confidence, valuation.confidence))}</div>
      </div>
    """

    flags_html = (
        "<h2>Rizikové signály</h2>"
        "<div class='flag' style='background:#2f855a'>Žádné rizikové signály.</div>"
    )

    footer_html = (
        "<div class='foot'>Zdroj oborového násobku: Damodaran "
        f"{_esc(base.region)}, {_esc(base.source_industry)}, {_esc(base.firms)} firem, "
        f"k {_esc(base.as_of)} ({_esc(base.source_url)}). Není investiční doporučení.</div>"
    )

    scoped_style = _STYLE.replace("body{", ".card{", 1)
    style = _STAGE_STYLE + scoped_style

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{style}</style></head>
<body>
  <div class="card">
    <h1>{_esc(report.company_name)}</h1>
    <div class="sub">IČO {_esc(report.ico)} &middot; období {_esc(report.period_year)} &middot; v tis. Kč</div>
    <div class="sub">Zdroj: účetní závěrka {_esc(report.period_year)} (Sbírka listin)</div>
    {yearly_html}
    {ratios_html}
    {valuation_html}
    {flags_html}
    {footer_html}
  </div>
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=".showcase-card.html",
        help="Path to write the rendered HTML to (default: .showcase-card.html)",
    )
    args = parser.parse_args()
    html_out = render_card()
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
