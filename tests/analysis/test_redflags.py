from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import detect_red_flags
from rejstrik.documents.schema import NoteItem


def _codes(flags):
    return {f.code for f in flags}


def test_negative_equity_is_critical():
    flags = detect_red_flags(NormalizedFinancials(equity=-50.0), Ratios(), [])
    neg = next(f for f in flags if f.code == "negative_equity")
    assert neg.severity == "critical"


def test_liquidity_leverage_and_loss_warnings():
    n = NormalizedFinancials(net_profit=-10.0)
    r = Ratios(current_ratio=0.5, debt_to_equity=4.0)
    codes = _codes(detect_red_flags(n, r, []))
    assert {"low_liquidity", "high_leverage", "net_loss"} <= codes


def test_going_concern_and_related_party_notes():
    notes = [
        NoteItem(
            topic="Going concern",
            summary="Material uncertainty about going concern.",
        ),
        NoteItem(topic="Spřízněné osoby", summary="Půjčka jednateli."),
    ]
    flags = detect_red_flags(NormalizedFinancials(), Ratios(), notes)
    by_code = {f.code: f for f in flags}
    assert by_code["going_concern"].severity == "critical"
    assert by_code["related_party"].severity == "info"


def test_insolvency_cross_check():
    flags = detect_red_flags(NormalizedFinancials(), Ratios(), [], insolvent=True)
    assert any(f.code == "insolvency" and f.severity == "critical" for f in flags)


def test_clean_company_has_no_flags():
    n = NormalizedFinancials(equity=400.0, net_profit=150.0)
    r = Ratios(current_ratio=2.0, debt_to_equity=1.0)
    assert detect_red_flags(n, r, []) == []


def test_public_money_dependence_flag():
    from rejstrik.analysis.normalize import NormalizedFinancials
    from rejstrik.analysis.ratios import Ratios
    from rejstrik.analysis.redflags import detect_red_flags

    flags = detect_red_flags(
        NormalizedFinancials(revenue=1000.0),
        Ratios(),
        [],
        public_money_ratio=0.6,
    )
    assert any(f.code == "public_money_dependence" for f in flags)


def test_no_public_money_flag_when_small():
    from rejstrik.analysis.normalize import NormalizedFinancials
    from rejstrik.analysis.ratios import Ratios
    from rejstrik.analysis.redflags import detect_red_flags

    flags = detect_red_flags(
        NormalizedFinancials(revenue=1000.0), Ratios(), [], public_money_ratio=0.05
    )
    assert not any(f.code == "public_money_dependence" for f in flags)


def test_low_interest_coverage_is_critical():
    flags = detect_red_flags(NormalizedFinancials(), Ratios(interest_coverage=0.5), [])
    flag = next(f for f in flags if f.code == "low_interest_coverage")
    assert flag.severity == "critical"


def test_negative_ocf_with_positive_profit_is_warning():
    n = NormalizedFinancials(operating_cash_flow=-50.0, net_profit=30.0)
    flags = detect_red_flags(n, Ratios(), [])
    flag = next(f for f in flags if f.code == "negative_operating_cash_flow")
    assert flag.severity == "warning"


def test_negative_ocf_not_flagged_when_loss_making():
    n = NormalizedFinancials(operating_cash_flow=-50.0, net_profit=-30.0)
    flags = detect_red_flags(n, Ratios(), [])
    assert not any(f.code == "negative_operating_cash_flow" for f in flags)


def test_in05_zone_flags():
    from rejstrik.analysis.in05 import IN05Result

    distress = detect_red_flags(
        NormalizedFinancials(),
        Ratios(),
        [],
        in05=IN05Result(value=0.5, zone="distress"),
    )
    assert any(f.code == "in05_distress" and f.severity == "critical" for f in distress)
    grey = detect_red_flags(
        NormalizedFinancials(), Ratios(), [], in05=IN05Result(value=1.2, zone="grey")
    )
    assert any(f.code == "in05_grey_zone" and f.severity == "info" for f in grey)
