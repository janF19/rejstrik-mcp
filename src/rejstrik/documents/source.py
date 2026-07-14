import hashlib
import os
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel

from rejstrik.core.http import make_client
from rejstrik.filings.justice import parse_download_link
from rejstrik.filings.models import Filing

_LEGACY_DETAIL_HOST = "or.justice.cz"
_LEGACY_DETAIL_PATH = "/ias/ui/vypis-sl-detail"


class PdfSource(BaseModel):
    data: bytes
    sha256: str
    filename: str


def _make(data: bytes, filename: str) -> PdfSource:
    return PdfSource(
        data=data, sha256=hashlib.sha256(data).hexdigest(), filename=filename
    )


def load_pdf(ref: str | Filing, client: httpx.Client | None = None) -> PdfSource:
    url = ref.pdf_url if isinstance(ref, Filing) else ref

    if not url.lower().startswith(("http://", "https://")) and os.path.exists(url):
        with open(url, "rb") as fh:
            return _make(fh.read(), os.path.basename(url))

    owns = client is None
    client = client or make_client()
    try:
        parts = urlsplit(url)
        if parts.hostname == _LEGACY_DETAIL_HOST and parts.path == _LEGACY_DETAIL_PATH:
            detail_resp = client.get(url)
            detail_resp.raise_for_status()
            download_url = parse_download_link(
                detail_resp.text, base_url=f"{parts.scheme}://{parts.hostname}"
            )
            if download_url is None:
                raise ValueError(f"No download link found on legacy detail page: {url}")
            resp = client.get(download_url)
        else:
            resp = client.get(url)
        resp.raise_for_status()
        return _make(resp.content, "filing.pdf")
    finally:
        if owns:
            client.close()
