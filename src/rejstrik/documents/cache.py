import os
from pathlib import Path

from platformdirs import user_cache_dir

from rejstrik.documents.source import PdfSource


def cache_dir() -> Path:
    override = os.environ.get("REJSTRIK_CACHE_DIR")
    base = Path(override) if override else Path(user_cache_dir("rejstrik-mcp"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def save_filing_pdf(source: PdfSource, ico: str, year: int | None) -> Path:
    stem = f"{ico}-{year if year is not None else 'unknown'}-{source.sha256[:8]}.pdf"
    path = cache_dir() / stem
    if not path.exists():
        path.write_bytes(source.data)
    return path
