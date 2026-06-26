from unittest.mock import patch

from typer.testing import CliRunner

from rejstrik.cli.main import app
from rejstrik.documents.answer import Answer, Citation
from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.documents.source import PdfSource
from rejstrik.filings.models import Filing
from rejstrik.registry.models import Company

runner = CliRunner()

FILINGS = [Filing(title="Účetní závěrka 2023", year=2023, pdf_url="https://x/a.pdf", is_financial_statement=True)]
SRC = PdfSource(data=b"%PDF x", sha256="x", filename="f.pdf")


def test_extract_cli_prints_figures_with_pages():
    company = Company(ico="00006947", name="Test s.r.o.")
    fs = FinancialStatement(company_name="Test s.r.o.", period_year=2023,
                            balance_sheet=[Figure(label="Total assets", value=1000.0, source_page=12)])
    with patch("rejstrik.cli.main.find_company", return_value=company), \
         patch("rejstrik.cli.main.list_filings", return_value=FILINGS), \
         patch("rejstrik.cli.main.load_pdf", return_value=SRC), \
         patch("rejstrik.cli.main.extract_financials", return_value=fs):
        result = runner.invoke(app, ["extract", "00006947"])
    assert result.exit_code == 0
    assert "Total assets" in result.stdout
    assert "12" in result.stdout


def test_ask_cli_prints_answer_and_sources():
    company = Company(ico="00006947", name="Test s.r.o.")
    ans = Answer(text="A pledge exists.", citations=[Citation(cited_text="zástavní právo", page=43)])
    with patch("rejstrik.cli.main.find_company", return_value=company), \
         patch("rejstrik.cli.main.list_filings", return_value=FILINGS), \
         patch("rejstrik.cli.main.load_pdf", return_value=SRC), \
         patch("rejstrik.cli.main.ask_filing", return_value=ans):
        result = runner.invoke(app, ["ask", "00006947", "Are there pledges?"])
    assert result.exit_code == 0
    assert "A pledge exists." in result.stdout
    assert "43" in result.stdout
