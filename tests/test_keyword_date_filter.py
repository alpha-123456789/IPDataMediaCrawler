from datetime import date, datetime, timezone

import pytest

import config
from tools.keyword_date_filter import (
    extract_publication_time,
    is_post_within_keyword_date_range,
    normalize_keyword_date_ranges,
)


@pytest.fixture(autouse=True)
def clear_keyword_date_ranges(monkeypatch):
    monkeypatch.setattr(config, "KEYWORD_DATE_RANGES", {})


def test_keyword_date_range_is_inclusive_and_skips_unknown_publication_time(monkeypatch):
    monkeypatch.setattr(
        config,
        "KEYWORD_DATE_RANGES",
        {"alpha": {"start_date": "2026-08-01", "end_date": "2026-08-31"}},
    )

    assert is_post_within_keyword_date_range("alpha", date(2026, 8, 1))
    assert is_post_within_keyword_date_range("alpha", date(2026, 8, 31))
    assert not is_post_within_keyword_date_range("alpha", date(2026, 7, 31))
    assert not is_post_within_keyword_date_range("alpha", None)


def test_unix_timestamp_uses_china_publication_date(monkeypatch):
    monkeypatch.setattr(
        config,
        "KEYWORD_DATE_RANGES",
        {"alpha": {"start_date": "2026-08-01", "end_date": "2026-08-01"}},
    )
    timestamp = datetime(2026, 7, 31, 16, 30, tzinfo=timezone.utc).timestamp()

    assert is_post_within_keyword_date_range("alpha", timestamp)


def test_numeric_string_timestamp_uses_china_publication_date(monkeypatch):
    monkeypatch.setattr(
        config,
        "KEYWORD_DATE_RANGES",
        {"alpha": {"start_date": "2026-08-01", "end_date": "2026-08-01"}},
    )
    timestamp = int(
        datetime(2026, 7, 31, 16, 30, tzinfo=timezone.utc).timestamp()
    )

    assert is_post_within_keyword_date_range("alpha", str(timestamp))
    assert is_post_within_keyword_date_range("alpha", str(timestamp * 1000))


def test_keyword_without_date_range_is_not_filtered():
    assert is_post_within_keyword_date_range("alpha", None)


def test_extract_publication_time_supports_search_result_shapes():
    assert extract_publication_time({"pubdate": 1}) == 1
    assert extract_publication_time({"photo": {"timestamp": 2}}) == 2
    assert extract_publication_time({"mblog": {"created_at": "2026-08-01"}}) == "2026-08-01"
    assert extract_publication_time({"note_card": {"time": 3}}) == 3
    assert extract_publication_time(
        {
            "note_card": {
                "corner_tag_info": [
                    {"type": "publish_time", "text": "昨天 20:39"},
                ]
            }
        }
    ) == "昨天 20:39"


def test_xhs_relative_publication_time_uses_keyword_date_range(monkeypatch):
    monkeypatch.setattr(
        config,
        "KEYWORD_DATE_RANGES",
        {"alpha": {"start_date": "2026-08-26", "end_date": "2026-08-26"}},
    )

    assert is_post_within_keyword_date_range("alpha", "昨天 20:39")
    assert is_post_within_keyword_date_range("alpha", "1天前")
    assert not is_post_within_keyword_date_range("alpha", "2天前")


def test_xhs_same_day_relative_publication_time_uses_keyword_date_range(monkeypatch):
    monkeypatch.setattr(
        config,
        "KEYWORD_DATE_RANGES",
        {"alpha": {"start_date": "2026-08-27", "end_date": "2026-08-27"}},
    )

    assert is_post_within_keyword_date_range("alpha", "刚刚")
    assert is_post_within_keyword_date_range("alpha", "5小时前")


def test_normalize_keyword_date_ranges_rejects_reversed_dates():
    with pytest.raises(ValueError, match="start_date"):
        normalize_keyword_date_ranges(
            {"alpha": {"start_date": "2026-09-01", "end_date": "2026-08-31"}}
        )
