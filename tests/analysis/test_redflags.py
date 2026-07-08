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
