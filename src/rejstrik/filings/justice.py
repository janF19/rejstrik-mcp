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
_LEGACY_SEARCH_URL = _BASE_URL + "/ias/ui/rejstrik-$firma?ico={ico}"
_LEGACY_DEEDS_URL = _BASE_URL + "/ias/ui/vypis-sl-firma?subjektId={subject_id}"

_SUBJECT_ID_RE = re.compile(r"subjektId=(\d+)")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


class RegistryBlockedError(Exception):
    """Raised when both the new and legacy Sbírka listin portals are unreachable."""


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
    Parse the Sbírka listin page (table.list) and return a sorted list of
    Filing objects.

    Each row's detail link resolves to the *detail page* URL, not a direct
    PDF link — the legacy portal issues short-lived download tokens that
    must be resolved fresh (see parse_download_link / documents.source).

    Sorting: financial statements first, then by year descending (None last).
    """
    tree = HTMLParser(html)
    filings: list[Filing] = []

    for row in tree.css("table.list tbody tr"):
        link_node = row.css_first('a[href*="vypis-sl-detail"]')
        symbol_nodes = row.css("span.symbol")
        if link_node is None or not symbol_nodes:
            continue

        href = (link_node.attributes.get("href") or "").strip()
        if not href:
            continue

        title = ", ".join(
            (n.text(strip=True) or "").strip() for n in symbol_nodes
        ).strip()
        if not title:
            continue

        pdf_url = base_url.rstrip("/") + "/ias/ui/" + href.removeprefix("./")

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


def parse_download_link(html: str, base_url: str = _BASE_URL) -> str | None:
    """Return the absolute PDF download URL from a vypis-sl-detail page, or None."""
    tree = HTMLParser(html)
    node = tree.css_first('a[href*="/ias/content/download"]')
    if node is None:
        return None
    href = (node.attributes.get("href") or "").strip()
    if not href:
        return None
    if href.startswith("http"):
        return href
    return base_url.rstrip("/") + "/" + href.lstrip("/")


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


def _fetch_legacy_filings(ico_padded: str, client: httpx.Client) -> list[Filing] | None:
    """Try the legacy or.justice.cz fallback; return None if the subject can't be found."""
    search_resp = client.get(_LEGACY_SEARCH_URL.format(ico=ico_padded))
    search_resp.raise_for_status()
    subject_id = parse_subject_id(search_resp.text)
    if subject_id is None:
        return None

    deeds_resp = client.get(_LEGACY_DEEDS_URL.format(subject_id=subject_id))
    deeds_resp.raise_for_status()
    return parse_deeds(deeds_resp.text)


def list_filings(ico: str, client: httpx.Client | None = None) -> list[Filing]:
    """
    Fetch and return all Sbírka listin filings for a given IČO.

    Tries the new verejnerejstriky.msp.gov.cz JSON API first (numeric IČO
    without leading zeroes). On a block-shaped failure (HTTP 403) falls back
    to the legacy or.justice.cz HTML portal (IČO with leading zeroes). Other
    failures (404, timeouts, etc.) from the new API propagate unchanged —
    they aren't evidence of a block.
    """
    ico_padded = ico.strip().zfill(8)
    ico_stripped = ico_padded.lstrip("0") or "0"
    own_client = client is None
    if own_client:
        client = make_client()

    try:
        try:
            resp = client.get(_NEW_FILINGS_URL.format(ico=ico_stripped))
            resp.raise_for_status()
            return parse_filings_api(resp.json())
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise
            try:
                legacy_filings = _fetch_legacy_filings(ico_padded, client)
            except httpx.HTTPError:
                legacy_filings = None
            if legacy_filings is None:
                raise RegistryBlockedError(
                    f"Sbírka listin unreachable for IČO {ico_padded}: "
                    f"new portal (verejnerejstriky.msp.gov.cz) returned 403 and "
                    f"the legacy portal (or.justice.cz) has no matching subject. "
                    f"The registry may be blocking automated access. Check manually: "
                    f"https://or.justice.cz/ias/ui/rejstrik-$firma?ico={ico_padded}"
                ) from exc
            return legacy_filings
    finally:
        if own_client:
            client.close()
