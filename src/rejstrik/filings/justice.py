"""Client and legacy parsers for Sbírka listin commercial registry filings."""

from __future__ import annotations

import logging
import re

import httpx
from selectolax.parser import HTMLParser

from rejstrik.core.http import make_client
from rejstrik.filings.models import Filing, classify_financial

_BASE_URL = "https://or.justice.cz"
_NEW_BASE_URL = "https://verejnerejstriky.msp.gov.cz"
_NEW_FILINGS_URL = _NEW_BASE_URL + "/api/sbirka-listin/subjekty/{ico}"
_NEW_DOCUMENT_URL = _NEW_BASE_URL + "/dokumenty/sbirka-listin/{document_id}"

_SUBJECT_ID_RE = re.compile(r"subjektId=(\d+)")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def parse_subject_id(html: str) -> str | None:
    """Return the first subjektId value found in any href in *html*, or None."""
    tree = HTMLParser(html)
    for node in tree.css("a[href]"):
        href = node.attributes.get("href", "") or ""
        m = _SUBJECT_ID_RE.search(href)
        if m:
            return m.group(1)
    return None


def parse_deeds(html: str, base_url: str = _BASE_URL) -> list[Filing]:
    """
    Parse the Sbírka listin page and return a sorted list of Filing objects.

    Sorting: financial statements first, then by year descending (None last).
    """
    tree = HTMLParser(html)
    filings: list[Filing] = []

    for row in tree.css("div.document-row"):
        title_node = row.css_first("span.document-title")
        link_node = row.css_first("a[href]")
        if title_node is None or link_node is None:
            continue

        title = (title_node.text(strip=True) or "").strip()
        href = (link_node.attributes.get("href") or "").strip()
        if not title or not href:
            continue

        # Resolve relative URLs
        if href.startswith("/"):
            pdf_url = base_url.rstrip("/") + href
        elif href.startswith("http"):
            pdf_url = href
        else:
            pdf_url = base_url.rstrip("/") + "/" + href

        # Extract year from title
        year_m = _YEAR_RE.search(title)
        year = int(year_m.group(0)) if year_m else None

        is_fin = classify_financial(title)
        filings.append(
            Filing(
                title=title, year=year, pdf_url=pdf_url, is_financial_statement=is_fin
            )
        )

    if not filings and len(html) > 1024:
        logging.warning(
            "parse_deeds: no documents found — selectors may need updating for real justice.cz HTML"
        )

    # Sort: financial statements first, then by year descending (None sorts last)
    filings.sort(key=lambda f: (not f.is_financial_statement, -(f.year or 0)))
    return filings


def parse_filings_api(data: dict) -> list[Filing]:
    """Parse the new verejnerejstriky.msp.gov.cz Sbirka listin JSON payload."""
    items = data.get("vysledekdetail", {}).get("prehledlistin", [])
    filings: list[Filing] = []

    for item in items:
        title = (item.get("typlistiny") or "").strip()
        if not title:
            continue

        document_id = None
        for detail in item.get("detail") or []:
            digital = detail.get("obsah", {}).get("digitalnipodoba", {})
            document_id = digital.get("documentid")
            if document_id:
                break

        if not document_id:
            continue

        year_m = _YEAR_RE.search(title)
        year = int(year_m.group(0)) if year_m else None
        filings.append(
            Filing(
                title=title,
                year=year,
                pdf_url=_NEW_DOCUMENT_URL.format(document_id=document_id),
                is_financial_statement=classify_financial(title),
            )
        )

    filings.sort(key=lambda f: (not f.is_financial_statement, -(f.year or 0)))
    return filings


def list_filings(ico: str, client: httpx.Client | None = None) -> list[Filing]:
    """
    Fetch and return all Sbírka listin filings for a given IČO.

    The public registry migrated from the old or.justice.cz HTML pages to the
    verejnerejstriky.msp.gov.cz JSON API. The endpoint expects the numeric IČO
    without leading zeroes.
    """
    ico = ico.strip().zfill(8).lstrip("0") or "0"
    own_client = client is None
    if own_client:
        client = make_client()

    try:
        resp = client.get(_NEW_FILINGS_URL.format(ico=ico))
        resp.raise_for_status()
        return parse_filings_api(resp.json())
    finally:
        if own_client:
            client.close()
