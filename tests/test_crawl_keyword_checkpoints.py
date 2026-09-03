import io
import json
from datetime import datetime

import crawl_all_keywords
import pytest
from tools.crawl_progress import PROGRESS_PREFIX


class _FakeProcess:
    def __init__(self, lines, returncode=0):
        self.stdout = io.StringIO("".join(lines))
        self.returncode = returncode

    def wait(self):
        return self.returncode


def test_run_crawl_forwards_keyword_checkpoint(monkeypatch):
    captured = {}

    def fake_popen(*args, **kwargs):
        captured["env"] = kwargs["env"]
        return _FakeProcess(
            [
                "ordinary crawler output\n",
                (
                    f'{PROGRESS_PREFIX}'
                    '{"event":"keyword_completed","platform":"dy","keyword":"alpha"}\n'
                ),
            ]
        )

    monkeypatch.setattr(crawl_all_keywords.subprocess, "Popen", fake_popen)
    completed = []

    ok = crawl_all_keywords.run_crawl(
        "dy",
        ["alpha", "beta"],
        on_keyword_completed=completed.append,
    )

    assert ok is True
    assert completed == ["alpha"]
    assert captured["env"]["CRAWL_PROGRESS_STDOUT"] == "1"


def test_run_crawl_forwards_keyword_date_ranges(monkeypatch):
    captured = {}

    def fake_popen(args, *unused_args, **unused_kwargs):
        captured["args"] = args
        return _FakeProcess([])

    monkeypatch.setattr(crawl_all_keywords.subprocess, "Popen", fake_popen)

    assert crawl_all_keywords.run_crawl(
        "dy",
        ["alpha"],
        keyword_date_ranges={
            "alpha": {"start_date": "2026-08-01", "end_date": "2026-08-31"}
        },
    )

    option_index = captured["args"].index("--keyword_date_ranges")
    assert json.loads(captured["args"][option_index + 1]) == {
        "alpha": {"start_date": "2026-08-01", "end_date": "2026-08-31"}
    }


def test_run_crawl_forwards_keyword_sort_modes(monkeypatch):
    captured = {}

    def fake_popen(args, *unused_args, **unused_kwargs):
        captured["args"] = args
        return _FakeProcess([])

    monkeypatch.setattr(crawl_all_keywords.subprocess, "Popen", fake_popen)

    assert crawl_all_keywords.run_crawl(
        "dy",
        ["alpha", "beta"],
        keyword_sort_modes={"alpha": 0, "beta": 1},
    )

    option_index = captured["args"].index("--keyword_sort_modes")
    assert json.loads(captured["args"][option_index + 1]) == {
        "alpha": 0,
        "beta": 1,
    }


def test_run_crawl_forwards_keyword_max_note_counts(monkeypatch):
    captured = {}

    def fake_popen(args, *unused_args, **unused_kwargs):
        captured["args"] = args
        return _FakeProcess([])

    monkeypatch.setattr(crawl_all_keywords.subprocess, "Popen", fake_popen)

    assert crawl_all_keywords.run_crawl(
        "xhs",
        ["alpha", "beta"],
        keyword_max_note_counts={"alpha": 12, "beta": 35},
    )

    option_index = captured["args"].index("--keyword_max_note_counts")
    assert json.loads(captured["args"][option_index + 1]) == {
        "alpha": 12,
        "beta": 35,
    }


def test_build_keyword_sort_modes_defaults_to_comprehensive():
    assert crawl_all_keywords.build_keyword_sort_modes(
        [
            {"keyword": "alpha"},
            {"keyword": "beta", "sort_mode": "1"},
        ]
    ) == {"alpha": 0, "beta": 1}


def test_build_keyword_max_note_counts_ignores_missing_values():
    assert crawl_all_keywords.build_keyword_max_note_counts(
        [
            {"keyword": "alpha", "max_note_count": None},
            {"keyword": "beta", "max_note_count": ""},
            {"keyword": "gamma", "max_note_count": 25},
        ]
    ) == {"gamma": 25}


@pytest.mark.parametrize("value", [0, -1, "abc", "1.5"])
def test_build_keyword_max_note_counts_rejects_non_positive_integers(value):
    with pytest.raises(ValueError, match="max_note_count"):
        crawl_all_keywords.build_keyword_max_note_counts(
            [{"keyword": "alpha", "max_note_count": value}]
        )


