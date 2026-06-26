import typer

from rejstrik.registry.ares import find_company, CompanyNotFound
from rejstrik.filings.justice import list_filings
from rejstrik.documents.source import load_pdf
from rejstrik.documents.extract import extract_financials
from rejstrik.documents.ask import ask_filing
from rejstrik.documents.pick import pick_latest_financial_filing

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


def _load_latest_statement(ico: str):
    """Resolve -> list -> pick -> download. Returns (company, PdfSource) or exits."""
    company = find_company(ico)
    filing = pick_latest_financial_filing(list_filings(company.ico))
    if filing is None:
        typer.echo("No financial statement found in Sbírka listin.", err=True)
        raise typer.Exit(1)
    return company, load_pdf(filing)


@app.command()
def extract(ico: str) -> None:
    """Extract structured financials from the latest financial statement."""
    company, source = _load_latest_statement(ico)
    fs = extract_financials(source)
    typer.echo(f"{company.name}  ({fs.period_year or '----'})")
    for fig in [*fs.balance_sheet, *fs.income_statement]:
        page = f"(p.{fig.source_page})" if fig.source_page else ""
        value = fig.value if fig.value is not None else "-"
        typer.echo(f"  {fig.label}: {value}  {page}".rstrip())


@app.command()
def ask(ico: str, question: str) -> None:
    """Ask a free-form question about the latest financial statement, with citations."""
    _company, source = _load_latest_statement(ico)
    answer = ask_filing(source, question)
    typer.echo(answer.text)
    if answer.citations:
        typer.echo("\nSources:")
        for c in answer.citations:
            page = f"(p.{c.page})" if c.page else ""
            typer.echo(f"  - {c.cited_text} {page}".rstrip())
