from pathlib import Path

import pypdf  # noqa: F401  — must be importable (declared dependency)

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_pyproject_bumped_to_v0_8_0():
    text = _PYPROJECT.read_text(encoding="utf-8")
    assert 'version = "0.8.0"' in text


def test_pyproject_declares_pypdf():
    text = _PYPROJECT.read_text(encoding="utf-8")
    assert "pypdf" in text


def test_changelog_documents_v0_5_0():
    text = (Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text(
        encoding="utf-8"
    )
    assert "0.5.0" in text
    assert "read_filing_text" in text


def test_readme_mentions_read_filing_text():
    text = (Path(__file__).resolve().parent.parent / "README.md").read_text(
        encoding="utf-8"
    )
    assert "read_filing_text" in text


def test_changelog_documents_v0_6_0():
    text = (Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text(
        encoding="utf-8"
    )
    assert "0.6.0" in text
    assert "estimate_valuation" in text


def test_readme_mentions_estimate_valuation():
    text = (Path(__file__).resolve().parent.parent / "README.md").read_text(
        encoding="utf-8"
    )
    assert "estimate_valuation" in text
