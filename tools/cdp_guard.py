# -*- coding: utf-8 -*-
"""CDP 浏览器端点检测，用于防止多个抓取进程同时运行。"""

import json
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def is_cdp_browser_running(
    start_port: int = 9222,
    scan_range: int = 100,
    timeout: float = 0.05,
) -> bool:
    """检查端口范围内是否存在可访问的 Chrome CDP 端点。

    自动启动浏览器时可能使用 start_port 之后的端口，因此保留扫描范围。
    通过 /json/version 验证 CDP 身份，避免把普通的端口占用误判为抓取进程。
    """
    for port in range(start_port, start_port + scan_range):
        try:
            with urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout) as response:
                if response.status != 200:
                    continue
                endpoint = json.load(response)
            if endpoint.get("webSocketDebuggerUrl"):
                return True
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
            continue
    return False