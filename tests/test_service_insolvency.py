import rejstrik.service as service
from rejstrik.documents.schema import Figure, FinancialStatement
from rejstrik.registry.isir import InsolvencyStatus
from rejstrik.registry.vat import VatStatus

STATEMENT = FinancialStatement(
    ico="00006947",
    period_year=2023,
    balance_sheet=[Figure(label="Aktiva celkem", value=10.0)],
)


def test_insolvent_company_gets_insolvency_red_flag():
    def insolvent(ico: str) -> InsolvencyStatus:
        return InsolvencyStatus(ico=ico, in_insolvency=True, cases=[], checked=True)

    report = service.analyze_statements(
        [STATEMENT],
        insolvency_check=insolvent,
        vat_check=lambda ico: VatStatus(ico=ico, is_vat_payer=False),
    )
    assert any(flag.code == "insolvency" for flag in report.red_flags)


def test_unknown_insolvency_adds_no_flag():
    def unknown(ico: str) -> InsolvencyStatus:
        return InsolvencyStatus(ico=ico, in_insolvency=False, cases=[], checked=False)

    report = service.analyze_statements(
        [STATEMENT],
        insolvency_check=unknown,
        vat_check=lambda ico: VatStatus(ico=ico, is_vat_payer=False),
    )
    assert not any(flag.code == "insolvency" for flag in report.red_flags)
