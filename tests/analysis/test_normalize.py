from rejstrik.analysis.normalize import NormalizedFinancials, normalize
from rejstrik.documents.schema import Figure, FinancialStatement


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
