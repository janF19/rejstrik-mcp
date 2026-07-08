from unittest.mock import patch

from typer.testing import CliRunner

from rejstrik.cli.main import app
from rejstrik.registry.contracts import Contract, ContractReport
from rejstrik.registry.subsidies import Subsidy, SubsidyReport

runner = CliRunner()


def test_subsidies_cli_prints_recipient_and_total():
    report = SubsidyReport(
        ico="00006947",
        recipient_name="Test s.r.o.",
        total_amount=1234.0,
        count=1,
        subsidies=[Subsidy(project_name="Project X", amount=1234.0)],
    )
    with patch("rejstrik.cli.main.get_subsidies", return_value=report):
        result = runner.invoke(app, ["subsidies", "00006947"])
    assert result.exit_code == 0
    assert "Test s.r.o." in result.stdout
    assert "1234" in result.stdout


def test_contracts_cli_prints_count_and_total():
    report = ContractReport(
        ico="00006947",
        count=1,
        total_value=5000.0,
        contracts=[Contract(subject="Supply contract", value=5000.0)],
    )
    with patch("rejstrik.cli.main.get_contracts", return_value=report):
        result = runner.invoke(app, ["contracts", "00006947"])
    assert result.exit_code == 0
    assert "1" in result.stdout
    assert "5000" in result.stdout
