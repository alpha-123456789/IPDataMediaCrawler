import asyncio
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

import config
from media_platform.xhs import core as xhs_core
from media_platform.xhs.client import XiaoHongShuClient
from media_platform.xhs.core import XiaoHongShuCrawler
from media_platform.xhs.exception import CaptchaError, InitialStateParseError
from media_platform.xhs.extractor import XiaoHongShuExtractor
from tools import crawl_dedup


@pytest.mark.asyncio
async def test_search_skips_empty_note_detail(monkeypatch):
    monkeypatch.setattr(config, "KEYWORDS", "test-keyword")
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 20)
    monkeypatch.setattr(config, "START_PAGE", 1)
    monkeypatch.setattr(config, "SORT_TYPE", "")
    monkeypatch.setattr(config, "MAX_CONCURRENCY_NUM", 1)

    async def return_all_note_ids(platform, note_ids):
        assert platform == "xhs"
        return note_ids

    monkeypatch.setattr(
        "media_platform.xhs.core.filter_uncrawled_note_ids",
        return_all_note_ids,
    )
    monkeypatch.setattr(
        "media_platform.xhs.core.filter_note_ids_needing_comment_recovery",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "media_platform.xhs.core.asyncio.sleep",
        AsyncMock(),
    )

    crawler = XiaoHongShuCrawler()
    crawler.xhs_client = AsyncMock()
    crawler.xhs_client.get_note_by_keyword.return_value = {
        "has_more": True,
        "items": [
            {
                "id": "note-1",
                "model_type": "note",
                "xsec_source": "pc_search",
                "xsec_token": "token-1",
            }
        ],
    }
    crawler.get_note_detail_async_task = AsyncMock(return_value=None)
    crawler.batch_get_note_comments = AsyncMock()
    crawler.get_notice_media = AsyncMock()

    await crawler.search()

    assert crawler.success == 0
    assert crawler.mismatch == 0
    crawler.batch_get_note_comments.assert_awaited_once_with([], [])


@pytest.mark.asyncio
async def test_search_skips_existing_note_before_detail_and_comments(monkeypatch):
    monkeypatch.setattr(config, "KEYWORDS", "test-keyword")
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 20)
    monkeypatch.setattr(config, "START_PAGE", 1)
    monkeypatch.setattr(config, "SORT_TYPE", "")

    async def no_uncrawled_note_ids(platform, note_ids):
        assert platform == "xhs"
        assert note_ids == ["note-1"]
        return []

    monkeypatch.setattr(
        "media_platform.xhs.core.filter_uncrawled_note_ids",
        no_uncrawled_note_ids,
    )
    monkeypatch.setattr(
        "media_platform.xhs.core.filter_note_ids_needing_comment_recovery",
        AsyncMock(return_value=[]),
    )

    crawler = XiaoHongShuCrawler()
    crawler.xhs_client = AsyncMock()
    crawler.xhs_client.get_note_by_keyword.return_value = {
        "has_more": True,
        "items": [
            {
                "id": "note-1",
                "model_type": "note",
                "xsec_source": "pc_search",
                "xsec_token": "token-1",
            }
        ],
    }
    crawler.get_note_detail_async_task = AsyncMock()
    crawler.batch_get_note_comments = AsyncMock()

    await crawler.search()

    crawler.get_note_detail_async_task.assert_not_awaited()
    crawler.batch_get_note_comments.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_processes_last_page_when_has_more_is_false(monkeypatch):
    monkeypatch.setattr(config, "KEYWORDS", "test-keyword")
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 20)
    monkeypatch.setattr(config, "START_PAGE", 1)
    monkeypatch.setattr(config, "SORT_TYPE", "")
    monkeypatch.setattr(config, "MAX_CONCURRENCY_NUM", 1)

    monkeypatch.setattr(
        "media_platform.xhs.core.filter_uncrawled_note_ids",
        AsyncMock(return_value=["note-1"]),
    )
    monkeypatch.setattr(
        "media_platform.xhs.core.filter_note_ids_needing_comment_recovery",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "media_platform.xhs.core.asyncio.sleep",
        AsyncMock(),
    )

    crawler = XiaoHongShuCrawler()
    crawler.xhs_client = AsyncMock()
    crawler.xhs_client.get_note_by_keyword.return_value = {
        "has_more": False,
        "items": [
            {
                "id": "note-1",
                "model_type": "note",
                "xsec_source": "pc_search",
                "xsec_token": "token-1",
            }
        ],
    }
    crawler.get_note_detail_async_task = AsyncMock(
        return_value={
            "note_id": "note-1",
            "title": "test-keyword",
            "desc": "",
            "xsec_token": "token-1",
        }
    )
    monkeypatch.setattr(
        "media_platform.xhs.core.xhs_store.update_xhs_note",
        AsyncMock(),
    )
    crawler.get_notice_media = AsyncMock()
    crawler.batch_get_note_comments = AsyncMock()

    await crawler.search()

    crawler.get_note_detail_async_task.assert_awaited_once()
    crawler.xhs_client.get_note_by_keyword.assert_awaited_once()
    assert crawler.success == 1


