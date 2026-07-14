import pytest
from pydantic import ValidationError

from rejstrik.documents.schema import Figure, NoteItem, FinancialStatement


def test_figure_optional_fields():
    f = Figure(label="Revenue")
    assert f.value is None
    assert f.source_page is None


def test_financial_statement_round_trip():
    fs = FinancialStatement(
        company_name="Test s.r.o.",
        ico="00006947",
        period_year=2023,
        currency="CZK",
        balance_sheet=[Figure(label="Total assets", value=1000.0, source_page=12)],
        income_statement=[Figure(label="Revenue", value=500.0, source_page=14)],
        cash_flow=[],
        notes=[
            NoteItem(
                topic="Related parties", summary="Loan to director", source_page=43
            )
        ],
    )
    dumped = fs.model_dump()
    restored = FinancialStatement(**dumped)
    assert restored.balance_sheet[0].source_page == 12
    assert restored.notes[0].topic == "Related parties"


def test_financial_statement_defaults_empty_lists():
    fs = FinancialStatement()
    assert fs.balance_sheet == []
    assert fs.notes == []


def test_canonical_figures_default_none_and_round_trip():
    from rejstrik.documents.schema import CanonicalFigures

    fs = FinancialStatement()
    assert fs.canonical is None

    fs2 = FinancialStatement(
        canonical=CanonicalFigures(
            total_assets=Figure(label="Aktiva celkem", value=1000.0, source_page=3),
            net_profit=Figure(label="VH za účetní období", value=120.0),
        )
    )
    restored = FinancialStatement(**fs2.model_dump())
    assert restored.canonical.total_assets.value == 1000.0
    assert restored.canonical.total_assets.source_page == 3
    assert restored.canonical.equity is None


def test_canonical_schema_names_czech_lines():
    schema = FinancialStatement.model_json_schema()
    dumped = str(schema)
    assert "Aktiva celkem" in dumped
    assert "nákladové úroky" in dumped


def test_statement_unit_accepts_known_scales():
    assert FinancialStatement(unit="thousands_czk").unit == "thousands_czk"
    assert FinancialStatement(unit="czk").unit == "czk"
    assert FinancialStatement(unit="millions_czk").unit == "millions_czk"
    assert FinancialStatement().unit is None


def test_statement_unit_rejects_unknown_scale():
    with pytest.raises(ValidationError):
        FinancialStatement(unit="bushels")
