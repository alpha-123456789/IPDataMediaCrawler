from importlib import import_module
from unittest.mock import AsyncMock

import pytest

import config
from model.m_baidu_tieba import TiebaNote
from model.m_zhihu import ZhihuContent
from tools.keyword_content_filter import content_matches_keyword
from var import source_keyword_var


KEYWORD = "\u5c41\u5c41\u4fa6\u63a2"


@pytest.fixture(autouse=True)
def keyword_context(monkeypatch):
    monkeypatch.setattr(config, "KEYWORDS", KEYWORD)
    monkeypatch.setattr(config, "CRAWLER_TYPE", "search")
    token = source_keyword_var.set(KEYWORD)
    yield
    source_keyword_var.reset(token)


@pytest.mark.parametrize(
    "content",
    [
        {"title": KEYWORD, "desc": None},
        {"title": None, "desc": KEYWORD},
        {"caption": KEYWORD},
        {"description": KEYWORD},
        {"summary": KEYWORD},
        {"intro": KEYWORD},
        {"content_text": KEYWORD},
        {"text_raw": KEYWORD},
        {"longText": {"longTextContent": KEYWORD}},
        {"View": {"title": "", "desc": KEYWORD}},
        {"photo": {"caption": KEYWORD}},
        {"mblog": {"page_info": {"page_title": "other", "content": KEYWORD}}},
        {"mblog": {"page_info": {"page_title": KEYWORD}}},
        {"tag_list": [{"name": KEYWORD}]},
        {"Tags": [{"tag_name": KEYWORD}]},
        {"text_extra": [{"hashtag_name": KEYWORD}]},
        {"cha_list": [{"cha_name": KEYWORD}]},
        {"desc_v2": [{"text": KEYWORD}]},
        {"View": {"pages": [{"part": KEYWORD}]}},
        ZhihuContent(title=KEYWORD),
    ],
)
def test_matches_any_post_text_field(content):
    assert content_matches_keyword(content, KEYWORD)


@pytest.mark.parametrize(
    "content",
    [
        None,
        {},
        {"title": None, "desc": None},
        {"title": KEYWORD[:2], "desc": KEYWORD[2:]},
        {"source_keyword": KEYWORD, "request_keyword": KEYWORD},
        {"author": {"nickname": KEYWORD, "signature": KEYWORD}},
        {"user": {"desc": KEYWORD}, "nickname": KEYWORD},
        {"Card": {"card": {"sign": KEYWORD}}},
        {"video_url": "https://example.com/" + KEYWORD},
        {"text_extra": [{"user_name": KEYWORD}]},
        {"comments": [{"content": KEYWORD}]},
        {"text": '<a href="https://example.com/' + KEYWORD + '">other</a>'},
        {"text": "<script>" + KEYWORD + "</script><style>" + KEYWORD + "</style>"},
    ],
)
def test_metadata_and_missing_text_cannot_satisfy_keyword(content):
    assert not content_matches_keyword(content, KEYWORD)


def test_matches_visible_html_with_highlighting_and_entities():
    assert content_matches_keyword(
        {"text": "<b>" + KEYWORD[:2] + "</b>" + KEYWORD[2:]}, KEYWORD
    )
    assert content_matches_keyword({"text": "&#23617;&#23617;&#20390;&#25506;"}, KEYWORD)


def test_search_requires_current_keyword_not_another_configured_keyword(monkeypatch):
    monkeypatch.setattr(config, "KEYWORDS", KEYWORD + ",other")
    assert not content_matches_keyword({"title": "other"})
    assert content_matches_keyword({"title": KEYWORD})


@pytest.mark.parametrize("mode", ["detail", "creator"])
def test_non_search_modes_use_any_configured_keyword(monkeypatch, mode):
    monkeypatch.setattr(config, "CRAWLER_TYPE", mode)
    monkeypatch.setattr(config, "KEYWORDS", " alpha, beta ")
    assert content_matches_keyword({"title": "beta"})
    assert content_matches_keyword({"desc": "alpha"})
    assert not content_matches_keyword({"title": KEYWORD})


def test_missing_keyword_never_matches_every_post(monkeypatch):
    monkeypatch.setattr(config, "KEYWORDS", " , ")
    source_keyword_var.set("")
    assert not content_matches_keyword({"title": "anything"})
    assert not content_matches_keyword({"title": "anything"}, "")


