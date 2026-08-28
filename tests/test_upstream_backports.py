import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import String

import config
from database.models import (
    BilibiliUpDynamic,
    BilibiliVideo,
    BilibiliVideoComment,
    DouyinAweme,
    DouyinAwemeComment,
    KuaishouVideoComment,
    WeiboNote,
    WeiboNoteComment,
)
from media_platform.xhs.playwright_sign import sign_with_xhshow
from store.bilibili._store_impl import BiliDbStoreImplement
from tools.time_util import rfc2822_to_timestamp


def test_rfc2822_timestamp_respects_source_timezone():
    assert rfc2822_to_timestamp("Sat Dec 23 17:12:54 +0800 2023") == 1703322774


def test_platform_business_ids_are_strings():
    columns = [
        BilibiliVideo.video_id,
        BilibiliVideoComment.comment_id,
        BilibiliVideoComment.video_id,
        BilibiliUpDynamic.dynamic_id,
        DouyinAweme.aweme_id,
        DouyinAwemeComment.comment_id,
        DouyinAwemeComment.aweme_id,
        KuaishouVideoComment.comment_id,
        WeiboNote.note_id,
        WeiboNoteComment.comment_id,
        WeiboNoteComment.note_id,
    ]

    assert all(isinstance(column.property.columns[0].type, String) for column in columns)


@pytest.mark.asyncio
async def test_bilibili_store_keeps_opaque_business_ids(monkeypatch):
    class Result:
        def scalar_one_or_none(self):
            return None

    class Session:
        def __init__(self):
            self.added = []
            self.commit = AsyncMock()

        async def execute(self, statement):
            return Result()

        def add(self, item):
            self.added.append(item)

    class SessionContext:
        def __init__(self, session):
            self.session = session

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    session = Session()
    monkeypatch.setattr(
        "store.bilibili._store_impl.get_session",
        lambda: SessionContext(session),
    )
    comment = {
        "comment_id": "comment-not-a-number",
        "video_id": "av-not-a-number",
        "create_time": "1700000000",
        "like_count": 1,
        "sub_comment_count": 0,
    }

    await BiliDbStoreImplement().store_comment(comment)

    assert comment["comment_id"] == "comment-not-a-number"
    assert comment["video_id"] == "av-not-a-number"
    assert session.added[0].comment_id == "comment-not-a-number"
    assert session.added[0].video_id == "av-not-a-number"


@pytest.mark.asyncio
async def test_database_save_mode_initializes_schema_before_crawling(monkeypatch):
    main_module = importlib.import_module("main")
    crawler = SimpleNamespace(start=AsyncMock())
    init_db = AsyncMock()

    monkeypatch.setattr(
        main_module.cmd_arg,
        "parse_cmd",
        AsyncMock(return_value=SimpleNamespace(init_db=None)),
    )
    monkeypatch.setattr(main_module, "is_cdp_browser_running", lambda _: False)
    monkeypatch.setattr(main_module.db, "init_db", init_db)
    monkeypatch.setattr(
        main_module.CrawlerFactory,
        "create_crawler",
        lambda **_: crawler,
    )
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite")
    monkeypatch.setattr(config, "PLATFORM", "xhs")
    monkeypatch.setattr(main_module, "crawler", None)

    await main_module.main()

    init_db.assert_awaited_once_with("sqlite")
    crawler.start.assert_awaited_once()


def test_xhshow_uses_library_get_and_post_signers(monkeypatch):
    calls = []

    class FakeXhshow:
        def sign_headers_get(self, **kwargs):
            calls.append(("get", kwargs))
            return {
                "x-s": "get-s",
                "x-t": "get-t",
                "x-s-common": "get-common",
                "x-b3-traceid": "get-trace",
            }

        def sign_headers_post(self, **kwargs):
            calls.append(("post", kwargs))
            return {
                "x-s": "post-s",
                "x-t": "post-t",
                "x-s-common": "post-common",
                "x-b3-traceid": "post-trace",
            }

    fake_module = types.ModuleType("xhshow")
    fake_module.Xhshow = FakeXhshow
    monkeypatch.setitem(sys.modules, "xhshow", fake_module)

    get_headers = sign_with_xhshow(
        "/api/sns/web/v1/search/notes",
        {"keyword": "test"},
        "a1=test-cookie",
        "GET",
    )
    post_headers = sign_with_xhshow(
        "/api/sns/web/v1/search/notes",
        {"keyword": "test"},
        "a1=test-cookie",
        "POST",
    )

    assert get_headers["x-s"] == "get-s"
    assert post_headers["x-s"] == "post-s"
    assert calls == [
        (
            "get",
            {
                "uri": "/api/sns/web/v1/search/notes",
                "cookies": "a1=test-cookie",
                "params": {"keyword": "test"},
            },
        ),
        (
            "post",
            {
                "uri": "/api/sns/web/v1/search/notes",
                "cookies": "a1=test-cookie",
                "payload": {"keyword": "test"},
            },
        ),
    ]
