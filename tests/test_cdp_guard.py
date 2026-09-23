import json
from contextlib import contextmanager
from types import SimpleNamespace

from tools import cdp_guard


def _response(payload, status=200):
    @contextmanager
    def opened():
        yield SimpleNamespace(
            status=status,
            read=lambda: json.dumps(payload).encode("utf-8"),
        )

    return opened()


def test_is_cdp_browser_running_detects_cdp_endpoint(monkeypatch):
    requested_urls = []

    def fake_urlopen(url, timeout):
        requested_urls.append((url, timeout))
        if url.endswith(":9224/json/version"):
            return _response({"webSocketDebuggerUrl": "ws://127.0.0.1:9224/devtools/browser/id"})
        raise OSError("connection refused")

    monkeypatch.setattr(cdp_guard, "urlopen", fake_urlopen)
    monkeypatch.setattr(cdp_guard.json, "load", lambda response: json.loads(response.read()))

    assert cdp_guard.is_cdp_browser_running(start_port=9224, scan_range=3)
    assert requested_urls == [
        ("http://127.0.0.1:9224/json/version", 0.05),
    ]


def test_is_cdp_browser_running_ignores_non_cdp_endpoint(monkeypatch):
    def fake_urlopen(url, timeout):
        return _response({"Browser": "some-http-service"})

    monkeypatch.setattr(cdp_guard, "urlopen", fake_urlopen)

    assert not cdp_guard.is_cdp_browser_running(start_port=9300, scan_range=2)
