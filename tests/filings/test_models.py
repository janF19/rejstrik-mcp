from rejstrik.filings.models import Filing, classify_financial


def test_classify_financial_matches_keywords():
    assert classify_financial("Účetní závěrka 2023") is True
    assert classify_financial("VYROCNI ZPRAVA 2022") is True   # no diacritics, upper
    assert classify_financial("výkaz zisku a ztráty") is True
    assert classify_financial("Podpisový vzor jednatele") is False


def test_filing_defaults():
    f = Filing(title="Rozvaha 2023", pdf_url="https://x/y.pdf", year=2023)
    assert f.is_financial_statement is False  # set by caller, not auto
    assert f.year == 2023
