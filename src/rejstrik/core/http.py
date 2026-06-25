import httpx

USER_AGENT = "rejstrik-mcp/0.1 (+https://github.com/janf19/rejstrik-mcp)"


def make_client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
    )
