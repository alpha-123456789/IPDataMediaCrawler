import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from media_platform.bilibili.client import BilibiliClient
from media_platform.bilibili.core import BilibiliCrawler


class _FakeAsyncClientContext:
    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
async def test_bilibili_request_retries_transient_timeout(monkeypatch):
    request = httpx.Request("GET", "https://api.bilibili.com/test")
    response = httpx.Response(
        200,
        json={"code": 0, "data": {"ok": True}},
        request=request,
    )
    fake_http_client = AsyncMock()
    fake_http_client.request.side_effect = [
        httpx.ReadTimeout("first timeout", request=request),
        httpx.ReadTimeout("second timeout", request=request),
        response,
    ]

    monkeypatch.setattr(
        "media_platform.bilibili.client.make_async_client",
        lambda **kwargs: _FakeAsyncClientContext(fake_http_client),
    )
    sleep_mock = AsyncMock()
    monkeypatch.setattr("media_platform.bilibili.client.asyncio.sleep", sleep_mock)

    client = BilibiliClient(
        headers={},
        playwright_page=AsyncMock(),
        cookie_dict={},
    )

    result = await client.request("GET", str(request.url))

    assert result == {"ok": True}
    assert fake_http_client.request.await_count == 3
    assert sleep_mock.await_args_list[0].args == (2,)
    assert sleep_mock.await_args_list[1].args == (4,)


@pytest.mark.asyncio
async def test_video_info_timeout_only_skips_failed_video():
    request = httpx.Request("GET", "https://api.bilibili.com/test")
    crawler = BilibiliCrawler()
    crawler.bili_client = AsyncMock()
    crawler.bili_client.get_video_info.side_effect = httpx.ReadTimeout(
        "timeout after retries",
        request=request,
    )

    result = await crawler.get_video_info_task(
        aid=123,
        bvid="",
        semaphore=asyncio.Semaphore(1),
    )

    assert result is None
