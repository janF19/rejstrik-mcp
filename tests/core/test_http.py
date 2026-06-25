from rejstrik.core.http import make_client, USER_AGENT


def test_client_has_user_agent_and_redirects():
    client = make_client()
    try:
        assert client.headers["User-Agent"] == USER_AGENT
        assert "rejstrik-mcp" in USER_AGENT
        assert client.follow_redirects is True
    finally:
        client.close()
