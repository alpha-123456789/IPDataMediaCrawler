import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from tenacity import wait_none

import config
from media_platform.douyin.client import DouYinClient
from media_platform.douyin.core import DouYinCrawler
from media_platform.kuaishou.client import KuaiShouClient
from media_platform.kuaishou.core import KuaishouCrawler
from media_platform.tieba.client import BaiduTieBaClient
from media_platform.weibo.client import WeiboClient
from media_platform.xhs.client import XiaoHongShuClient
from media_platform.zhihu.core import ZhihuCrawler
from tools import crawl_dedup


class _FakeAsyncClientContext:
    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client_class", "module_name"),
    [
        (DouYinClient, "media_platform.douyin.client"),
        (KuaiShouClient, "media_platform.kuaishou.client"),
    ],
)
async def test_explicit_request_retry_succeeds_on_third_attempt(
    monkeypatch,
    client_class,
    module_name,
):
    request = httpx.Request("GET", "https://example.com/detail")
    response = httpx.Response(200, json={"ok": True}, request=request)
    fake_http_client = AsyncMock()
    fake_http_client.request.side_effect = [
        httpx.ReadTimeout("first timeout", request=request),
        httpx.ReadTimeout("second timeout", request=request),
        response,
    ]

    monkeypatch.setattr(
        f"{module_name}.make_async_client",
        lambda **kwargs: _FakeAsyncClientContext(fake_http_client),
    )
    sleep_mock = AsyncMock()
    monkeypatch.setattr(f"{module_name}.asyncio.sleep", sleep_mock)

    client = client_class(
        headers={},
        playwright_page=AsyncMock(),
        cookie_dict={},
    )

    result = await client._send_request_with_retry("GET", str(request.url))

    assert result is response
    assert fake_http_client.request.await_count == 3
    assert [call.args for call in sleep_mock.await_args_list] == [(2,), (4,)]


@pytest.mark.asyncio
async def test_kuaishou_search_uses_signed_rest_endpoint():
    page = AsyncMock()
    client = KuaiShouClient(
        headers={},
        playwright_page=page,
        cookie_dict={},
    )
    client.request_rest_v2_signed = AsyncMock(
        return_value={"result": 1, "feeds": []}
    )

    result = await client.search_info_by_keyword_v2("猴子警长", "2", "session-1")

    assert result == {"result": 1, "feeds": []}
    client.request_rest_v2_signed.assert_awaited_once_with(
        "/rest/v/search/feed",
        {
            "keyword": "猴子警长",
            "pcursor": "2",
            "page": "search",
            "searchSessionId": "session-1",
        },
    )


@pytest.mark.asyncio
async def test_kuaishou_creator_feed_uses_signed_rest_endpoint():
    client = KuaiShouClient(
        headers={},
        playwright_page=AsyncMock(),
        cookie_dict={},
    )
    client.request_rest_v2_signed = AsyncMock(
        return_value={"result": 1, "feeds": []}
    )

    result = await client.get_video_by_creater_v2("creator-1", "cursor-1")

    assert result == {"result": 1, "feeds": []}
    client.request_rest_v2_signed.assert_awaited_once_with(
        "/rest/v/profile/feed",
        {
            "user_id": "creator-1",
            "pcursor": "cursor-1",
            "page": "profile",
        },
    )


@pytest.mark.asyncio
async def test_kuaishou_creator_pagination_reads_rest_response(monkeypatch):
    client = KuaiShouClient(
        headers={},
        playwright_page=AsyncMock(),
        cookie_dict={},
    )
    client.get_video_by_creater_v2 = AsyncMock(
        return_value={
            "result": 1,
            "pcursor": "no_more",
            "feeds": [{"id": "video-1"}],
        }
    )
    callback = AsyncMock()
    monkeypatch.setattr("media_platform.kuaishou.client.asyncio.sleep", AsyncMock())

    videos = await client.get_all_videos_by_creator(
        "creator-1",
        crawl_interval=0,
        callback=callback,
    )

    assert videos == [{"id": "video-1"}]
    client.get_video_by_creater_v2.assert_awaited_once_with("creator-1", "")
    callback.assert_awaited_once_with([{"id": "video-1"}])


