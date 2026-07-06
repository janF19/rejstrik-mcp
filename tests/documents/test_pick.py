from rejstrik.documents.pick import pick_financial_filing, pick_latest_financial_filing
from rejstrik.filings.models import Filing


def test_pick_returns_first_financial_statement():
    filings = [
        Filing(
            title="Účetní závěrka 2023",
            year=2023,
            pdf_url="https://x/a.pdf",
            is_financial_statement=True,
        ),
        Filing(
            title="Podpisový vzor",
            pdf_url="https://x/b.pdf",
            is_financial_statement=False,
        ),
    ]
    assert pick_latest_financial_filing(filings).year == 2023


def test_pick_returns_none_when_no_financial_statement():
    filings = [
        Filing(
            title="Podpisový vzor",
            pdf_url="https://x/b.pdf",
            is_financial_statement=False,
        )
    ]
    assert pick_latest_financial_filing(filings) is None


def _fin(year, doc_id):
    return Filing(
        title=f"ucetni zaverka {year}",
        year=year,
        pdf_url=f"https://verejnerejstriky.msp.gov.cz/dokumenty/sbirka-listin/{doc_id}",
        is_financial_statement=True,
    )


def test_pick_financial_filing_default_latest():
    filings = [_fin(2024, "aaa"), _fin(2023, "bbb")]
    assert pick_financial_filing(filings).year == 2024


def test_pick_financial_filing_by_year():
    filings = [_fin(2024, "aaa"), _fin(2023, "bbb")]
    assert pick_financial_filing(filings, year=2023).pdf_url.endswith("bbb")


def test_pick_financial_filing_by_year_missing_returns_none():
    assert pick_financial_filing([_fin(2024, "aaa")], year=2019) is None


def test_pick_financial_filing_by_filing_id_substring():
    filings = [_fin(2024, "aaa"), _fin(2023, "bbb")]
    assert pick_financial_filing(filings, filing_id="bbb").year == 2023


def test_pick_financial_filing_by_filing_id_ignores_year_filter():
    non_fin = Filing(title="zprava", year=2022, pdf_url="https://x/ccc")
    assert pick_financial_filing([non_fin], filing_id="ccc") is non_fin