def test_zhihu_answer_can_match_its_question_title():
    from media_platform.zhihu.help import ZhihuExtractor

    answer = {
        "id": "1", "type": "answer", "question": {"id": "2", "title": KEYWORD},
        "content": "unrelated", "created_time": 1, "updated_time": 1,
    }
    content = ZhihuExtractor()._extract_answer_content(answer)

    assert content.title == KEYWORD
    assert content_matches_keyword(content)


@pytest.mark.parametrize("body", ["x" * 600 + KEYWORD, ""])
def test_tieba_matches_full_first_floor_body_with_meta_fallback(body):
    from media_platform.tieba.help import TieBaExtractor

    meta = KEYWORD if not body else "unrelated"
    html = (
        '<html><head><title>unrelated</title>'
        f'<meta name="description" content="{meta}"></head><body>'
        '<div class="l_post j_l_post"><div class="d_post_content">'
        f"{body}</div></div>"
        '<div class="l_post j_l_post"><div class="d_post_content">'
        "reply</div></div></body></html>"
    )
    note = TieBaExtractor().extract_note_detail(html)

    assert note.desc == (body or meta)
    assert content_matches_keyword(note)


def test_tieba_does_not_use_replies_as_post_text():
    from media_platform.tieba.help import TieBaExtractor

    html = (
        "<html><head><title>unrelated</title></head><body>"
        '<div class="l_post j_l_post"><div class="d_post_content">'
        "unrelated</div></div>"
        '<div class="l_post j_l_post"><div class="d_post_content">'
        f"{KEYWORD}</div></div></body></html>"
    )

    assert not content_matches_keyword(TieBaExtractor().extract_note_detail(html))


def _post(platform, text):
    if platform == "douyin":
        return {"aweme_id": "1", "desc": text}
    if platform == "kuaishou":
        return {"photo": {"id": "1", "caption": text}}
    if platform == "bilibili":
        return {"View": {"aid": 1, "title": "", "desc": text, "owner": {}, "stat": {}}}
    if platform == "xhs":
        return {"note_id": "1", "title": "", "desc": text}
    if platform == "weibo":
        return {
            "mblog": {
                "id": "1", "text": text, "user": {},
                "created_at": "Wed Oct 14 12:00:00 +0800 2026",
            }
        }
    if platform == "zhihu":
        return ZhihuContent(content_id="1", content_text=text)
    return TiebaNote(
        note_id="1", title="", desc=text, note_url="https://tieba.baidu.com/p/1",
        tieba_name="test", tieba_link="https://tieba.baidu.com/f?kw=test",
    )


