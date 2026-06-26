import hashlib
import os

import httpx
from pydantic import BaseModel

from rejstrik.core.http import make_client
from rejstrik.filings.models import Filing


class PdfSource(BaseModel):
    data: bytes
    sha256: str
    filename: str


def _make(data: bytes, filename: str) -> PdfSource:
    return PdfSource(data=data, sha256=hashlib.sha256(data).hexdigest(), filename=filename)


def load_pdf(ref: str | Filing, client: httpx.Client | None = None) -> PdfSource:
    url = ref.pdf_url if isinstance(ref, Filing) else ref

    if not url.lower().startswith(("http://", "https://")) and os.path.exists(url):
        with open(url, "rb") as fh:
            return _make(fh.read(), os.path.basename(url))

    owns = client is None
    client = client or make_client()
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return _make(resp.content, "filing.pdf")
    finally:
        if owns:
            client.close()
