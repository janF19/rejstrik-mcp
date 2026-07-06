import pytest

from rejstrik.mcp import server


@pytest.fixture()
def no_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.mark.parametrize(
    "call",
    [
        lambda: server.extract_financials("00514152"),
        lambda: server.ask_filing("00514152", "what changed?"),
        lambda: server.analyze_company_financials("Budvar"),
        lambda: server.analyze_company_card("Budvar"),
    ],
)
def test_keyed_tools_raise_helpful_error_without_key(no_keys, call):
    with pytest.raises(server.MissingApiKey) as exc:
        call()
    message = str(exc.value)
    assert "get_filing" in message
    assert "analyze_financials" in message
