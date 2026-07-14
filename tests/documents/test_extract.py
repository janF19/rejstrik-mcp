from rejstrik.documents.extract import extract_financials, EXTRACT_INSTRUCTIONS
from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.documents.source import PdfSource

SRC = PdfSource(data=b"%PDF x", sha256="x", filename="f.pdf")


class FakeLLM:
    def __init__(self):
        self.calls = []

    def extract(self, source, schema, instructions):
        self.calls.append((source, schema, instructions))
        return schema(
            company_name="Fake s.r.o.",
            balance_sheet=[Figure(label="Total assets", value=1.0, source_page=3)],
        )

    def ask(self, source, question):
        raise NotImplementedError


def test_extract_financials_delegates_to_llm_with_schema_and_instructions():
    fake = FakeLLM()
    result = extract_financials(SRC, llm=fake)
    assert isinstance(result, FinancialStatement)
    assert result.company_name == "Fake s.r.o."
    src, schema, instructions = fake.calls[0]
    assert src is SRC
    assert schema is FinancialStatement
    assert instructions == EXTRACT_INSTRUCTIONS


def test_extract_instructions_mention_czech_statements_and_pages():
    low = EXTRACT_INSTRUCTIONS.lower()
    assert "rozvaha" in low
    assert "page" in low


def test_extract_instructions_demand_verbatim_figures_and_unit():
    low = EXTRACT_INSTRUCTIONS.lower()
    assert "verbatim" in low
    assert "`unit`" in EXTRACT_INSTRUCTIONS
    assert "thousands_czk" in EXTRACT_INSTRUCTIONS
    assert "tisících" in EXTRACT_INSTRUCTIONS
