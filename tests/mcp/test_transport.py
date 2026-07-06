from rejstrik.mcp import server


def test_main_defaults_to_stdio(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        server.mcp, "run", lambda transport: calls.setdefault("t", transport)
    )
    server.main([])
    assert calls["t"] == "stdio"


def test_main_http_flag(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        server.mcp, "run", lambda transport: calls.setdefault("t", transport)
    )
    server.main(["--http", "--port", "9000"])
    assert calls["t"] == "streamable-http"
    assert server.mcp.settings.port == 9000
