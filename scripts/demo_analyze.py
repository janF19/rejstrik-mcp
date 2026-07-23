#!/usr/bin/env python3
"""Demo of the actual MCP flow: an agent finds a company, fetches its filed
financial statement, reads the PDF pages, and calls analyze_financials with
the figures it extracted. Recorded by record_demo.sh for the README GIF.

The figures below were read by Claude from the real filed PDF (ROBE lighting
s.r.o., účetní závěrka 2023, verejnerejstriky.msp.gov.cz) — this script
replays that extraction step so the analysis half of the flow is live.
"""

import logging
import time

from rejstrik.documents.schema import CanonicalFigures, FinancialStatement, Figure
from rejstrik.filings.justice import list_filings
from rejstrik.mcp.card import render_report_markdown
from rejstrik.mcp.server import analyze_financials
from rejstrik.registry.ares import find_company

logging.getLogger("httpx").setLevel(logging.WARNING)


def step(label: str) -> None:
    print(f"\n\033[36m▸ {label}\033[0m")
    time.sleep(0.4)


step('find_company("ROBE lighting")')
company = find_company("ROBE lighting")
print(f"  {company.name}  ·  IČO {company.ico}  ·  {company.address}")

step(f"list_filings({company.ico})")
filings = list_filings(company.ico)
filing = next(f for f in filings if f.pdf_url.endswith("105512283"))
print(f"  {filing.title}")

step("get_filing + read_filing_page_images — agent reads the scanned PDF")
print("  pages 9-13: Rozvaha, Pasiva, Výkaz zisku a ztráty")
print("  → figures extracted from the images (v tisících Kč):")
figures = {
    "Aktiva celkem": 3_541_478,
    "Vlastní kapitál": 3_039_871,
    "Cizí zdroje": 499_199,
    "Tržby": 3_886_882,
    "Provozní výsledek hospodaření": 903_044,
    "Výsledek hospodaření za účetní období": 752_222,
}
for label, value in figures.items():
    print(f"    {label:<40} {value:>12,}".replace(",", " "))

step('analyze_financials(statements=[...], ico="64088791")')
canon = CanonicalFigures(
    total_assets=Figure(label="Aktiva celkem", value=3_541_478),
    current_assets=Figure(label="Oběžná aktiva", value=2_415_279),
    equity=Figure(label="Vlastní kapitál", value=3_039_871),
    total_liabilities=Figure(label="Cizí zdroje", value=499_199),
    current_liabilities=Figure(label="Krátkodobé závazky", value=382_436),
    revenue=Figure(label="Tržby z prodeje výrobků, služeb a zboží", value=3_886_882),
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
statement = FinancialStatement(
    company_name=company.name,
    ico=company.ico,
    period_year=2023,
    unit="thousands_czk",
    canonical=canon,
)
report = analyze_financials([statement], ico=company.ico)

step("render_report_markdown(report)")
print()
print(render_report_markdown(report))
