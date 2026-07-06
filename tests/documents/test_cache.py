from rejstrik.documents.cache import cache_dir, save_filing_pdf
from rejstrik.documents.source import PdfSource
import hashlib


def _source(data: bytes = b"%PDF-1.4 fake") -> PdfSource:
    return PdfSource(
        data=data, sha256=hashlib.sha256(data).hexdigest(), filename="filing.pdf"
    )


def test_cache_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("REJSTRIK_CACHE_DIR", str(tmp_path / "custom"))
    d = cache_dir()
    assert d == tmp_path / "custom"
    assert d.is_dir()


def test_save_filing_pdf_writes_named_file(tmp_path, monkeypatch):
    monkeypatch.setenv("REJSTRIK_CACHE_DIR", str(tmp_path))
    src = _source()
    path = save_filing_pdf(src, "00514152", 2024)
    assert path.name == f"00514152-2024-{src.sha256[:8]}.pdf"
    assert path.read_bytes() == src.data


def test_save_filing_pdf_unknown_year_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("REJSTRIK_CACHE_DIR", str(tmp_path))
    src = _source()
    first = save_filing_pdf(src, "00514152", None)
    second = save_filing_pdf(src, "00514152", None)
    assert first == second
    assert "unknown" in first.name
