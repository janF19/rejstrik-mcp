import pytest

from rejstrik.analysis.industry_multiples import (
    FALLBACK_INDUSTRY_KEY,
    IndustryMultiple,
    get_industry_multiple,
)


def test_known_key_returns_row_with_provenance():
    im = get_industry_multiple("machinery")
    assert isinstance(im, IndustryMultiple)
    assert im.industry_key == "machinery"
    assert im.source_industry == "Machinery"
    assert im.ev_ebitda == pytest.approx(14.980532406240457)
    assert im.firms == 210
    assert im.source_url.startswith("https://")
    assert im.as_of
    assert im.region == "Europe"


def test_unknown_key_falls_back_to_total_market():
    im = get_industry_multiple("does_not_exist")
    assert im.industry_key == FALLBACK_INDUSTRY_KEY


def test_blank_key_falls_back():
    assert get_industry_multiple(None).industry_key == FALLBACK_INDUSTRY_KEY
    assert get_industry_multiple("  ").industry_key == FALLBACK_INDUSTRY_KEY
