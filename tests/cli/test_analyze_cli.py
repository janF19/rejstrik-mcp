from unittest.mock import patch

from typer.testing import CliRunner

from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import RedFlag
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.cli.main import app
from rejstrik.documents.schema import FinancialStatement

runner = CliRunner()

REPORT = CompanyFinancialReport(
    company_name="Test s.r.o.",
    ico="00006947",
    period_year=2023,
    currency="CZK",
    statement=FinancialStatement(),
    normalized=NormalizedFinancials(),
    ratios=Ratios(current_ratio=0.5, equity_ratio=0.4),
    red_flags=[
        RedFlag(
            code="low_liquidity",
            severity="warning",
            message="Current ratio below 1.",
        )
    ],
    source_filing_title="Účetní závěrka 2023",
)


def test_analyze_cli_prints_ratios_and_flags():
    with patch("rejstrik.cli.main.analyze_company_financials", return_value=REPORT):
        result = runner.invoke(app, ["analyze", "Test"])
    assert result.exit_code == 0
    assert "Test s.r.o." in result.stdout
    assert "current_ratio" in result.stdout
    assert "WARNING" in result.stdout
    assert "Current ratio below 1." in result.stdout


def test_analyze_cli_accepts_years_option():
    with patch(
        "rejstrik.cli.main.analyze_company_financials", return_value=REPORT
    ) as mock_analyze:
        result = runner.invoke(app, ["analyze", "Budvar", "--years", "3"])
    assert result.exit_code == 0
    mock_analyze.assert_called_once_with("Budvar", years=3)
