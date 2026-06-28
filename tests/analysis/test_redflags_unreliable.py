from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import detect_red_flags


def test_unreliable_vat_adds_warning():
    flags = detect_red_flags(NormalizedFinancials(), Ratios(), [], unreliable_vat=True)
    assert any(f.code == "unreliable_vat" and f.severity == "warning" for f in flags)


def test_reliable_or_unknown_vat_adds_no_flag():
    reliable = detect_red_flags(
        NormalizedFinancials(), Ratios(), [], unreliable_vat=False
    )
    unknown = detect_red_flags(
        NormalizedFinancials(), Ratios(), [], unreliable_vat=None
    )
    assert not any(f.code == "unreliable_vat" for f in reliable)
    assert not any(f.code == "unreliable_vat" for f in unknown)
