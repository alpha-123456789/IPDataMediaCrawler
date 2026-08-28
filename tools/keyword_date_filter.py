"""Keyword-specific publication date filtering for search results."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import config


PUBLICATION_TIMEZONE = ZoneInfo("Asia/Shanghai")
_DATE_FIELDS = (
    "time",
    "create_time",
    "createTime",
    "publish_time",
    "publishTime",
    "timestamp",
    "created_at",
    "createdAt",
    "pubdate",
)
_NESTED_DATE_FIELDS = ("note_card", "photo", "mblog", "aweme_info")


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(
                timestamp, tz=PUBLICATION_TIMEZONE
            ).date()
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None
    today = datetime.now(PUBLICATION_TIMEZONE).date()
    if text == "刚刚":
        return today
    if text.endswith("小时前") and text[:-3].isdigit():
        return today
    if text.startswith("昨天"):
        return today - timedelta(days=1)
    if text.endswith("天前") and text[:-2].isdigit():
        return today - timedelta(days=int(text[:-2]))
    try:
        return _parse_date(float(text))
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        try:
            month_day = datetime.strptime(text[:5], "%m-%d").date()
            result = date(today.year, month_day.month, month_day.day)
            return result if result <= today else date(today.year - 1, month_day.month, month_day.day)
        except ValueError:
            pass
        try:
            return parsedate_to_datetime(text).date()
        except (TypeError, ValueError, IndexError):
            return None


def normalize_keyword_date_ranges(raw_ranges: Any) -> dict[str, dict[str, str]]:
    """Normalize and validate keyword date ranges from the crawler command."""
    if not raw_ranges:
        return {}
    if not isinstance(raw_ranges, Mapping):
        raise ValueError("keyword_date_ranges must be a JSON object")

    normalized: dict[str, dict[str, str]] = {}
    for raw_keyword, raw_range in raw_ranges.items():
        keyword = str(raw_keyword).strip()
        if not keyword:
            continue
        if not isinstance(raw_range, Mapping):
            raise ValueError(f"日期范围格式错误，关键词 '{keyword}' 的范围必须是对象")

        start = _parse_date(raw_range.get("start_date"))
        end = _parse_date(raw_range.get("end_date"))
        if not start and not end:
            continue
        if start and end and start > end:
            raise ValueError(
                f"日期范围错误，关键词 '{keyword}' 的 start_date 不能晚于 end_date"
            )

        normalized[keyword] = {
            "start_date": start.isoformat() if start else "",
            "end_date": end.isoformat() if end else "",
        }
    return normalized


def get_keyword_date_range(keyword: str) -> tuple[date | None, date | None] | None:
    date_ranges = getattr(config, "KEYWORD_DATE_RANGES", {})
    raw_range = date_ranges.get(keyword)
    if not raw_range:
        return None

    return _parse_date(raw_range.get("start_date")), _parse_date(
        raw_range.get("end_date")
    )


def extract_publication_time(post: Mapping[str, Any]) -> Any:
    """Extract the search-result publication time across supported platforms."""
    for field in _DATE_FIELDS:
        if post.get(field) not in (None, ""):
            return post[field]

    for parent_field in _NESTED_DATE_FIELDS:
        nested = post.get(parent_field)
        if not isinstance(nested, Mapping):
            continue
        for field in _DATE_FIELDS:
            if nested.get(field) not in (None, ""):
                return nested[field]
        if parent_field == "note_card":
            for tag in nested.get("corner_tag_info", []):
                if (
                    isinstance(tag, Mapping)
                    and tag.get("type") == "publish_time"
                    and tag.get("text") not in (None, "")
                ):
                    return tag["text"]
    return None


def is_post_within_keyword_date_range(keyword: str, publication_time: Any) -> bool:
    """Return whether a search result may proceed to detail/comment crawling."""
    date_range = get_keyword_date_range(keyword)
    if date_range is None:
        return True

    publication_date = _parse_date(publication_time)
    if publication_date is None:
        return False

    start, end = date_range
    return (start is None or publication_date >= start) and (
        end is None or publication_date <= end
    )
