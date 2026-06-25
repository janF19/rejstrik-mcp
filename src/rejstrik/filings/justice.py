"""
Parser for or.justice.cz Sbírka listin (Czech commercial registry filings).

NOTE: Fixtures used in tests are synthetic (or.justice.cz was under maintenance
on 2026-06-25). Selectors and HTML structure should be verified against real
responses when the service resumes.
"""

from __future__ import annotations

import logging
import re

import httpx
from selectolax.parser import HTMLParser

from rejstrik.core.http import make_client
from rejstrik.filings.models import Filing, classify_financial

_BASE_URL = "https://or.justice.cz"
_SEARCH_URL = _BASE_URL + "/ias/ui/rejstrik-firma.vysledky"
_DEEDS_URL = _BASE_URL + "/ias/ui/vypis-sl-firma"

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


def list_filings(ico: str, client: httpx.Client | None = None) -> list[Filing]:
    """
    Fetch and return all Sbírka listin filings for a given IČO.

    Steps:
      1. GET /ias/ui/rejstrik-firma.vysledky?ico={ico}
      2. Extract subjektId from response
      3. GET /ias/ui/vypis-sl-firma?subjektId={subject_id}
      4. Parse and return filings
    """
    ico = ico.strip().zfill(8)
    own_client = client is None
    if own_client:
        client = make_client()

    try:
        resp = client.get(_SEARCH_URL, params={"ico": ico})
        resp.raise_for_status()
        subject_id = parse_subject_id(resp.text)
        if subject_id is None:
            return []

        resp2 = client.get(_DEEDS_URL, params={"subjektId": subject_id})
        resp2.raise_for_status()
        return parse_deeds(resp2.text)
    finally:
        if own_client:
            client.close()
