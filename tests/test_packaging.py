from pathlib import Path

import pypdf  # noqa: F401  — must be importable (declared dependency)

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_pyproject_bumped_to_v0_5_0():
    text = _PYPROJECT.read_text(encoding="utf-8")
    assert 'version = "0.5.0"' in text


def test_pyproject_declares_pypdf():
    text = _PYPROJECT.read_text(encoding="utf-8")
    assert "pypdf" in text