@pytest.mark.asyncio
async def test_kuaishou_signed_rest_request_includes_fresh_signature(monkeypatch):
    signature = AsyncMock(return_value="signed-value")
    monkeypatch.setattr(
        "media_platform.kuaishou.client.get_ks_sign_from_playwright",
        signature,
    )
    client = KuaiShouClient(
        headers={"User-Agent": "test"},
        playwright_page=AsyncMock(),
        cookie_dict={},
    )
    response = httpx.Response(200, json={"result": 1, "feeds": []})
    client._send_request_with_retry = AsyncMock(return_value=response)

    result = await client.request_rest_v2_signed(
        "/rest/v/search/feed",
        {"keyword": "猴子警长", "pcursor": "1"},
    )

    assert result == {"result": 1, "feeds": []}
    signature.assert_awaited_once_with(
        client.playwright_page,
        "/rest/v/search/feed",
        {"caver": 2},
        {"keyword": "猴子警长", "pcursor": "1"},
    )
    client._send_request_with_retry.assert_awaited_once_with(
        method="POST",
        url=(
            "https://www.kuaishou.com/rest/v/search/feed"
            "?__NS_hxfalcon=signed-value&caver=2"
        ),
        data='{"keyword":"猴子警长","pcursor":"1"}',
        headers={"User-Agent": "test"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("crawler_class", "client_attr", "detail_method", "task_method", "task_kwargs"),
    [
        (
            DouYinCrawler,
            "dy_client",
            "get_video_by_id",
            "get_aweme_detail",
            {"aweme_id": "dy-1"},
        ),
        (
            KuaishouCrawler,
            "ks_client",
            "get_video_info",
            "get_video_info_task",
            {"video_id": "ks-1"},
        ),
    ],
)
async def test_detail_timeout_is_skipped_after_retries(
    crawler_class,
    client_attr,
    detail_method,
    task_method,
    task_kwargs,
):
    request = httpx.Request("GET", "https://example.com/detail")
    crawler = crawler_class()
    client = AsyncMock()
    getattr(client, detail_method).side_effect = httpx.ReadTimeout(
        "timeout after retries",
        request=request,
    )
    setattr(crawler, client_attr, client)

    result = await getattr(crawler, task_method)(
        semaphore=asyncio.Semaphore(1),
        **task_kwargs,
    )

    assert result is None


@pytest.mark.asyncio
async def test_xhs_request_raises_original_timeout_after_three_attempts(monkeypatch):
    request = httpx.Request("GET", "https://edith.xiaohongshu.com/test")
    fake_http_client = AsyncMock()
    fake_http_client.request.side_effect = httpx.ReadTimeout(
        "timeout",
        request=request,
    )
    monkeypatch.setattr(
        "media_platform.xhs.client.make_async_client",
        lambda **kwargs: _FakeAsyncClientContext(fake_http_client),
    )

    client = XiaoHongShuClient(
        headers={},
        playwright_page=AsyncMock(),
        cookie_dict={},
    )
    request_without_wait = client.request.retry_with(wait=wait_none())

    with pytest.raises(httpx.ReadTimeout):
        await request_without_wait(client, "GET", str(request.url))

    assert fake_http_client.request.await_count == 3


@pytest.mark.asyncio
async def test_xhs_query_self_retries_timeout_three_times(monkeypatch):
    request = httpx.Request("GET", "https://edith.xiaohongshu.com/api/sns/web/v1/user/selfinfo")
    response = httpx.Response(
        200,
        json={"data": {"result": {"success": True}}},
        request=request,
    )
    fake_http_client = AsyncMock()
    fake_http_client.get.side_effect = [
        httpx.ReadTimeout("first timeout", request=request),
        httpx.ReadTimeout("second timeout", request=request),
        response,
    ]
    monkeypatch.setattr(
        "media_platform.xhs.client.make_async_client",
        lambda **kwargs: _FakeAsyncClientContext(fake_http_client),
    )

    client = XiaoHongShuClient(
        headers={},
        playwright_page=AsyncMock(),
        cookie_dict={},
    )
    client._pre_headers = AsyncMock(return_value={})
    query_without_wait = client.query_self.retry_with(wait=wait_none())

    result = await query_without_wait(client)

    assert result == {"data": {"result": {"success": True}}}
    assert fake_http_client.get.await_count == 3


@pytest.mark.asyncio
async def test_weibo_request_retries_timeout_three_times(monkeypatch):
    request = httpx.Request("GET", "https://m.weibo.cn/test")
    response = httpx.Response(
        200,
        json={"ok": 1, "data": {"id": "wb-1"}},
        request=request,
    )
    fake_http_client = AsyncMock()
    fake_http_client.request.side_effect = [
        httpx.ReadTimeout("first timeout", request=request),
        httpx.ReadTimeout("second timeout", request=request),
        response,
    ]
    monkeypatch.setattr(
        "media_platform.weibo.client.make_async_client",
        lambda **kwargs: _FakeAsyncClientContext(fake_http_client),
    )

    client = WeiboClient(
        headers={},
        playwright_page=AsyncMock(),
        cookie_dict={},
    )
    request_without_wait = client.request.retry_with(wait=wait_none())

    result = await request_without_wait(client, "GET", str(request.url))

    assert result == {"id": "wb-1"}
    assert fake_http_client.request.await_count == 3


@pytest.mark.asyncio
async def test_tieba_failed_creator_note_does_not_cancel_other_notes():
    client = BaiduTieBaClient(playwright_page=AsyncMock())

    async def get_note(note_id):
        if note_id == "bad":
            raise RuntimeError("timeout after retries")
        return {"note_id": note_id}

    client.get_note_by_id = get_note

    notes = await asyncio.gather(
        client._get_note_by_id_or_none("bad"),
        client._get_note_by_id_or_none("good"),
    )

    assert notes == [None, {"note_id": "good"}]


@pytest.mark.asyncio
async def test_zhihu_specified_note_failure_does_not_cancel_other_notes(monkeypatch):
    urls = [
        "https://www.zhihu.com/question/1/answer/11",
        "https://www.zhihu.com/question/2/answer/22",
    ]
    monkeypatch.setattr(config, "ZHIHU_SPECIFIED_ID_LIST", urls)
    monkeypatch.setattr(config, "MAX_CONCURRENCY_NUM", 2)

    crawler = ZhihuCrawler()
    request = httpx.Request("GET", urls[0])
    crawler.get_note_detail = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("timeout after retries", request=request),
            {"content_id": "22"},
        ]
    )
    crawler.batch_get_content_comments = AsyncMock()
    update_content = AsyncMock()
    monkeypatch.setattr(
        "media_platform.zhihu.core.zhihu_store.update_zhihu_content",
        update_content,
    )

    await crawler.get_specified_notes()

    update_content.assert_awaited_once_with({"content_id": "22"})
    crawler.batch_get_content_comments.assert_awaited_once_with(
        [{"content_id": "22"}]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["bili", "wb", "ks", "dy"])
