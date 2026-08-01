import inspect

import rejstrik
from scripts import smoke


def test_version_exposed():
    assert rejstrik.__version__ == "0.9.1"


def test_smoke_exposes_canary_function():
    assert hasattr(smoke, "canary")
    assert callable(smoke.canary)


def test_smoke_main_calls_canary():
    source = inspect.getsource(smoke.main)
    assert "canary(" in source


def test_trend_plausibility_flags_mismatch_and_wild_swings():
    from types import SimpleNamespace

    from rejstrik.analysis.redflags import RedFlag
    from rejstrik.analysis.trends import TrendItem

    report = SimpleNamespace(
        red_flags=[
            RedFlag(code="unit_mismatch_suspected", severity="warning", message="m")
        ],
        trends=[
            TrendItem(metric="revenue", current=1.0, prior=1000.0, pct_change=-0.999)
        ],
    )
    issues = smoke.trend_plausibility_issues(report)
    assert len(issues) == 2


def test_trend_plausibility_accepts_normal_year():
    from types import SimpleNamespace

    from rejstrik.analysis.trends import TrendItem

    report = SimpleNamespace(
        red_flags=[],
        trends=[
            TrendItem(metric="revenue", current=110.0, prior=100.0, pct_change=0.1)
        ],
    )
    assert smoke.trend_plausibility_issues(report) == []