PLATFORM_STORES = [
    ("douyin", "DouyinStoreFactory", "update_douyin_aweme"),
    ("kuaishou", "KuaishouStoreFactory", "update_kuaishou_video"),
    ("bilibili", "BiliStoreFactory", "update_bilibili_video"),
    ("xhs", "XhsStoreFactory", "update_xhs_note"),
    ("weibo", "WeibostoreFactory", "update_weibo_note"),
    ("zhihu", "ZhihuStoreFactory", "update_zhihu_content"),
    ("tieba", "TieBaStoreFactory", "update_tieba_note"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("platform,factory_name,save_name", PLATFORM_STORES)
@pytest.mark.parametrize("mode", ["search", "detail", "creator"])
async def test_all_platform_stores_reject_unrelated_posts_in_every_mode(
    monkeypatch, platform, factory_name, save_name, mode,
):
    monkeypatch.setattr(config, "CRAWLER_TYPE", mode)
    module = import_module("store." + platform)
    backend = AsyncMock()
    monkeypatch.setattr(
        getattr(module, factory_name), "create_store", lambda: backend
    )
    save = getattr(module, save_name)

    await save(_post(platform, "unrelated"))
    backend.store_content.assert_not_awaited()

    # Match the full text even when the keyword appears after stored truncation limits.
    await save(_post(platform, "x" * 600 + KEYWORD))
    backend.store_content.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "platform,factory_name,save_name",
    [entry for entry in PLATFORM_STORES if entry[0] in {"bilibili", "kuaishou", "xhs", "weibo"}],
)
async def test_other_text_match_saves_even_when_primary_text_is_null(
    monkeypatch, platform, factory_name, save_name,
):
    module = import_module("store." + platform)
    backend = AsyncMock()
    monkeypatch.setattr(getattr(module, factory_name), "create_store", lambda: backend)
    post = _post(platform, None)
    if platform == "bilibili":
        post["View"]["title"] = None
    if platform == "xhs":
        post["title"] = None
    post["summary"] = KEYWORD

    await getattr(module, save_name)(post)

    backend.store_content.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "platform,crawler_name,entrypoint,fetch,comment,setting,media",
    [
        ("douyin", "DouYinCrawler", "get_specified_awemes", "get_aweme_detail",
         "batch_get_note_comments", "DY_SPECIFIED_ID_LIST", "get_aweme_media"),
        ("kuaishou", "KuaishouCrawler", "get_specified_videos", "get_video_info_task",
         "batch_get_video_comments", "KS_SPECIFIED_ID_LIST", None),
        ("bilibili", "BilibiliCrawler", "get_specified_videos", "get_video_info_task",
         "batch_get_video_comments", None, "get_bilibili_video"),
        ("xhs", "XiaoHongShuCrawler", "get_specified_notes", "get_note_detail_async_task",
         "batch_get_note_comments", "XHS_SPECIFIED_NOTE_URL_LIST", "get_notice_media"),
        ("weibo", "WeiboCrawler", "get_specified_notes", "get_note_info_task",
         "batch_get_notes_comments", "WEIBO_SPECIFIED_ID_LIST", None),
        ("zhihu", "ZhihuCrawler", "get_specified_notes", "get_note_detail",
         "batch_get_content_comments", "ZHIHU_SPECIFIED_ID_LIST", None),
        ("tieba", "TieBaCrawler", "get_specified_notes", "get_note_detail_async_task",
         "batch_get_note_comments", "TIEBA_SPECIFIED_ID_LIST", None),
    ],
)
async def test_detail_flows_only_save_and_fetch_comments_for_matching_posts(
    monkeypatch, platform, crawler_name, entrypoint, fetch, comment, setting, media,
):
    monkeypatch.setattr(config, "CRAWLER_TYPE", "detail")
    core = import_module("media_platform." + platform + ".core")
    crawler = getattr(core, crawler_name)()
    unrelated, matched = _post(platform, "unrelated"), _post(platform, KEYWORD)
    monkeypatch.setattr(crawler, fetch, AsyncMock(side_effect=[unrelated, matched]))
    comments = AsyncMock()
    monkeypatch.setattr(crawler, comment, comments)
    media_fetch = AsyncMock()
    if media:
        monkeypatch.setattr(crawler, media, media_fetch)
    save_name = next(entry[2] for entry in PLATFORM_STORES if entry[0] == platform)
    save = AsyncMock()
    monkeypatch.setattr(import_module("store." + platform), save_name, save)
    if platform == "bilibili":
        monkeypatch.setattr(core.bilibili_store, "update_up_info", AsyncMock())
        await getattr(crawler, entrypoint)(["BV1", "BV2"])
    else:
        monkeypatch.setattr(config, setting, ["1", "2"])
        await getattr(crawler, entrypoint)()

    assert save.await_count == 1
    assert (save.await_args.args or tuple(save.await_args.kwargs.values())) == (matched,)
    if media:
        assert media_fetch.await_count == 1
    expected = [matched] if platform in {"zhihu", "tieba"} else [1 if platform == "bilibili" else "1"]
    if platform == "xhs":
        comments.assert_awaited_once_with(expected, [""])
    else:
        comments.assert_awaited_once_with(expected)


@pytest.mark.asyncio
async def test_bilibili_creator_dynamics_require_matching_text(monkeypatch):
    from store import bilibili

    monkeypatch.setattr(config, "CRAWLER_TYPE", "creator")
    backend = AsyncMock()
    monkeypatch.setattr(bilibili.BiliStoreFactory, "create_store", lambda: backend)
    creator = {"id": "1", "name": KEYWORD}
    dynamic = {
        "dynamic_id": "2", "text": "unrelated", "type": "WORD",
        "pub_ts": 1, "total_comments": 0, "total_forwards": 0, "total_liked": 0,
    }

    await bilibili.update_bilibili_creator_dynamic(creator, dynamic)
    backend.store_dynamic.assert_not_awaited()
    dynamic["text"] = KEYWORD
    await bilibili.update_bilibili_creator_dynamic(creator, dynamic)
    backend.store_dynamic.assert_awaited_once()


