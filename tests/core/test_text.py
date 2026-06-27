from rejstrik.core.text import normalize_label


def test_strips_diacritics_and_lowercases():
    assert normalize_label("Vlastní Kapitál") == "vlastni kapital"
    assert normalize_label("AKTIVA celkem") == "aktiva celkem"


def test_plain_ascii_unchanged():
    assert normalize_label("Revenue") == "revenue"
