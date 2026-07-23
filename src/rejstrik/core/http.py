import time

import httpx

from rejstrik import __version__

USER_AGENT = f"rejstrik-mcp/{__version__} (+https://github.com/janF19/rejstrik-mcp)"

_RETRY_STATUS = {502, 503, 504}


class _RetryTransport(httpx.HTTPTransport):
    def __init__(self, retries: int) -> None:
        super().__init__(retries=retries)
        self._retries = retries

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        last = None
        for attempt in range(self._retries + 1):
            response = super().handle_request(request)
            if request.method != "GET" or response.status_code not in _RETRY_STATUS:
                return response
            last = response
            if attempt < self._retries:
                response.close()
                time.sleep(min(2**attempt * 0.5, 4.0))
        return last


def make_client(timeout: float = 30.0, retries: int = 3) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
        transport=_RetryTransport(retries=retries),
    )
