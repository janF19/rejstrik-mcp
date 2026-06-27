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

_NEW_FILINGS_URL = "https://verejnerejstriky.msp.gov.cz/api/sbirka-listin/subjekty/514152"


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
def test_list_filings_uses_new_sbirka_listin_api():
    respx.get(_NEW_FILINGS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "OK",
                "vysledekdetail": {
                    "prehledlistin": [
                        {
                            "cislolistiny": "AV 325/SL92/KSCB",
                            "typlistiny": "ostatní odvolání z funkce člena dozorčí rady",
                            "zalozenodosl": "09-01-2025",
                            "digitalizovan": 1,
                            "detail": [
                                {
                                    "obsah": {
                                        "digitalnipodoba": {
                                            "pocetstran": 2,
                                            "documentid": "102856505",
                                        }
                                    }
                                }
                            ],
                        },
                        {
                            "cislolistiny": "AV 325/SL93/KSCB",
                            "typlistiny": "účetní závěrka [2024], výroční zpráva [2024], zpráva auditora [2024]",
                            "zalozenodosl": "01-07-2025",
                            "digitalizovan": 1,
                            "detail": [
                                {
                                    "obsah": {
                                        "digitalnipodoba": {
                                            "pocetstran": 40,
                                            "documentid": "107465869",
                                        }
                                    }
                                }
                            ],
                        },
                    ]
                },
            },
        )
    )

    client = httpx.Client()
    filings = list_filings("00514152", client=client)
    client.close()

    assert len(filings) == 2
    assert filings[0].title == (
        "účetní závěrka [2024], výroční zpráva [2024], zpráva auditora [2024]"
    )
    assert filings[0].year == 2024
    assert filings[0].is_financial_statement is True
    assert filings[0].pdf_url == (
        "https://verejnerejstriky.msp.gov.cz/dokumenty/sbirka-listin/107465869"
    )
