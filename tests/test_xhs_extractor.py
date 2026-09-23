import json

import pytest

from media_platform.xhs.extractor import XiaoHongShuExtractor


def test_creator_initial_state_supports_javascript_value_literals():
    html = """
        <script>
            window.__INITIAL_STATE__ = {
                "user": {
                    "userPageData": {
                        "name": "undefined and NaN stay unchanged in strings",
                        "items": [undefined, NaN, Infinity, -Infinity],
                        "nested": {"value" : undefined}
                    }
                }
            };
        </script>
    """

    creator = XiaoHongShuExtractor().extract_creator_info_from_html(html)

    assert creator == {
        "name": "undefined and NaN stay unchanged in strings",
        "items": [None, None, None, None],
        "nested": {"value": None},
    }


def test_creator_initial_state_stops_at_balanced_object_boundary():
    html = (
        '<script>window.__INITIAL_STATE__={"user":{"userPageData":'
        '{"bio":"brace } and </script> text"}}};</script>'
        '<script>window.extra={"invalid":undefined};</script>'
    )

    creator = XiaoHongShuExtractor().extract_creator_info_from_html(html)

    assert creator == {"bio": "brace } and </script> text"}


def test_creator_initial_state_supports_set_constructor():
    html = (
        '<script>window.__INITIAL_STATE__={"user":{"userPageData":'
        '{"selectedIds":new Set([]),"excludedIds":new Set(["a", undefined])}}};'
        "</script>"
    )

    creator = XiaoHongShuExtractor().extract_creator_info_from_html(html)

    assert creator == {"selectedIds": [], "excludedIds": ["a", None]}


def test_creator_initial_state_keeps_unknown_javascript_syntax_visible():
    html = (
        '<script>window.__INITIAL_STATE__={"user":{"userPageData":'
        '{"value":void 0}}};</script>'
    )

    with pytest.raises(json.JSONDecodeError):
        XiaoHongShuExtractor().extract_creator_info_from_html(html)
