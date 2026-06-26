from rejstrik.documents.pick import pick_latest_financial_filing
from rejstrik.filings.models import Filing


def test_pick_returns_first_financial_statement():
    filings = [
        Filing(title="Účetní závěrka 2023", year=2023, pdf_url="https://x/a.pdf", is_financial_statement=True),
        Filing(title="Podpisový vzor", pdf_url="https://x/b.pdf", is_financial_statement=False),
    ]
    assert pick_latest_financial_filing(filings).year == 2023


def test_pick_returns_none_when_no_financial_statement():
    filings = [Filing(title="Podpisový vzor", pdf_url="https://x/b.pdf", is_financial_statement=False)]
    assert pick_latest_financial_filing(filings) is None
