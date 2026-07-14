"""
Tests for rejstrik.filings.justice (or.justice.cz Sbírka listin parser).

Fixtures are REAL HTML captured live on 2026-07-13 against IČO 00514152
(Budějovický Budvar, subjektId 59981) — see
docs/superpowers/plans/2026-07-13-stage-a-implementation.md for the
live-investigation notes.
"""

from pathlib import Path

import httpx
import pytest
import respx

from rejstrik.filings.justice import (
    RegistryBlockedError,
    parse_download_link,
    parse_subject_id,
    parse_deeds,
    list_filings,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "justice"
SEARCH_HTML = (FIXTURES / "legacy_search_00514152.html").read_text(encoding="utf-8")
DEEDS_HTML = (FIXTURES / "legacy_deeds_00514152.html").read_text(encoding="utf-8")
DETAIL_HTML = (FIXTURES / "legacy_detail_87101138.html").read_text(encoding="utf-8")
BLOCK_HTML = (FIXTURES / "new_api_block_403.html").read_text(encoding="utf-8")

_NEW_FILINGS_URL = (
    "https://verejnerejstriky.msp.gov.cz/api/sbirka-listin/subjekty/514152"
)
_LEGACY_SEARCH_URL = "https://or.justice.cz/ias/ui/rejstrik-$firma?ico=00514152"
_LEGACY_DEEDS_URL = "https://or.justice.cz/ias/ui/vypis-sl-firma?subjektId=59981"


def test_parse_subject_id_found():
    subject_id = parse_subject_id(SEARCH_HTML)
    assert subject_id == "59981"


def test_parse_deeds_extracts_filings_with_absolute_urls():
    filings = parse_deeds(DEEDS_HTML)

    assert len(filings) >= 90

    for f in filings:
        assert f.pdf_url.startswith(
            "https://or.justice.cz/ias/ui/vypis-sl-detail?dokument="
        ), f"Expected absolute legacy detail URL, got: {f.pdf_url}"

    assert any(f.is_financial_statement for f in filings)
    assert filings[0].is_financial_statement is True


def test_parse_deeds_joins_multi_type_title_and_extracts_year():
    filings = parse_deeds(DEEDS_HTML)
    by_dokument = {f.pdf_url.split("dokument=")[1].split("&")[0]: f for f in filings}

    combo = by_dokument["87101138"]
    assert combo.title == (
        "účetní závěrka [2024], výroční zpráva [2024], zpráva auditora [2024]"
    )
    assert combo.year == 2024
    assert combo.is_financial_statement is True
    assert combo.pdf_url == (
        "https://or.justice.cz/ias/ui/vypis-sl-detail"
        "?dokument=87101138&subjektId=59981&spis=411891"
    )


def test_parse_deeds_sorts_financial_first_year_desc():
    filings = parse_deeds(DEEDS_HTML)
    financial = [f for f in filings if f.is_financial_statement]
    non_financial_start = filings.index(financial[-1]) + 1
    # every non-financial filing appears after the last financial one
    assert all(not f.is_financial_statement for f in filings[non_financial_start:])
    years = [f.year for f in financial if f.year is not None]
    assert years == sorted(years, reverse=True)


def test_parse_download_link_extracts_absolute_url():
    link = parse_download_link(DETAIL_HTML, base_url="https://or.justice.cz")
    assert link is not None
    assert link.startswith("https://or.justice.cz/ias/content/download?id=")


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


@respx.mock
def test_list_filings_falls_back_to_legacy_portal_on_403():
    respx.get(_NEW_FILINGS_URL).mock(return_value=httpx.Response(403, text=BLOCK_HTML))
    respx.get(_LEGACY_SEARCH_URL).mock(
        return_value=httpx.Response(200, text=SEARCH_HTML)
    )
    respx.get(_LEGACY_DEEDS_URL).mock(return_value=httpx.Response(200, text=DEEDS_HTML))

    client = httpx.Client()
    filings = list_filings("00514152", client=client)
    client.close()

    assert len(filings) >= 90
    assert filings[0].is_financial_statement is True
    assert filings[0].pdf_url.startswith(
        "https://or.justice.cz/ias/ui/vypis-sl-detail?dokument="
    )


@respx.mock
def test_list_filings_does_not_fall_back_on_404():
    respx.get(_NEW_FILINGS_URL).mock(return_value=httpx.Response(404, text="not found"))

    client = httpx.Client()
    try:
        with pytest.raises(httpx.HTTPStatusError):
            list_filings("00514152", client=client)
    finally:
        client.close()


@respx.mock
def test_list_filings_raises_registry_blocked_when_both_portals_fail():
    respx.get(_NEW_FILINGS_URL).mock(return_value=httpx.Response(403, text=BLOCK_HTML))
    respx.get(_LEGACY_SEARCH_URL).mock(
        return_value=httpx.Response(200, text="<html><body>no results</body></html>")
    )

    client = httpx.Client()
    try:
        with pytest.raises(RegistryBlockedError) as exc_info:
            list_filings("00514152", client=client)
    finally:
        client.close()

    message = str(exc_info.value)
    assert "verejnerejstriky.msp.gov.cz" in message
    assert "or.justice.cz" in message
    assert "https://or.justice.cz/ias/ui/rejstrik-$firma?ico=00514152" in message


@respx.mock
def test_list_filings_falls_back_on_429():
    respx.get(_NEW_FILINGS_URL).mock(return_value=httpx.Response(429, text="slow down"))
    respx.get(_LEGACY_SEARCH_URL).mock(
        return_value=httpx.Response(200, text=SEARCH_HTML)
    )
    respx.get(_LEGACY_DEEDS_URL).mock(return_value=httpx.Response(200, text=DEEDS_HTML))

    client = httpx.Client()
    filings = list_filings("00514152", client=client)
    client.close()

    assert len(filings) >= 90
    assert filings[0].pdf_url.startswith(
        "https://or.justice.cz/ias/ui/vypis-sl-detail?dokument="
    )


@respx.mock
def test_list_filings_falls_back_on_503():
    respx.get(_NEW_FILINGS_URL).mock(
        return_value=httpx.Response(503, text="unavailable")
    )
    respx.get(_LEGACY_SEARCH_URL).mock(
        return_value=httpx.Response(200, text=SEARCH_HTML)
    )
    respx.get(_LEGACY_DEEDS_URL).mock(return_value=httpx.Response(200, text=DEEDS_HTML))

    client = httpx.Client()
    filings = list_filings("00514152", client=client)
    client.close()

    assert len(filings) >= 90


@respx.mock
def test_list_filings_falls_back_on_challenge_html_200():
    # Azure Front Door interstitial: HTTP 200 but an HTML challenge body, not JSON.
    respx.get(_NEW_FILINGS_URL).mock(
        return_value=httpx.Response(
            200,
            html="<html><body>Checking your browser…</body></html>",
        )
    )
    respx.get(_LEGACY_SEARCH_URL).mock(
        return_value=httpx.Response(200, text=SEARCH_HTML)
    )
    respx.get(_LEGACY_DEEDS_URL).mock(return_value=httpx.Response(200, text=DEEDS_HTML))

    client = httpx.Client()
    filings = list_filings("00514152", client=client)
    client.close()

    assert len(filings) >= 90


@respx.mock
def test_list_filings_does_not_fall_back_on_timeout():
    respx.get(_NEW_FILINGS_URL).mock(side_effect=httpx.ConnectTimeout("boom"))

    client = httpx.Client()
    try:
        with pytest.raises(httpx.ConnectTimeout):
            list_filings("00514152", client=client)
    finally:
        client.close()


@respx.mock
def test_registry_blocked_message_names_non_json_trigger():
    respx.get(_NEW_FILINGS_URL).mock(
        return_value=httpx.Response(
            200, html="<html><body>Checking your browser…</body></html>"
        )
    )
    respx.get(_LEGACY_SEARCH_URL).mock(
        return_value=httpx.Response(200, text="<html><body>no results</body></html>")
    )

    client = httpx.Client()
    try:
        with pytest.raises(RegistryBlockedError) as exc_info:
            list_filings("00514152", client=client)
    finally:
        client.close()

    assert "non-JSON response" in str(exc_info.value)


def test_parse_filings_api_split_year_title_takes_max_year():
    from rejstrik.filings.justice import parse_filings_api

    data = {
        "vysledekdetail": {
            "prehledlistin": [
                {
                    "typlistiny": "účetní závěrka 2023/2024",
                    "detail": [
                        {"obsah": {"digitalnipodoba": {"documentid": "111222333"}}}
                    ],
                }
            ]
        }
    }

    filings = parse_filings_api(data)
    assert len(filings) == 1
    # The accounting period ends in the later year — take 2024, not 2023.
    assert filings[0].year == 2024
