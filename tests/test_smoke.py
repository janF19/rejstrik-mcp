import inspect

import rejstrik
from scripts import smoke


def test_version_exposed():
    assert rejstrik.__version__ == "0.6.0"


def test_smoke_exposes_canary_function():
    assert hasattr(smoke, "canary")
    assert callable(smoke.canary)


def test_smoke_main_calls_canary():
    source = inspect.getsource(smoke.main)
    assert "canary(" in source
