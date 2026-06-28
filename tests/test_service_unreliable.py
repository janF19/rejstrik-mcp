from unittest.mock import patch

import rejstrik.service as service
from rejstrik.documents.schema import Figure, FinancialStatement
from rejstrik.documents.source import PdfSource
from rejstrik.filings.models import Filing
from rejstrik.registry.isir import InsolvencyStatus
from rejstrik.registry.models import Company
from rejstrik.registry.vat import VatStatus

COMPANY = Company(ico="00006947", name="Test s.r.o.")
FILINGS = [
    Filing(
        title="Ucetni zaverka 2023",
        year=2023,
        pdf_url="https://x/a.pdf",
        is_financial_statement=True,
    )
]
SRC = PdfSource(data=b"%PDF x", sha256="x", filename="f.pdf")
STATEMENT = FinancialStatement(
    ico="00006947",
    period_year=2023,
    balance_sheet=[Figure(label="Aktiva celkem", value=10.0)],
)


def test_unreliable_payer_becomes_red_flag():
    def clean_isir(ico: str) -> InsolvencyStatus:
        return InsolvencyStatus(ico=ico, in_insolvency=False, cases=[], checked=True)

    def unreliable_vat(ico: str) -> VatStatus:
        return VatStatus(
            ico=ico, dic="CZ00006947", is_vat_payer=True, is_unreliable=True
        )

    with (
        patch.object(service, "find_company", return_value=COMPANY),
        patch.object(service, "list_filings", return_value=FILINGS),
        patch.object(service, "load_pdf", return_value=SRC),
        patch.object(service, "extract_financials", return_value=STATEMENT),
    ):
        report = service.analyze_company_financials(
            "Test", insolvency_check=clean_isir, vat_check=unreliable_vat
        )
    assert any(f.code == "unreliable_vat" for f in report.red_flags)
