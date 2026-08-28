import json

import config
import pytest

from custom.keyword_runner import KeywordRunner
from media_platform.bilibili.core import _get_keyword_search_order
from media_platform.xhs.client import XiaoHongShuClient
from media_platform.bilibili.field import SearchOrderType
from media_platform.xhs.core import _get_keyword_sort_type
from media_platform.xhs.field import SearchSortType


def test_xhs_keyword_sort_mode_overrides_platform_default(monkeypatch):
    monkeypatch.setattr(config, "SORT_TYPE", "popularity_descending")
    monkeypatch.setattr(config, "KEYWORD_SORT_MODES", {"alpha": 1, "beta": 0})

    assert _get_keyword_sort_type("alpha") is SearchSortType.LATEST
    assert _get_keyword_sort_type("beta") is SearchSortType.GENERAL
    assert _get_keyword_sort_type("other") is SearchSortType.MOST_POPULAR


def test_bilibili_keyword_sort_mode_uses_publish_date(monkeypatch):
    monkeypatch.setattr(config, "KEYWORD_SORT_MODES", {"alpha": 1, "beta": 0})

    assert _get_keyword_search_order("alpha") is SearchOrderType.LAST_PUBLISH
    assert _get_keyword_search_order("beta") is SearchOrderType.DEFAULT


def test_legacy_keyword_runner_forwards_sort_mode(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command

    monkeypatch.setattr("custom.keyword_runner.subprocess.run", fake_run)
    runner = KeywordRunner({"platform": "xhs", "cmd_args": []})

    runner.run_keyword("alpha", 1)

    option_index = captured["command"].index("--keyword_sort_modes")
    assert json.loads(captured["command"][option_index + 1]) == {"alpha": 1}


def test_legacy_keyword_runner_only_forwards_xhs_note_time_filter(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command

    monkeypatch.setattr("custom.keyword_runner.subprocess.run", fake_run)
    runner = KeywordRunner({"platform": "bili", "cmd_args": []})

    runner.run_keyword("alpha", 0, 2)

    assert "--keyword_filter_note_times" not in captured["command"]


@pytest.mark.asyncio
async def test_xhs_search_request_uses_web_filter_shape(monkeypatch):
    client = XiaoHongShuClient(
        headers={},
        playwright_page=None,
        cookie_dict={},
    )
    captured = {}

    async def fake_post(uri, data, **kwargs):
        captured["uri"] = uri
        captured["data"] = data
        return {}

    monkeypatch.setattr(client, "post", fake_post)

    await client.get_note_by_keyword(
        "alpha",
        sort=SearchSortType.LATEST,
        filter_note_time="一周内",
    )

    assert captured["uri"] == "/api/sns/web/v1/search/notes"
    assert captured["data"]["sort"] == "general"
    assert captured["data"]["filters"] == [
        {"tags": ["time_descending"], "type": "sort_type"},
        {"tags": ["不限"], "type": "filter_note_type"},
        {"tags": ["一周内"], "type": "filter_note_time"},
        {"tags": ["不限"], "type": "filter_note_range"},
        {"tags": ["不限"], "type": "filter_pos_distance"},
    ]
