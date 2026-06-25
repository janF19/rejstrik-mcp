from unittest.mock import patch

from typer.testing import CliRunner

from rejstrik.cli.main import app
from rejstrik.registry.models import Company
from rejstrik.filings.models import Filing

runner = CliRunner()


def test_find_prints_company():
    company = Company(ico="00006947", name="Test s.r.o.", address="Praha")
    with patch("rejstrik.cli.main.find_company", return_value=company):
        result = runner.invoke(app, ["find", "Test"])
    assert result.exit_code == 0
    assert "00006947" in result.stdout
    assert "Test s.r.o." in result.stdout


def test_filings_financial_only_filters():
    filings = [
        Filing(title="Účetní závěrka 2023", year=2023, pdf_url="https://x/a.pdf", is_financial_statement=True),
        Filing(title="Podpisový vzor", pdf_url="https://x/b.pdf", is_financial_statement=False),
    ]
    with patch("rejstrik.cli.main.list_filings", return_value=filings):
        result = runner.invoke(app, ["filings", "00006947", "--financial-only"])
    assert result.exit_code == 0
    assert "Účetní závěrka 2023" in result.stdout
    assert "Podpisový vzor" not in result.stdout
