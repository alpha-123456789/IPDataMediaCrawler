"""将关键词任务完成结果回调到后台 Web 接口。"""

import json
import os
import socket
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


NOTIFY_URL = "http://localhost:5000/MultiDataViewManage/KeywordTaskNotify/Completion"
NOTIFY_URL_ENV = "KEYWORD_NOTIFY_URL"
NOTIFY_TOKEN_ENV = "KEYWORD_NOTIFY_TOKEN"
NOTIFY_TIMEOUT_SECONDS = 15
PROJECT_DIR = Path(__file__).resolve().parents[2]


def get_notify_url() -> str:
    """读取当前配置的回调地址。"""
    load_dotenv(PROJECT_DIR / ".env", override=True)
    return (os.getenv(NOTIFY_URL_ENV) or NOTIFY_URL).strip()


def send_keyword_task_completion(payload: dict[str, Any]) -> bool:
    """发送完成回调；未配置或发送失败时不影响原任务结果。"""
    load_dotenv(PROJECT_DIR / ".env", override=True)
    token = (os.getenv(NOTIFY_TOKEN_ENV) or "").strip()
    if not token:
        print("[通知] 未配置 KEYWORD_NOTIFY_TOKEN，跳过完成通知", flush=True)
        return False

    notify_url = get_notify_url()
    print(f"[通知] 回调地址：{notify_url}", flush=True)
    request_payload = dict(payload)
    request_payload.setdefault(
        "executor_name",
        os.getenv("KEYWORD_CRAWLER_RUNNER_NAME") or socket.gethostname(),
    )
    request = urllib.request.Request(
        notify_url,
        data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Keyword-Notify-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=NOTIFY_TIMEOUT_SECONDS) as response:
            status_code = response.getcode()
            response_body = response.read().decode("utf-8", errors="replace").strip()
            if not 200 <= status_code < 300:
                raise RuntimeError(f"HTTP {status_code}：{response_body or '无响应内容'}")
            try:
                result = json.loads(response_body)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"响应不是有效 JSON：{response_body or '空响应'}"
                ) from exc
            if result.get("success") is not True:
                raise RuntimeError(f"后台未确认钉钉发送成功：{response_body}")
        print("[通知] 关键词任务完成通知已发送", flush=True)
        return True
    except Exception as exc:
        response_body = ""
        if hasattr(exc, "read"):
            try:
                response_body = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:
                pass
        detail = f"{exc}：{response_body}" if response_body else str(exc)
        print(f"[通知] 关键词任务完成通知发送失败：{detail}", flush=True)
        return False