def test_regular_checkpoint_survives_later_subprocess_failure(monkeypatch, tmp_path):
    history_path = tmp_path / "crawl_history.json"
    monkeypatch.setattr(crawl_all_keywords, "HISTORY_FILE", history_path)
    monkeypatch.setattr(
        crawl_all_keywords,
        "disable_one_time_keywords",
        lambda keywords: None,
    )

    def fake_run_crawl(platform, keywords, on_keyword_completed, **kwargs):
        assert platform == "dy"
        assert keywords == ["alpha", "beta"]
        assert kwargs["keyword_sort_modes"] == {"alpha": 0, "beta": 0}
        on_keyword_completed("alpha")
        saved_history = json.loads(history_path.read_text(encoding="utf-8"))
        assert saved_history["dy"]["alpha"]
        return False

    monkeypatch.setattr(crawl_all_keywords, "run_crawl", fake_run_crawl)

    summary = crawl_all_keywords.run_regular_check(
        ["dy"],
        [
            {"keyword": "alpha", "is_one_time": False},
            {"keyword": "beta", "is_one_time": False},
        ],
    )

    saved_history = json.loads(history_path.read_text(encoding="utf-8"))
    assert saved_history["dy"]["alpha"]
    assert "beta" not in saved_history["dy"]
    assert summary == {
        "total": 2,
        "skipped": 0,
        "success": 1,
        "failed": 1,
    }


def test_realtime_crawl_ignores_current_month_history(monkeypatch, tmp_path):
    history_path = tmp_path / "crawl_history.json"
    history_path.write_text(
        json.dumps({"dy": {"alpha": datetime.now().strftime("%Y-%m")}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(crawl_all_keywords, "HISTORY_FILE", history_path)
    monkeypatch.setattr(
        crawl_all_keywords,
        "get_realtime_keywords_with_flag",
        lambda: [{"keyword": "alpha", "is_regular": 1}],
    )
    monkeypatch.setattr(crawl_all_keywords, "update_remark", lambda keywords, remark: None)
    monkeypatch.setattr(crawl_all_keywords, "disable_temp_keywords", lambda keywords: None)
    disabled_realtime = []
    monkeypatch.setattr(
        crawl_all_keywords,
        "disable_realtime_for_regular_keywords",
        lambda keywords: disabled_realtime.extend(keywords),
    )

    calls = []

    def fake_run_crawl(platform, keywords, on_keyword_completed, **kwargs):
        calls.append((platform, keywords))
        assert kwargs["keyword_sort_modes"] == {"alpha": 0}
        on_keyword_completed("alpha")
        return True

    monkeypatch.setattr(crawl_all_keywords, "run_crawl", fake_run_crawl)

    crawl_all_keywords.run_realtime_check(["dy"])

    assert calls == [("dy", ["alpha"])]
    assert json.loads(history_path.read_text(encoding="utf-8")) == {
        "dy": {"alpha": datetime.now().strftime("%Y-%m")}
    }
    assert disabled_realtime == ["alpha"]


def test_realtime_temp_keyword_requires_all_platforms_in_current_run(monkeypatch):
    monkeypatch.setattr(
        crawl_all_keywords,
        "get_realtime_keywords_with_flag",
        lambda: [{"keyword": "alpha", "is_regular": 0}],
    )
    monkeypatch.setattr(crawl_all_keywords, "update_remark", lambda keywords, remark: None)
    monkeypatch.setattr(
        crawl_all_keywords,
        "disable_realtime_for_regular_keywords",
        lambda keywords: None,
    )

    disabled = []
    monkeypatch.setattr(
        crawl_all_keywords,
        "disable_temp_keywords",
        lambda keywords: disabled.extend(keywords),
    )
    monkeypatch.setattr(
        crawl_all_keywords,
        "run_crawl",
        lambda platform, keywords, on_keyword_completed, **kwargs: (
            on_keyword_completed("alpha") or True
            if platform == "dy"
            else False
        ),
    )

    crawl_all_keywords.run_realtime_check(["dy", "xhs"])

    assert disabled == []


def test_realtime_regular_keyword_stays_enabled_when_any_platform_fails(monkeypatch):
    monkeypatch.setattr(
        crawl_all_keywords,
        "get_realtime_keywords_with_flag",
        lambda: [{"keyword": "alpha", "is_regular": 1}],
    )
    monkeypatch.setattr(crawl_all_keywords, "update_remark", lambda keywords, remark: None)
    monkeypatch.setattr(crawl_all_keywords, "disable_temp_keywords", lambda keywords: None)

    disabled_realtime = []
    monkeypatch.setattr(
        crawl_all_keywords,
        "disable_realtime_for_regular_keywords",
        lambda keywords: disabled_realtime.extend(keywords),
    )
    monkeypatch.setattr(
        crawl_all_keywords,
        "run_crawl",
        lambda platform, keywords, on_keyword_completed, **kwargs: (
            on_keyword_completed("alpha") or True
            if platform == "dy"
            else False
        ),
    )

    crawl_all_keywords.run_realtime_check(["dy", "xhs"])

    assert disabled_realtime == []