@pytest.mark.asyncio
async def test_search_recovers_missing_comments_without_fetching_existing_note(monkeypatch):
    monkeypatch.setattr(config, "KEYWORDS", "test-keyword")
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 20)
    monkeypatch.setattr(config, "START_PAGE", 1)
    monkeypatch.setattr(config, "SORT_TYPE", "")

    monkeypatch.setattr(
        "media_platform.xhs.core.filter_uncrawled_note_ids",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "media_platform.xhs.core.filter_note_ids_needing_comment_recovery",
        AsyncMock(return_value=["note-1"]),
    )

    crawler = XiaoHongShuCrawler()
    crawler.xhs_client = AsyncMock()
    crawler.xhs_client.get_note_by_keyword.return_value = {
        "has_more": True,
        "items": [
            {
                "id": "note-1",
                "model_type": "note",
                "xsec_source": "pc_search",
                "xsec_token": "token-1",
            }
        ],
    }
    crawler.get_note_detail_async_task = AsyncMock()
    crawler.batch_get_note_comments = AsyncMock()

    await crawler.search()

    crawler.get_note_detail_async_task.assert_not_awaited()
    crawler.batch_get_note_comments.assert_awaited_once_with(
        ["note-1"], ["token-1"]
    )


@pytest.mark.asyncio
async def test_detail_skips_when_api_and_html_are_empty(monkeypatch):
    monkeypatch.setattr(
        "media_platform.xhs.core.asyncio.sleep",
        AsyncMock(),
    )

    crawler = XiaoHongShuCrawler()
    crawler.xhs_client = AsyncMock()
    crawler.xhs_client.get_note_by_id.return_value = None
    crawler.xhs_client.get_note_by_id_from_html.return_value = None

    result = await crawler.get_note_detail_async_task(
        note_id="note-empty",
        xsec_source="pc_search",
        xsec_token="token-empty",
        semaphore=asyncio.Semaphore(1),
    )

    assert result is None


@pytest.mark.asyncio
async def test_creator_parse_error_is_converted_to_data_fetch_error():
    client = object.__new__(XiaoHongShuClient)
    client._domain = "https://www.xiaohongshu.com"
    client.headers = {}
    client.request = AsyncMock(
        return_value=(
            '<script>window.__INITIAL_STATE__={"user":{"userPageData":'
            '{"value":void 0}}};</script>'
        )
    )
    client._extractor = XiaoHongShuExtractor()

    with pytest.raises(InitialStateParseError, match="Failed to parse creator page initial state"):
        await client.get_creator_info("creator-with-invalid-state")


