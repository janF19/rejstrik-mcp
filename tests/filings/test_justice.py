"""
Tests for rejstrik.filings.justice (or.justice.cz Sbírka listin parser).

IMPORTANT: These tests run against SYNTHETIC HTML fixtures because or.justice.cz
was under maintenance on 2026-06-25. Selectors must be re-verified against real
HTML when the service resumes.
"""

from pathlib import Path

import httpx
import respx

from rejstrik.filings.justice import parse_subject_id, parse_deeds, list_filings

FIXTURES = Path(__file__).parent.parent / "fixtures" / "justice"
SUBJECT_HTML = (FIXTURES / "subject_00006947.html").read_text(encoding="utf-8")
DEEDS_HTML = (FIXTURES / "deeds_00006947.html").read_text(encoding="utf-8")

_SEARCH_URL = "https://or.justice.cz/ias/ui/rejstrik-firma.vysledky"
_DEEDS_URL = "https://or.justice.cz/ias/ui/vypis-sl-firma"


def test_parse_subject_id_found():
    subject_id = parse_subject_id(SUBJECT_HTML)
    assert subject_id is not None
    assert subject_id.isdigit()


def test_parse_deeds_extracts_filings_with_absolute_urls():
    filings = parse_deeds(DEEDS_HTML)

    # Must have at least one filing
    assert len(filings) >= 1

    # All PDF URLs must be absolute https:// links
    for f in filings:
        assert f.pdf_url.startswith("https://"), (
            f"Expected absolute URL, got: {f.pdf_url}"
        )

    # At least one filing must be classified as a financial statement
    assert any(f.is_financial_statement for f in filings)

    # First filing must be a financial statement (sorted financial-first)
    assert filings[0].is_financial_statement is True


@respx.mock
def test_list_filings_orchestrates_lookup_and_deeds():
    subject_id = parse_subject_id(SUBJECT_HTML)
    assert subject_id is not None  # sanity

    respx.get(_SEARCH_URL, params={"ico": "00006947"}).mock(
        return_value=httpx.Response(200, text=SUBJECT_HTML)
    )
    respx.get(_DEEDS_URL, params={"subjektId": subject_id}).mock(
        return_value=httpx.Response(200, text=DEEDS_HTML)
    )

    client = httpx.Client()
    filings = list_filings("00006947", client=client)
    client.close()

    assert len(filings) >= 1
