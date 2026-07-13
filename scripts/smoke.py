"""Manual live smoke test — network required, run before releases, not in CI.

Usage: python scripts/smoke.py [company]
"""

import sys

import httpx

from rejstrik.documents.config import has_llm_key
from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.registry.ares import find_company
from rejstrik.filings.justice import list_filings
from rejstrik.service import (
    analyze_company_financials,
    analyze_statements,
    fetch_filing,
)

_CANARY_ENDPOINTS = {
    "new API (verejnerejstriky.msp.gov.cz)": (
        "https://verejnerejstriky.msp.gov.cz/api/sbirka-listin/subjekty/514152"
    ),
    "legacy portal (or.justice.cz)": (
        "https://or.justice.cz/ias/ui/rejstrik-$firma?ico=00514152"
    ),
}


def canary() -> None:
    """Hit both Sbirka listin portals directly and print PASS/BLOCKED per endpoint."""
    for name, url in _CANARY_ENDPOINTS.items():
        try:
            resp = httpx.get(url, timeout=10.0, follow_redirects=True)
            status = "PASS" if resp.status_code < 400 else "BLOCKED"
            print(f"[canary] {status} {name}: HTTP {resp.status_code}")
        except httpx.HTTPError as exc:
            print(f"[canary] BLOCKED {name}: {exc!r}")


def main() -> None:
    canary()
    query = sys.argv[1] if len(sys.argv) > 1 else "Budejovicky Budvar"
    company = find_company(query)
    print(f"[1/5] find_company: {company.name} ({company.ico})")

    filings = [f for f in list_filings(company.ico) if f.is_financial_statement]
    print(f"[2/5] list_filings: {len(filings)} financial statements")

    doc, _source = fetch_filing(company.ico)
    print(
        f"[3/5] get_filing: {doc.title} ({doc.year}) -> {doc.file_path} "
        f"({doc.size_bytes} bytes)"
    )

    statements = [
        FinancialStatement(
            company_name=company.name,
            ico=company.ico,
            period_year=2024,
            currency="CZK",
            income_statement=[Figure(label="Tržby", value=1000.0)],
        ),
        FinancialStatement(
            company_name=company.name,
            ico=company.ico,
            period_year=2023,
            currency="CZK",
            income_statement=[Figure(label="Tržby", value=800.0)],
        ),
    ]
    report = analyze_statements(statements, ico=company.ico)
    print(
        f"[4/5] analyze_statements: {len(report.red_flags)} red flags, "
        f"{len(report.trends)} trend metrics (registry checks live)"
    )
    assert report.trends, "trends must be computed for 2 statements"

    if has_llm_key():
        multi_year_report = analyze_company_financials(company.ico, years=2)
        print(
            f"[5/5] analyze_company_financials(years=2): "
            f"{len(multi_year_report.trends)} trend metrics"
        )
        assert multi_year_report.trends, "trends must be computed for years=2"
        for trend in multi_year_report.trends:
            print(f"    {trend}")
    else:
        print("[5/5] skipped multi-year analyze_company_financials (no LLM key set)")

    print("SMOKE OK")


if __name__ == "__main__":
    main()