async def test_platform_dedup_skips_existing_content_regardless_of_age(monkeypatch, platform):
    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class FakeSession:
        def __init__(self):
            self.results = [FakeResult([("123", 100)])]
            self.calls = 0

        async def execute(self, statement):
            result = self.results[self.calls]
            self.calls += 1
            return result

    class FakeSessionContext:
        def __init__(self, session):
            self.session = session

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    session = FakeSession()
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "db")
    monkeypatch.setattr(crawl_dedup, "get_session", lambda: FakeSessionContext(session))

    uncrawled = await crawl_dedup.filter_uncrawled_note_ids(platform, ["123", "456"])

    assert uncrawled == ["456"]
    assert session.calls == 1

@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["bili", "wb", "ks", "dy"])
async def test_platform_dedup_skips_existing_content_without_comments(monkeypatch, platform):
    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class FakeSession:
        def __init__(self):
            self.results = [FakeResult([("123", 1_000)])]
            self.calls = 0

        async def execute(self, statement):
            result = self.results[self.calls]
            self.calls += 1
            return result

    class FakeSessionContext:
        def __init__(self, session):
            self.session = session

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    session = FakeSession()
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "db")
    monkeypatch.setattr(crawl_dedup, "get_session", lambda: FakeSessionContext(session))

    uncrawled = await crawl_dedup.filter_uncrawled_note_ids(platform, ["123", "456"])

    assert uncrawled == ["456"]
    assert session.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["bili", "wb", "ks", "dy", "xhs"])
async def test_comment_queue_only_keeps_new_content(
    monkeypatch, platform
):
    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class FakeSession:
        def __init__(self):
            self.results = [
                FakeResult([("101", 100), ("102", 1_000), ("103", 1_000)]),
            ]
            self.calls = 0

        async def execute(self, statement):
            result = self.results[self.calls]
            self.calls += 1
            return result

    class FakeSessionContext:
        def __init__(self, session):
            self.session = session

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    session = FakeSession()
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "db")
    monkeypatch.setattr(crawl_dedup, "get_session", lambda: FakeSessionContext(session))

    comment_ids = await crawl_dedup.filter_note_ids_for_comment_crawl(
        platform,
        ["101", "102", "103", "104"],
    )

    assert comment_ids == ["104"]
    assert session.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["bili", "wb", "dy", "xhs"])
async def test_comment_recovery_requires_positive_count_and_no_saved_comments(
    monkeypatch, platform
):
    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class FakeSession:
        def __init__(self):
            self.results = [
                FakeResult(
                    [
                        ("101", "5"),
                        ("102", "0"),
                        ("103", ""),
                        ("104", None),
                        ("105", "invalid"),
                        ("106", "3"),
                    ]
                ),
                FakeResult([("106",)]),
            ]
            self.calls = 0

        async def execute(self, statement):
            result = self.results[self.calls]
            self.calls += 1
            return result

    class FakeSessionContext:
        def __init__(self, session):
            self.session = session

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    session = FakeSession()
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "db")
    monkeypatch.setattr(crawl_dedup, "get_session", lambda: FakeSessionContext(session))

    recovery_ids = await crawl_dedup.filter_note_ids_needing_comment_recovery(
        platform,
        ["101", "102", "103", "104", "105", "106", "107"],
    )

    assert recovery_ids == ["101"]
    assert session.calls == 2


@pytest.mark.asyncio
async def test_kuaishou_comment_recovery_is_disabled_without_stored_count(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "db")

    recovery_ids = await crawl_dedup.filter_note_ids_needing_comment_recovery(
        "ks", ["video-1"]
    )

    assert recovery_ids == []
