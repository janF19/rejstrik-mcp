from rejstrik.analysis.industry import (
    FALLBACK_INDUSTRY_KEY,
    NACE_DIVISION_MAP,
    industry_key_for_nace,
)


def test_map_is_ported_verbatim_spot_checks():
    assert NACE_DIVISION_MAP["28"] == "machinery"
    assert NACE_DIVISION_MAP["25"] == "machinery"
    assert NACE_DIVISION_MAP["27"] == "electrical_equipment"
    assert NACE_DIVISION_MAP["10"] == "food_processing"
    # financial divisions map to the fallback
    assert NACE_DIVISION_MAP["64"] == FALLBACK_INDUSTRY_KEY
    assert NACE_DIVISION_MAP["65"] == FALLBACK_INDUSTRY_KEY
    assert NACE_DIVISION_MAP["66"] == FALLBACK_INDUSTRY_KEY


def test_resolves_division_from_code():
    key, reason = industry_key_for_nace(["28150"])
    assert key == "machinery"
    assert "28" in reason


def test_manufacturing_prioritized_over_retail():
    # division 28 (manufacturing, priority 0) beats 47 (retail, priority 2)
    key, _ = industry_key_for_nace(["47110", "28150"])
    assert key == "machinery"


def test_no_codes_returns_fallback():
    key, reason = industry_key_for_nace([])
    assert key == FALLBACK_INDUSTRY_KEY
    assert reason


def test_unmapped_division_returns_fallback():
    key, _ = industry_key_for_nace(["99999"])
    assert key == FALLBACK_INDUSTRY_KEY
