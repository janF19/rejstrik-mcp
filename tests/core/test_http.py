import httpx
import respx

from rejstrik.core.http import make_client, USER_AGENT


def test_client_has_user_agent_and_redirects():
    client = make_client()
    try:
        assert client.headers["User-Agent"] == USER_AGENT
        assert "rejstrik-mcp" in USER_AGENT
        assert client.follow_redirects is True
    finally:
        client.close()


def test_user_agent_reflects_current_version():
    assert "0.3" in USER_AGENT


@respx.mock
def test_get_retries_on_503_then_succeeds():
    route = respx.get("https://example.test/x").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    client = make_client(retries=3)
    resp = client.get("https://example.test/x")
    assert resp.status_code == 200
    assert route.call_count == 3
    client.close()
