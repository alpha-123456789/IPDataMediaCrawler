import io
import json

import crawl_all_keywords
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


def test_regular_checkpoint_survives_later_subprocess_failure(monkeypatch, tmp_path):
    history_path = tmp_path / "crawl_history.json"
    monkeypatch.setattr(crawl_all_keywords, "HISTORY_FILE", history_path)
    monkeypatch.setattr(
        crawl_all_keywords,
        "disable_one_time_keywords",
        lambda keywords: None,
    )

    def fake_run_crawl(platform, keywords, on_keyword_completed):
        assert platform == "dy"
        assert keywords == ["alpha", "beta"]
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
