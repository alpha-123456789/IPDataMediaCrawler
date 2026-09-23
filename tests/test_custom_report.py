import builtins
import sys
from types import SimpleNamespace

from custom.keyword_insight.custom_report import (
    _build_llm_source,
    _build_report_metadata,
    _generate_custom_llm_report,
    build_custom_report,
    _date_string_where,
    _timestamp_where,
    FilteredPostRepository,
    parse_date_range,
    parse_post_ids,
)
from custom.keyword_insight.report_builder import (
    AI_FAILURE_MESSAGE,
    ReportBuilder,
    configured_llm_models,
    generate_llm_report,
)


def test_parse_date_range_includes_end_date():
    date_range = parse_date_range("2026-07-01", "2026-07-31")

    assert date_range.end_exclusive_date == "2026-08-01"
    assert date_range.end_ts - date_range.start_ts == 31 * 24 * 60 * 60


def test_parse_date_range_rejects_reverse_dates():
    try:
        parse_date_range("2026-08-01", "2026-07-31")
    except ValueError as exc:
        assert str(exc) == "开始日期不能晚于结束日期"
    else:
        raise AssertionError("Expected a ValueError")


def test_parse_post_ids_supports_space_comma_and_deduplication():
    assert parse_post_ids(["id-a,id-b", "id-a", " id-c "]) == [
        "id-a",
        "id-b",
        "id-c",
    ]


def test_repository_loads_only_selected_platform():
    repository = FilteredPostRepository(
        parse_date_range("2026-07-01", "2026-07-31"),
        "dy",
        ["123456"],
    )

    assert repository.platform == "dy"
    assert repository.post_ids == ["123456"]


def test_sql_filters_use_dates_and_selected_post_ids():
    date_range = parse_date_range("2026-07-01", "2026-07-31")

    timestamp_sql, timestamp_params = _timestamp_where(
        "create_time",
        date_range,
        "video_id",
        ["id-1", "id-2"],
    )
    date_sql, date_params = _date_string_where(
        "publish_time",
        date_range,
        "note_id",
        ["id-1"],
    )

    assert timestamp_sql == "create_time >= %s AND create_time < %s AND video_id IN (%s,%s)"
    assert timestamp_params == [date_range.start_ts, date_range.end_ts, "id-1", "id-2"]
    assert date_sql == "publish_time >= %s AND publish_time < %s AND note_id IN (%s)"
    assert date_params == ["2026-07-01", "2026-08-01", "id-1"]


def test_xhs_sql_filter_uses_millisecond_timestamps():
    date_range = parse_date_range("2026-07-01", "2026-07-31")

    sql, params = _timestamp_where(
        "time",
        date_range,
        "note_id",
        ["id-1"],
        multiplier=1000,
    )

    assert sql == "time >= %s AND time < %s AND note_id IN (%s)"
    assert params == [
        date_range.start_ts * 1000,
        date_range.end_ts * 1000,
        "id-1",
    ]


def test_zhihu_timestamp_normalizes_milliseconds():
    assert FilteredPostRepository._zhihu_timestamp("1785542400000") == 1785542400
    assert FilteredPostRepository._zhihu_timestamp("1785542400") == 1785542400


def test_report_builder_always_uses_ai_even_when_legacy_flag_is_false(monkeypatch):
    monkeypatch.setattr(
        ReportBuilder,
        "_build_llm_report",
        staticmethod(lambda *args, **kwargs: "AI report"),
    )

    report = ReportBuilder.build(
        "keyword",
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        {},
        {},
        {},
        {},
        [],
        {},
        use_llm=False,
    )

    assert report == "AI report"


