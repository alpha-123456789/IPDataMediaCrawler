# -*- coding: utf-8 -*-

import config
import pytest
from cmd_arg import parse_cmd
from media_platform.tieba import TieBaCrawler


@pytest.mark.asyncio
async def test_tieba_detail_cli_sets_specified_ids():
    await parse_cmd(
        [
            "--platform",
            "tieba",
            "--type",
            "detail",
            "--specified_id",
            "https://tieba.baidu.com/p/10451142633,9835114923",
        ]
    )

    assert config.TIEBA_SPECIFIED_ID_LIST == ["10451142633", "9835114923"]


@pytest.mark.asyncio
async def test_tieba_creator_cli_sets_creator_urls():
    await parse_cmd(
        [
            "--platform",
            "tieba",
            "--type",
            "creator",
            "--creator_id",
            "tb.1.example,https://tieba.baidu.com/home/main?id=tb.1.raw",
        ]
    )

    assert config.TIEBA_CREATOR_URL_LIST == [
        "https://tieba.baidu.com/home/main?id=tb.1.example",
        "https://tieba.baidu.com/home/main?id=tb.1.raw",
    ]


@pytest.mark.asyncio
async def test_cli_sets_per_keyword_sort_modes():
    args = await parse_cmd(
        [
            "--platform",
            "xhs",
            "--type",
            "search",
            "--keywords",
            "alpha,beta",
            "--keyword_sort_modes",
            '{"alpha": 0, "beta": 1}',
        ]
    )

    assert config.KEYWORD_SORT_MODES == {"alpha": 0, "beta": 1}
    assert args.keyword_sort_modes == {"alpha": 0, "beta": 1}


@pytest.mark.asyncio
async def test_cli_sets_per_keyword_xhs_note_time_filters():
    args = await parse_cmd(
        [
            "--platform",
            "xhs",
            "--type",
            "search",
            "--keywords",
            "alpha,beta",
            "--keyword_filter_note_times",
            '{"alpha": 0, "beta": 2}',
        ]
    )

    assert config.KEYWORD_FILTER_NOTE_TIMES == {"alpha": "不限", "beta": "一周内"}
    assert args.keyword_filter_note_times == {
        "alpha": "不限",
        "beta": "一周内",
    }


@pytest.mark.asyncio
async def test_cli_sets_per_keyword_max_note_counts():
    args = await parse_cmd(
        [
            "--platform",
            "xhs",
            "--type",
            "search",
            "--keywords",
            "alpha,beta",
            "--keyword_max_note_counts",
            '{"alpha": 12, "beta": 35}',
        ]
    )

    assert config.KEYWORD_MAX_NOTE_COUNTS == {"alpha": 12, "beta": 35}
    assert args.keyword_max_note_counts == {"alpha": 12, "beta": 35}


@pytest.mark.asyncio
async def test_tieba_detail_reads_runtime_specified_ids(monkeypatch):
    crawler = TieBaCrawler()
    seen_note_ids = []

    async def fake_get_note_detail(note_id, semaphore):
        seen_note_ids.append(note_id)
        return None

    async def fake_batch_get_comments(note_details):
        return None

    monkeypatch.setattr(config, "TIEBA_SPECIFIED_ID_LIST", ["10451142633"])
    monkeypatch.setattr(crawler, "get_note_detail_async_task", fake_get_note_detail)
    monkeypatch.setattr(crawler, "batch_get_note_comments", fake_batch_get_comments)

    await crawler.get_specified_notes()

    assert seen_note_ids == ["10451142633"]
