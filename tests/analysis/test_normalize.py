from rejstrik.analysis.normalize import NormalizedFinancials, normalize
from rejstrik.documents.schema import CanonicalFigures, Figure, FinancialStatement


def test_maps_czech_labels_to_fields():
    fs = FinancialStatement(
        period_year=2023,
        balance_sheet=[
            Figure(label="Aktiva celkem", value=1000.0),
            Figure(label="Vlastní kapitál", value=400.0),
            Figure(label="Oběžná aktiva", value=600.0),
            Figure(label="Krátkodobé závazky", value=300.0),
            Figure(label="Cizí zdroje", value=600.0),
        ],
        income_statement=[
            Figure(label="Tržby z prodeje výrobků a služeb", value=2000.0),
            Figure(label="Výsledek hospodaření za účetní období", value=150.0),
        ],
    )
    n = normalize(fs)
    assert isinstance(n, NormalizedFinancials)
    assert n.period_year == 2023
    assert n.total_assets == 1000.0
    assert n.equity == 400.0
    assert n.current_assets == 600.0
    assert n.current_liabilities == 300.0
    assert n.total_liabilities == 600.0
    assert n.revenue == 2000.0
    assert n.net_profit == 150.0


def test_missing_fields_stay_none():
    n = normalize(
        FinancialStatement(
            period_year=2022,
            balance_sheet=[Figure(label="Aktiva celkem", value=10.0)],
        )
    )
    assert n.total_assets == 10.0
    assert n.equity is None
    assert n.revenue is None


def test_english_labels_also_match():
    fs = FinancialStatement(
        balance_sheet=[Figure(label="Total assets", value=5.0)],
        income_statement=[Figure(label="Revenue", value=9.0)],
    )
    n = normalize(fs)
    assert n.total_assets == 5.0
    assert n.revenue == 9.0


def test_canonical_takes_precedence_over_keywords():
    fs = FinancialStatement(
        period_year=2023,
        canonical=CanonicalFigures(
            revenue=Figure(label="Tržby", value=999.0),
        ),
        income_statement=[Figure(label="Tržby z prodeje výrobků", value=2000.0)],
    )
    assert normalize(fs).revenue == 999.0


def test_fallback_ignores_asset_sale_revenue():
    fs = FinancialStatement(
        income_statement=[
            Figure(label="Tržby z prodeje dlouhodobého majetku a materiálu", value=5.0),
            Figure(label="Tržby z prodeje výrobků a služeb", value=2000.0),
        ]
    )
    assert normalize(fs).revenue == 2000.0


def test_fallback_separates_operating_and_net_result():
    fs = FinancialStatement(
        income_statement=[
            Figure(label="Provozní výsledek hospodaření", value=300.0),
            Figure(label="Výsledek hospodaření za účetní období", value=150.0),
        ]
    )
    n = normalize(fs)
    assert n.operating_profit == 300.0
    assert n.net_profit == 150.0


def test_fallback_bare_result_is_not_net_profit():
    fs = FinancialStatement(
        income_statement=[Figure(label="Provozní výsledek hospodaření", value=300.0)]
    )
    n = normalize(fs)
    assert n.operating_profit == 300.0
    assert n.net_profit is None


def test_fallback_maps_new_fields():
    fs = FinancialStatement(
        balance_sheet=[
            Figure(label="Zásoby", value=40.0),
            Figure(label="Krátkodobé pohledávky", value=60.0),
            Figure(label="Peněžní prostředky", value=25.0),
        ],
        income_statement=[Figure(label="Nákladové úroky", value=12.0)],
        cash_flow=[Figure(label="Čistý peněžní tok z provozní činnosti", value=180.0)],
    )
    n = normalize(fs)
    assert n.inventories == 40.0
    assert n.receivables == 60.0
    assert n.cash == 25.0
    assert n.interest_expense == 12.0
    assert n.operating_cash_flow == 180.0


def test_normalize_extracts_depreciation_amortization_from_canonical():
    from rejstrik.documents.schema import (
        CanonicalFigures,
        Figure,
        FinancialStatement,
    )
    from rejstrik.analysis.normalize import normalize

    stmt = FinancialStatement(
        period_year=2023,
        canonical=CanonicalFigures(
            depreciation_amortization=Figure(
                label="Úpravy hodnot v provozní oblasti", value=42.0
            )
        ),
    )
    assert normalize(stmt).depreciation_amortization == 42.0


def test_normalize_extracts_depreciation_from_income_statement_label():
    from rejstrik.documents.schema import Figure, FinancialStatement
    from rejstrik.analysis.normalize import normalize

    stmt = FinancialStatement(
        period_year=2023,
        income_statement=[Figure(label="Úpravy hodnot v provozní oblasti", value=17.0)],
    )
    assert normalize(stmt).depreciation_amortization == 17.0
