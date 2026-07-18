import typer

from rejstrik.filings.justice import list_filings
from rejstrik.registry.ares import CompanyNotFound, find_company
from rejstrik.registry.contracts import get_contracts
from rejstrik.registry.subsidies import get_subsidies

app = typer.Typer(help="Czech registry MCP that reads the documents — CLI")


@app.command()
def find(query: str) -> None:
    """Resolve a company by name or IČO via ARES."""
    try:
        company = find_company(query)
    except CompanyNotFound as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    typer.echo(f"{company.ico}  {company.name}  {company.address or ''}".rstrip())


@app.command()
def filings(
    ico: str, financial_only: bool = typer.Option(False, "--financial-only")
) -> None:
    """List Sbírka listin documents for a company."""
    items = list_filings(ico)
    if financial_only:
        items = [f for f in items if f.is_financial_statement]
    if not items:
        typer.echo("No filings found.")
        return
    for f in items:
        marker = "[FS] " if f.is_financial_statement else "     "
        year = str(f.year) if f.year else "----"
        typer.echo(f"{marker}{year}  {f.title}  {f.pdf_url}")


@app.command()
def subsidies(ico: str) -> None:
    """List state subsidies received by a company (IS ReD / former CEDR)."""
    report = get_subsidies(ico)
    typer.echo(
        f"{report.recipient_name or '?'}  total: {report.total_amount}  "
        f"({report.count} subsidies)"
    )
    for s in report.subsidies:
        typer.echo(f"  {s.project_name or '?'}: {s.amount}")


@app.command()
def contracts(ico: str) -> None:
    """List public contracts involving a company (Registr smluv)."""
    report = get_contracts(ico)
    typer.echo(f"{report.count} contracts  total: {report.total_value}")
    for c in report.contracts:
        typer.echo(f"  {c.subject or '?'}: {c.value}")