def test_report_builder_returns_fixed_message_when_ai_is_unavailable(monkeypatch):
    original_import = builtins.__import__

    def import_without_anthropic(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("anthropic unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_anthropic)

    report = ReportBuilder._build_llm_report(
        "keyword",
        [],
        [],
        [],
        [],
        {},
        {},
        [],
        "",
    )

    assert report == AI_FAILURE_MESSAGE


def test_configured_llm_models_uses_primary_and_two_fallbacks(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_DEFAULT_HAIKU_MODEL", "primary")
    monkeypatch.setenv("ANTHROPIC_FALLBACK_MODEL_1", "secondary")
    monkeypatch.setenv("ANTHROPIC_FALLBACK_MODEL_2", "tertiary")

    assert configured_llm_models() == ["primary", "secondary", "tertiary"]


def test_generate_llm_report_uses_fallback_after_model_failure(monkeypatch):
    requested_models = []
    client_options = {}

    class FakeMessages:
        def create(self, *, model, **kwargs):
            requested_models.append(model)
            if model == "primary":
                raise RuntimeError("primary unavailable")
            return SimpleNamespace(content=[SimpleNamespace(text="备用模型报告")])

    class FakeClient:
        def __init__(self, **kwargs):
            client_options.update(kwargs)
            self.messages = FakeMessages()

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=FakeClient))
    monkeypatch.setenv("ANTHROPIC_DEFAULT_HAIKU_MODEL", "primary")
    monkeypatch.setenv("ANTHROPIC_FALLBACK_MODEL_1", "secondary")
    monkeypatch.setenv("ANTHROPIC_FALLBACK_MODEL_2", "tertiary")

    assert generate_llm_report("prompt", max_tokens=100) == "备用模型报告"
    assert requested_models == ["primary", "secondary"]
    assert client_options["timeout"] == 110


def test_llm_source_limits_samples_and_text(monkeypatch):
    monkeypatch.setenv("LLM_SOURCE_MAX_POSTS", "1")
    monkeypatch.setenv("LLM_SOURCE_MAX_COMMENTS", "1")
    monkeypatch.setenv("LLM_SOURCE_MAX_POST_TEXT", "4")
    monkeypatch.setenv("LLM_SOURCE_MAX_COMMENT_TEXT", "3")

    source = _build_llm_source(
        [
            {"note_id": "low", "desc": "低互动帖子", "liked_count": 1},
            {"note_id": "high", "desc": "高互动帖子正文", "liked_count": 10},
        ],
        [
            {"note_id": "low", "content": "低互动评论", "like_count": 1},
            {"note_id": "high", "content": "高互动评论正文", "like_count": 10},
        ],
    )

    assert source["posts"] == [{
        "id": "high",
        "platform": None,
        "title": "",
        "content": "高互动帖",
        "likes": 10,
        "comments": 0,
    }]
    assert source["comments"] == [{
        "post_id": "high",
        "content": "高互动",
        "likes": 10,
        "replies": 0,
    }]


def test_report_metadata_keeps_counts_without_duplicate_raw_samples():
    metadata = _build_report_metadata(
        parse_date_range("2026-07-01", "2026-07-31"),
        "xhs",
        [],
        [{}],
        [{}],
        [],
        1,
        [{
            "topic": "剧情",
            "count": 2,
            "percent": 50,
            "sample_texts": ["不应进入最终元数据"],
        }],
        [{
            "concern": "内容质量",
            "count": 3,
            "raw_samples": ["不应重复发送"],
            "subclusters": [{
                "name": "剧情节奏",
                "count": 2,
                "sample_texts": ["不应重复发送"],
            }],
        }],
        {
            "distribution": {"positive": 50, "neutral": 50, "negative": 0},
            "positive_quotes": ["不应重复发送"],
            "emotion_subcategories": {
                "喜爱": {"count": 2, "samples": ["不应重复发送"]},
            },
        },
        {"total_likes": 10},
    )

    serialized = str(metadata)
    assert metadata["topics"][0]["count"] == 2
    assert metadata["concerns"][0]["count"] == 3
    assert metadata["sentiment"]["emotion_subcategories"]["喜爱"]["count"] == 2
    assert "不应重复发送" not in serialized


def _custom_llm_args(note_count):
    notes = [
        {
            "note_id": f"post-{index}",
            "title": f"标题 {index}",
            "desc": f"正文 {index}",
            "liked_count": index,
            "comment_count": 1,
        }
        for index in range(note_count)
    ]
    comments = [
        {
            "note_id": f"post-{index}",
            "content": f"评论 {index}",
            "like_count": index,
        }
        for index in range(note_count)
    ]
    return (
        "分析用户反馈",
        parse_date_range("2026-07-01", "2026-07-31"),
        "xhs",
        [],
        notes,
        comments,
        [],
        note_count,
        [],
        [],
        {},
        {"total_likes": sum(range(note_count))},
    )


def test_custom_llm_report_does_not_batch_up_to_100_posts(monkeypatch):
    requests = []

    def fake_generate(prompt, max_tokens):
        requests.append((prompt, max_tokens))
        return "最终报告"

    monkeypatch.setattr(
        "custom.keyword_insight.custom_report.generate_llm_report",
        fake_generate,
    )

    report = _generate_custom_llm_report(*_custom_llm_args(100))

    assert report == "最终报告"
    assert len(requests) == 1
    assert "第 1/" not in requests[0][0]
    assert '"id": "post-0"' in requests[0][0]
    assert '"id": "post-99"' in requests[0][0]


def test_custom_llm_report_batches_every_100_posts_then_merges(monkeypatch):
    requests = []

    def fake_generate(prompt, max_tokens):
        requests.append((prompt, max_tokens))
        if "第 1/2 批" in prompt:
            return "第一批摘要"
        if "第 2/2 批" in prompt:
            return "第二批摘要"
        return "最终报告"

    monkeypatch.setattr(
        "custom.keyword_insight.custom_report.generate_llm_report",
        fake_generate,
    )

    report = _generate_custom_llm_report(*_custom_llm_args(101))

    assert report == "最终报告"
    assert len(requests) == 3
    assert requests[0][1] == 700
    assert requests[1][1] == 700
    assert requests[2][1] == 1200
    assert "本批包含 100 篇帖子" in requests[0][0]
    assert "本批包含 1 篇帖子" in requests[1][0]
    assert "第一批摘要" in requests[2][0]
    assert "第二批摘要" in requests[2][0]


def test_custom_llm_report_stops_when_a_batch_fails(monkeypatch):
    requests = []

    def fake_generate(prompt, max_tokens):
        requests.append(prompt)
        return None if "第 2/2 批" in prompt else "第一批摘要"

    monkeypatch.setattr(
        "custom.keyword_insight.custom_report.generate_llm_report",
        fake_generate,
    )

    report = _generate_custom_llm_report(*_custom_llm_args(101))

    assert report is None
    assert len(requests) == 2


def test_generate_llm_report_returns_none_after_all_models_fail(monkeypatch):
    requested_models = []

    class FakeMessages:
        def create(self, *, model, **kwargs):
            requested_models.append(model)
            raise RuntimeError(f"{model} unavailable")

    class FakeClient:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=FakeClient))
    monkeypatch.setenv("ANTHROPIC_DEFAULT_HAIKU_MODEL", "primary")
    monkeypatch.setenv("ANTHROPIC_FALLBACK_MODEL_1", "secondary")
    monkeypatch.setenv("ANTHROPIC_FALLBACK_MODEL_2", "tertiary")

    assert generate_llm_report("prompt", max_tokens=100) is None
    assert requested_models == ["primary", "secondary", "tertiary"]


def test_custom_report_returns_fixed_message_when_ai_fails(monkeypatch):
    class StubAnalyzer:
        def clean_text(self, text):
            return text

        def __getattr__(self, name):
            return lambda *args, **kwargs: {} if name.startswith("analyze_") else None

    monkeypatch.setattr(
        "custom.keyword_insight.custom_report.Analyzer",
        StubAnalyzer,
    )
    monkeypatch.setattr(
        "custom.keyword_insight.custom_report._generate_custom_llm_report",
        lambda *args, **kwargs: None,
    )

    report, *_ = build_custom_report(
        "分析要求",
        parse_date_range("2026-07-01", "2026-07-31"),
        "dy",
        [],
        [{"title": "标题", "desc": "正文"}],
        [],
        [],
        0,
        use_llm=False,
    )

    assert report == AI_FAILURE_MESSAGE
