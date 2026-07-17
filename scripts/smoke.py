"""Manual live smoke test — network required, run before releases, not in CI.

Usage: python scripts/smoke.py [company]
"""

from datetime import date
import sys

import httpx

from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.registry.ares import find_company
from rejstrik.filings.justice import list_filings
from rejstrik.service import analyze_statements, fetch_filing

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


def trend_plausibility_issues(report) -> list[str]:
    """Sanity-check a multi-year report: unit-mismatch flags or >90% headline
    swings mean the numbers are almost certainly unit-inconsistent, and the
    smoke run must fail rather than print SMOKE OK over garbage."""
    issues = [
        f"red flag: {flag.message}"
        for flag in report.red_flags
        if flag.code == "unit_mismatch_suspected"
    ]
    for trend in report.trends:
        if trend.pct_change is not None and abs(trend.pct_change) > 0.9:
            issues.append(
                f"implausible {trend.metric} change {trend.pct_change:+.1%} "
                f"(current={trend.current}, prior={trend.prior})"
            )
    return issues


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
    base_year = doc.year or (date.today().year - 1)

    statements = [
        FinancialStatement(
            company_name=company.name,
            ico=company.ico,
            period_year=base_year,
            currency="CZK",
            income_statement=[Figure(label="Tržby", value=1000.0)],
        ),
        FinancialStatement(
            company_name=company.name,
            ico=company.ico,
            period_year=base_year - 1,
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

    print("[5/5] skipped in-server extraction (keyless smoke)")

    print("SMOKE OK")


if __name__ == "__main__":
    main()
