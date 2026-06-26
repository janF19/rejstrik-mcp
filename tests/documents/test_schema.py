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
        notes=[NoteItem(topic="Related parties", summary="Loan to director", source_page=43)],
    )
    dumped = fs.model_dump()
    restored = FinancialStatement(**dumped)
    assert restored.balance_sheet[0].source_page == 12
    assert restored.notes[0].topic == "Related parties"


def test_financial_statement_defaults_empty_lists():
    fs = FinancialStatement()
    assert fs.balance_sheet == []
    assert fs.notes == []