@pytest.mark.asyncio
async def test_kuaishou_search_filters_before_limit_and_comment_fetch(monkeypatch):
    from media_platform.kuaishou import core

    monkeypatch.setattr(config, "START_PAGE", 1)
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 1)
    monkeypatch.setattr(config, "KEYWORD_MAX_NOTE_COUNTS", {})
    monkeypatch.setattr(config, "KEYWORD_DATE_RANGES", {})
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(core, "emit_keyword_completed", lambda *args: None)
    dedup = AsyncMock(side_effect=lambda platform, ids: ids)
    monkeypatch.setattr(core, "filter_uncrawled_note_ids", dedup)
    save = AsyncMock()
    monkeypatch.setattr(core.kuaishou_store, "update_kuaishou_video", save)
    unrelated = {"photo": {"id": "1", "caption": "unrelated"}, "author": {"name": KEYWORD}}
    matched = {"photo": {"id": "2", "caption": KEYWORD}}
    crawler = core.KuaishouCrawler()
    crawler.ks_client = AsyncMock()
    crawler.ks_client.search_info_by_keyword_v2.return_value = {
        "result": 1, "feeds": [unrelated, matched],
    }
    crawler.batch_get_video_comments = AsyncMock()

    await crawler.search()

    save.assert_awaited_once_with(video_item=matched)
    dedup.assert_awaited_once_with("ks", ["2"])
    crawler.batch_get_video_comments.assert_awaited_once_with(["2"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["normal", "all_in_time_range", "daily_limit_in_time_range"]
)
async def test_bilibili_all_search_modes_filter_posts_and_comments(monkeypatch, mode):
    from media_platform.bilibili import core

    monkeypatch.setattr(config, "BILI_SEARCH_MODE", mode)
    monkeypatch.setattr(config, "START_PAGE", 1)
    monkeypatch.setattr(config, "START_DAY", "2026-10-14")
    monkeypatch.setattr(config, "END_DAY", "2026-10-14")
    monkeypatch.setattr(config, "MAX_NOTES_PER_DAY", 10)
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 10)
    monkeypatch.setattr(config, "KEYWORD_MAX_NOTE_COUNTS", {})
    monkeypatch.setattr(config, "KEYWORD_DATE_RANGES", {})
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(core, "emit_keyword_completed", lambda *args: None)
    monkeypatch.setattr(
        core, "filter_uncrawled_note_ids",
        AsyncMock(side_effect=lambda platform, ids: ids),
    )
    monkeypatch.setattr(
        core, "filter_note_ids_needing_comment_recovery", AsyncMock(return_value=[])
    )
    save = AsyncMock()
    monkeypatch.setattr(core.bilibili_store, "update_bilibili_video", save)
    update_up = AsyncMock()
    monkeypatch.setattr(core.bilibili_store, "update_up_info", update_up)
    details = {
        1: {"View": {"aid": 1, "title": "unrelated", "desc": None}},
        2: {"View": {"aid": 2, "title": None, "desc": KEYWORD}},
        3: {"View": {"aid": 3, "title": KEYWORD, "desc": ""}},
    }
    crawler = core.BilibiliCrawler()
    crawler.bili_client = AsyncMock()
    crawler.bili_client.search_video_by_keyword.side_effect = [
        {"result": [{"aid": aid} for aid in details]}, {"result": []},
    ]
    crawler.get_video_info_task = AsyncMock(
        side_effect=lambda aid, **kwargs: details[aid]
    )
    crawler.get_bilibili_video = AsyncMock()
    crawler.batch_get_video_comments = AsyncMock()

    await crawler.search()

    assert [call.args[0] for call in save.await_args_list] == [details[2], details[3]]
    assert update_up.await_count == 2
    assert crawler.get_bilibili_video.await_count == 2
    crawler.batch_get_video_comments.assert_awaited_once_with([2, 3])
