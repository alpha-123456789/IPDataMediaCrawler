# -*- coding: utf-8 -*-
"""CDP 浏览器端口占用检测，用于防止多个抓取进程同时运行。"""

import socket


def is_cdp_browser_running(start_port: int = 9222, scan_range: int = 100) -> bool:
    """
    检查是否有 CDP 浏览器实例正在运行（通过检测 debug port 是否被占用）。
    扫描范围与 browser_launcher.find_available_port() 一致：从 start_port 开始连续 scan_range 个端口。
    返回 True 表示有端口被占用（即有抓取正在进行）。
    """
    for port in range(start_port, start_port + scan_range):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            if result == 0:
                return True
        except (socket.error, OSError):
            pass
    return False