@pytest.mark.asyncio
async def test_creator_parse_error_is_not_persisted_as_creator_failure(monkeypatch):
    crawler = XiaoHongShuCrawler()
    crawler.xhs_client = AsyncMock()
    crawler.xhs_client.get_creator_info.side_effect = InitialStateParseError(
        "Failed to parse creator page initial state"
    )
    crawler._get_uncrawled_creator_ids = AsyncMock(return_value=["creator-with-invalid-state"])
    recorded_failures = []

    monkeypatch.setattr(xhs_core.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(
        xhs_core,
        "record_creator_failure",
        lambda platform, creator_id: recorded_failures.append((platform, creator_id)),
    )

    await crawler.get_creators_and_notes()

    assert recorded_failures == []


@pytest.mark.asyncio
async def test_detail_propagates_captcha():
    crawler = XiaoHongShuCrawler()
    crawler.xhs_client = AsyncMock()
    crawler.xhs_client.get_note_by_id.side_effect = CaptchaError("captcha required")

    with pytest.raises(CaptchaError) as exc_info:
        await crawler.get_note_detail_async_task(
            note_id="note-captcha",
            xsec_source="pc_search",
            xsec_token="token-captcha",
            semaphore=asyncio.Semaphore(1),
        )

    assert exc_info.value.redirect_url == (
        "https://www.xiaohongshu.com/explore/note-captcha?"
        "xsec_token=token-captcha&xsec_source=pc_search"
    )
    crawler.xhs_client.get_note_by_id_from_html.assert_not_awaited()


@pytest.mark.asyncio
async def test_xhs_api_headers_match_browser_fingerprint(monkeypatch):
    async def fake_convert_cookies(browser_context, urls=None):
        return "a1=test-cookie", {"a1": "test-cookie"}

    monkeypatch.setattr(
        xhs_core.utils,
        "convert_browser_context_cookies",
        fake_convert_cookies,
    )

    crawler = XiaoHongShuCrawler()
    crawler.browser_context = object()
    crawler.context_page = object()

    client = await crawler.create_xhs_client(httpx_proxy=None)

    assert client.headers["user-agent"] == crawler.user_agent
    assert client.headers["sec-ch-ua"] == crawler.sec_ch_ua
    assert client.headers["sec-ch-ua-platform"] == crawler.sec_ch_ua_platform
    assert 'Chrome/136.0.0.0' in client.headers["user-agent"]
    assert '"Windows"' == client.headers["sec-ch-ua-platform"]


@pytest.mark.asyncio
async def test_sync_api_fingerprint_from_browser():
    crawler = XiaoHongShuCrawler()
    crawler.context_page = AsyncMock()
    crawler.context_page.evaluate.return_value = {
        "userAgent": "Mozilla/5.0 test Chrome/140.0.0.0",
        "userAgentData": {
            "brands": [
                {"brand": "Chromium", "version": "140"},
                {"brand": "Google Chrome", "version": "140"},
            ],
            "mobile": False,
            "platform": "Windows",
        },
    }

    await crawler._sync_api_fingerprint_from_browser()

    assert crawler.user_agent == "Mozilla/5.0 test Chrome/140.0.0.0"
    assert crawler.sec_ch_ua == '"Chromium";v="140", "Google Chrome";v="140"'
    assert crawler.sec_ch_ua_mobile == "?0"
    assert crawler.sec_ch_ua_platform == '"Windows"'


@pytest.mark.asyncio
async def test_comments_propagate_captcha():
    crawler = XiaoHongShuCrawler()
    crawler.xhs_client = AsyncMock()
    crawler.xhs_client.get_note_all_comments.side_effect = CaptchaError("captcha required")

    with pytest.raises(CaptchaError) as exc_info:
        await crawler.get_comments(
            note_id="note-captcha",
            xsec_token="token-captcha",
            semaphore=asyncio.Semaphore(1),
        )

    assert exc_info.value.redirect_url == (
        "https://www.xiaohongshu.com/explore/note-captcha?"
        "xsec_token=token-captcha&xsec_source=pc_search"
    )


def test_extract_captcha_data_from_nested_json():
    request = httpx.Request("GET", "https://edith.xiaohongshu.com/test")
    response = httpx.Response(
        461,
        json={
            "data": {
                "verifyType": "slider",
                "verifyUuid": "uuid-from-json",
                "verifyBiz": "web_detail",
            }
        },
        request=request,
    )

    assert XiaoHongShuClient._extract_captcha_data(response) == {
        "verify_type": "slider",
        "verify_uuid": "uuid-from-json",
        "verify_biz": "web_detail",
    }


@pytest.mark.asyncio
async def test_captcha_without_verify_params_cools_down_and_retries(monkeypatch):
    sleep_mock = AsyncMock()
    monkeypatch.setattr("media_platform.xhs.core.asyncio.sleep", sleep_mock)

    crawler = XiaoHongShuCrawler()
    crawler.context_page = AsyncMock()
    crawler.context_page.url = "https://www.xiaohongshu.com/explore/note-461"
    crawler.browser_context = AsyncMock()
    crawler.xhs_client = AsyncMock()
    captcha_error = CaptchaError(
        "captcha without parameters",
        status_code=461,
        redirect_url="https://www.xiaohongshu.com/explore/note-461",
    )

    await crawler._wait_for_captcha(captcha_error, cooldown_seconds=300)

    crawler.context_page.bring_to_front.assert_not_awaited()
    crawler.context_page.goto.assert_not_awaited()
    crawler.context_page.locator.assert_not_called()
    sleep_mock.assert_awaited_once_with(300)
    crawler.xhs_client.update_cookies.assert_awaited_once()
    crawler.xhs_client.pong.assert_not_awaited()


@pytest.mark.asyncio
async def test_captcha_with_verify_params_opens_verification_page(monkeypatch):
    sleep_mock = AsyncMock()
    monkeypatch.setattr("media_platform.xhs.core.asyncio.sleep", sleep_mock)

    crawler = XiaoHongShuCrawler()
    crawler.context_page = AsyncMock()
    crawler.browser_context = AsyncMock()
    crawler.xhs_client = AsyncMock()
    crawler._page_has_visible_captcha = AsyncMock(side_effect=[True, False])
    captcha_error = CaptchaError(
        "captcha with parameters",
        verify_type="slider",
        verify_uuid="verify-uuid",
        verify_biz="461",
        status_code=461,
        redirect_url="https://www.xiaohongshu.com/explore/note-verify",
    )

    await crawler._wait_for_captcha(captcha_error, timeout_seconds=60)

    opened_url = crawler.context_page.goto.await_args.args[0]
    parsed_url = urlparse(opened_url)
    assert parsed_url.path == "/website-login/captcha"
    assert parse_qs(parsed_url.query) == {
        "redirectPath": [captcha_error.redirect_url],
        "verifyUuid": ["verify-uuid"],
        "verifyType": ["slider"],
        "verifyBiz": ["461"],
    }
    sleep_mock.assert_awaited_once_with(30)
    crawler.xhs_client.update_cookies.assert_awaited_once()


@pytest.mark.asyncio
async def test_xhs_dedup_skips_existing_note(monkeypatch):
    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class FakeSession:
        def __init__(self):
            self.calls = 0

        async def execute(self, statement):
            self.calls += 1
            return FakeResult([("already-crawled", 100)])

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

    uncrawled = await crawl_dedup.filter_uncrawled_note_ids(
        "xhs",
        ["already-crawled", "new-note"],
    )

    assert uncrawled == ["new-note"]
    assert session.calls == 1
