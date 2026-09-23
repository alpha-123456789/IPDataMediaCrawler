import json
from datetime import date
from types import SimpleNamespace

import crawl_all_keywords
from custom.keyword_insight import notify_client
from custom.keyword_insight import keyword_report_runner


class FakeResponse:
    def __init__(self, status_code=200, body=b'{"success": true}'):
        self.status_code = status_code
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def getcode(self):
        return self.status_code

    def read(self):
        return self.body


def test_notification_client_posts_to_configured_web_endpoint(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("KEYWORD_NOTIFY_TOKEN", "test-token")
    monkeypatch.setenv(
        "KEYWORD_NOTIFY_URL",
        "https://overseasdata.mm.babybus.com/MultiDataViewManage/KeywordTaskNotify/Completion",
    )
    monkeypatch.setenv("KEYWORD_CRAWLER_RUNNER_NAME", "test-runner")
    monkeypatch.setattr(notify_client, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(notify_client.urllib.request, "urlopen", fake_urlopen)

    assert notify_client.send_keyword_task_completion(
        {
            "kind": "report",
            "dedupe_key": "report-12",
            "task_id": 12,
            "modify_user_id": "42",
        }
    )

    request = captured["request"]
    assert request.full_url == (
        "https://overseasdata.mm.babybus.com/MultiDataViewManage/KeywordTaskNotify/Completion"
    )
    assert request.get_header("X-keyword-notify-token") == "test-token"
    assert json.loads(request.data.decode("utf-8")) == {
        "kind": "report",
        "dedupe_key": "report-12",
        "task_id": 12,
        "modify_user_id": "42",
        "executor_name": "test-runner",
    }
    assert captured["timeout"] == notify_client.NOTIFY_TIMEOUT_SECONDS


def test_notification_client_rejects_backend_business_failure(monkeypatch):
    monkeypatch.setenv("KEYWORD_NOTIFY_TOKEN", "test-token")
    monkeypatch.setenv("KEYWORD_NOTIFY_URL", "https://example.test/notify")
    monkeypatch.setattr(notify_client, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        notify_client.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(
            body='{"success": false, "message": "钉钉发送失败"}'.encode("utf-8")
        ),
    )

    assert not notify_client.send_keyword_task_completion(
        {"kind": "report", "dedupe_key": "report-13", "task_id": 13}
    )


def test_notification_client_rejects_empty_backend_response(monkeypatch):
    monkeypatch.setenv("KEYWORD_NOTIFY_TOKEN", "test-token")
    monkeypatch.setenv("KEYWORD_NOTIFY_URL", "https://example.test/notify")
    monkeypatch.setattr(notify_client, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        notify_client.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(body=b""),
    )

    assert not notify_client.send_keyword_task_completion(
        {"kind": "report", "dedupe_key": "report-14", "task_id": 14}
    )


def test_realtime_completion_sends_success_and_failure_summary(monkeypatch):
    monkeypatch.setattr(
        crawl_all_keywords,
        "get_realtime_keywords_with_flag",
        lambda: [
            {"keyword": "alpha", "is_regular": 1, "modify_user_id": "42"},
            {"keyword": "beta", "is_regular": 0, "modify_user_id": "43"},
        ],
    )
    monkeypatch.setattr(crawl_all_keywords, "update_remark", lambda keywords, remark: None)
    monkeypatch.setattr(
        crawl_all_keywords,
        "disable_realtime_for_regular_keywords",
        lambda keywords: None,
    )
    monkeypatch.setattr(
        crawl_all_keywords,
        "disable_temp_keywords",
        lambda keywords: None,
    )
    def fake_run_crawl(platform, keywords, on_keyword_completed, **kwargs):
        if platform == "dy" and keywords == ["alpha"]:
            on_keyword_completed("alpha")
            return True
        return False

    monkeypatch.setattr(crawl_all_keywords, "run_crawl", fake_run_crawl)
    notifications = []
    monkeypatch.setattr(
        crawl_all_keywords,
        "send_keyword_task_completion",
        notifications.append,
    )

    crawl_all_keywords.run_realtime_check(["dy"])

    assert len(notifications) == 2
    notifications_by_user = {
        payload["modify_user_id"]: payload for payload in notifications
    }
    assert notifications_by_user["42"]["kind"] == "realtime"
    assert notifications_by_user["42"]["dedupe_key"].startswith("realtime-")
    assert notifications_by_user["42"]["platforms"] == ["dy"]
    assert notifications_by_user["42"]["success_items"] == ["dy / alpha"]
    assert notifications_by_user["42"]["failed_items"] == []
    assert notifications_by_user["43"]["success_items"] == []
    assert notifications_by_user["43"]["failed_items"] == ["dy / beta"]


def test_realtime_crawl_requires_keyword_completion_event_even_when_process_succeeds(
    monkeypatch,
):
    monkeypatch.setattr(
        crawl_all_keywords,
        "get_realtime_keywords_with_flag",
        lambda: [{"keyword": "alpha", "is_regular": 1, "modify_user_id": "42"}],
    )
    monkeypatch.setattr(crawl_all_keywords, "update_remark", lambda keywords, remark: None)
    disabled_realtime = []
    monkeypatch.setattr(
        crawl_all_keywords,
        "disable_realtime_for_regular_keywords",
        lambda keywords: disabled_realtime.extend(keywords),
    )
    monkeypatch.setattr(crawl_all_keywords, "disable_temp_keywords", lambda keywords: None)

    notifications = []

    def fake_run_crawl(platform, keywords, on_keyword_completed, **kwargs):
        assert platform == "xhs"
        assert keywords == ["alpha"]
        assert callable(on_keyword_completed)
        return True

    monkeypatch.setattr(crawl_all_keywords, "run_crawl", fake_run_crawl)
    monkeypatch.setattr(
        crawl_all_keywords,
        "send_keyword_task_completion",
        notifications.append,
    )

    crawl_all_keywords.run_realtime_check(["xhs"])

    assert disabled_realtime == []
    assert notifications == [
        {
            "kind": "realtime",
            "dedupe_key": notifications[0]["dedupe_key"],
            "modify_user_id": "42",
            "platforms": ["xhs"],
            "success_items": [],
            "failed_items": ["xhs / alpha"],
        }
    ]


def test_complete_task_returns_whether_running_task_was_updated(monkeypatch):
    class FakeCursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, query, params):
            self.query = query
            self.params = params

    class FakeConnection:
        def __init__(self):
            self.cursor_instance = FakeCursor()
            self.committed = False

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            self.committed = True

        def rollback(self):
            raise AssertionError("rollback should not be called")

        def close(self):
            pass

    connection = FakeConnection()
    monkeypatch.setattr(keyword_report_runner, "get_conn", lambda: connection)

    assert keyword_report_runner.complete_task(12, True, execute_log="done")
    assert connection.committed
    assert connection.cursor_instance.params[-1] == 12


def test_report_runner_forces_utf8_for_child_process(monkeypatch):
    captured = {}

    class FakeProcess:
        stdout = ["[筛选] 平台：bili\n", "[完成] 报告已保存：测试报告\n"]

        @staticmethod
        def wait():
            return 0

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setenv("PYTHONIOENCODING", "gbk")
    monkeypatch.setenv("PYTHONUTF8", "0")
    monkeypatch.setattr(keyword_report_runner.subprocess, "Popen", fake_popen)

    execute_log = keyword_report_runner.run_task(
        {
            "id": 15,
            "prompt": "分析反馈",
            "report_name": "测试报告",
            "source_keyword": "测试",
            "start_date": date(2026, 9, 1),
            "end_date": date(2026, 9, 14),
            "platform": "bili",
            "post_ids": "123",
        }
    )

    assert captured["kwargs"]["encoding"] == "utf-8"
    assert captured["kwargs"]["env"]["PYTHONIOENCODING"] == "utf-8"
    assert captured["kwargs"]["env"]["PYTHONUTF8"] == "1"
    assert execute_log == "[筛选] 平台：bili\n[完成] 报告已保存：测试报告"


def test_report_runner_fails_when_child_process_times_out(monkeypatch):
    class FakeProcess:
        pid = 123
        returncode = -9

        def __init__(self):
            self.killed = False
            self.communicate_calls = 0

        def communicate(self, timeout=None):
            self.communicate_calls += 1
            if self.communicate_calls == 1:
                raise keyword_report_runner.subprocess.TimeoutExpired(
                    "custom_report",
                    timeout,
                    output="[数据] 正在查询帖子和评论数据\n",
                )
            return "", None

        def kill(self):
            self.killed = True

        def wait(self, timeout=None):
            return self.returncode

    process = FakeProcess()
    monkeypatch.setattr(keyword_report_runner, "TASK_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(
        keyword_report_runner.subprocess,
        "Popen",
        lambda command, **kwargs: process,
    )

    try:
        keyword_report_runner.run_task(
            {
                "id": 16,
                "prompt": "分析反馈",
                "report_name": "超时测试",
                "source_keyword": "测试",
                "start_date": date(2026, 9, 1),
                "end_date": date(2026, 9, 14),
                "platform": "bili",
                "post_ids": "123",
            }
        )
    except TimeoutError as exc:
        assert "超过 1 秒未完成" in str(exc)
    else:
        raise AssertionError("超时任务应抛出 TimeoutError")

    assert process.killed
