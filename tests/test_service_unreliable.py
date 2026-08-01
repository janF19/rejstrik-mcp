from rejstrik import service
from rejstrik.documents.schema import Figure, FinancialStatement
from rejstrik.registry.isir import InsolvencyStatus
from rejstrik.registry.vat import VatStatus

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

    report = service.analyze_statements(
        [STATEMENT], insolvency_check=clean_isir, vat_check=unreliable_vat
    )
    assert any(f.code == "unreliable_vat" for f in report.red_flags)
