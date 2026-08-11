# -*- coding: utf-8 -*-
"""
按平台批量抓取关键词，自动跳过本月已抓取的关键词。
关键词来源：数据库 crawler_keyword 表（status=1 为启用）
历史记录：crawl_history.json（自动生成）
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from custom.db import get_conn
from tools.cdp_guard import is_cdp_browser_running
from tools.crawl_progress import (
    PROGRESS_ENV,
    parse_keyword_completed_event,
)

HISTORY_FILE = Path("crawl_history.json")

# 所有平台共用的抓取参数
PLATFORMS = ["dy", "ks", "wb", "bili", "xhs"]
CRAWL_CONFIG = {
    "lt": "qrcode",
    "crawler_max_notes_count": 100,
    "get_comment": True,
    "get_sub_comment": False,
    "max_comments_count_singlenotes": 20,
}


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data):
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        file.write(json.dumps(data, ensure_ascii=False, indent=2))
        file.flush()
        os.fsync(file.fileno())
    os.replace(temp_path, path)


def get_regular_keywords_with_flag() -> list:
    """获取常规模式关键词及其是否为一次性关键词。

    常规定期关键词：status=1 AND is_regular=1。
    一次性关键词：status=1 AND is_regular=0 AND is_realtime=0；
    在所有目标平台抓取成功后会被自动禁用。
    """
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT keyword, is_regular, is_realtime
                FROM crawler_keyword
                WHERE status = 1
                  AND (
                      is_regular = 1
                      OR (is_regular = 0 AND is_realtime = 0)
                  )
            """)
            rows = cursor.fetchall()
            return [
                {
                    "keyword": row['keyword'].strip(),
                    "is_one_time": row['is_regular'] == 0 and row['is_realtime'] == 0,
                }
                for row in rows
                if row['keyword'] and row['keyword'].strip()
            ]
    finally:
        conn.close()


def get_realtime_keywords_with_flag() -> list:
    """获取需要实时抓取的关键词及其 is_regular 标志: status=1 AND is_realtime=1"""
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT keyword, is_regular
                FROM crawler_keyword
                WHERE status = 1 AND is_realtime = 1
            """)
            rows = cursor.fetchall()
            return [
                {"keyword": row['keyword'].strip(), "is_regular": row['is_regular']}
                for row in rows
                if row['keyword'] and row['keyword'].strip()
            ]
    finally:
        conn.close()


def update_remark(keywords: list, remark: str):
    """批量更新关键词的 remark 字段"""
    if not keywords:
        return
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            placeholders = ",".join(["%s"] * len(keywords))
            cursor.execute(f"""
                UPDATE crawler_keyword
                SET remark = %s
                WHERE keyword IN ({placeholders})
            """, [remark] + keywords)
            conn.commit()
    finally:
        conn.close()


def disable_temp_keywords(keywords: list):
    """将实时模式中 is_regular=0 的临时关键词 status 设为 0。"""
    if not keywords:
        return
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            placeholders = ",".join(["%s"] * len(keywords))
            cursor.execute(f"""
                UPDATE crawler_keyword
                SET status = 0
                WHERE keyword IN ({placeholders})
                  AND is_regular = 0
            """, keywords)
            conn.commit()
    finally:
        conn.close()


def disable_one_time_keywords(keywords: list):
    """将 regular 模式中已完成的一次性关键词 status 设为 0。"""
    if not keywords:
        return
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            placeholders = ",".join(["%s"] * len(keywords))
            cursor.execute(f"""
                UPDATE crawler_keyword
                SET status = 0
                WHERE keyword IN ({placeholders})
                  AND is_regular = 0
                  AND is_realtime = 0
            """, keywords)
            conn.commit()
    finally:
        conn.close()


def run_crawl(platform: str, keywords: list, on_keyword_completed=None) -> bool:
    """Run a single crawl session for a platform with multiple keywords (comma-separated)."""
    cmd = [
        "uv", "run", "main.py",
        "--platform", platform,
        "--lt", CRAWL_CONFIG["lt"],
        "--type", "search",
        "--keywords", ",".join(keywords),
        "--crawler_max_notes_count", str(CRAWL_CONFIG["crawler_max_notes_count"]),
        "--get_comment", str(CRAWL_CONFIG["get_comment"]),
        "--get_sub_comment", str(CRAWL_CONFIG["get_sub_comment"]),
        "--max_comments_count_singlenotes", str(CRAWL_CONFIG["max_comments_count_singlenotes"]),
    ]

    print(f"\n{'='*60}")
    print(f"[RUN] platform={platform}  keywords={keywords}")
    print(f"      cmd: {' '.join(cmd)}")
    print(f"{'='*60}")

    env = os.environ.copy()
    if on_keyword_completed:
        env[PROGRESS_ENV] = "1"

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    if process.stdout is None:
        raise RuntimeError("Unable to read crawler subprocess output")

    for raw_line in process.stdout:
        line = raw_line.rstrip("\r\n")
        event = parse_keyword_completed_event(line)
        if event:
            if (
                on_keyword_completed
                and event["platform"] == platform
                and event["keyword"] in keywords
            ):
                on_keyword_completed(event["keyword"])
            else:
                print(f"[WARN] Ignored invalid crawler progress event: {event}")
            continue
        print(line, flush=True)

    return process.wait() == 0


def ensure_cdp_browser_idle(mode_label: str) -> bool:
    """在进入抓取流程前检查 CDP 浏览器是否空闲。"""
    if is_cdp_browser_running():
        print(f"[{mode_label}] 上一次抓取的浏览器仍在运行，跳过本次执行")
        return False
    return True


def run_realtime_check(platforms: list):
    """检查并执行实时关键词抓取。"""
    keyword_rows = get_realtime_keywords_with_flag()
    if not keyword_rows:
        print("[REALTIME] 没有需要实时抓取的关键词")
        return

    keywords = [r["keyword"] for r in keyword_rows]
    regular_keywords = [r["keyword"] for r in keyword_rows if r["is_regular"] == 1]
    temp_keywords = [r["keyword"] for r in keyword_rows if r["is_regular"] == 0]

    print(f"[REALTIME] 发现 {len(keywords)} 个实时关键词: {keywords}")
    if regular_keywords:
        print(f"[REALTIME]   定期关键词(is_regular=1): {regular_keywords}")
    if temp_keywords:
        print(f"[REALTIME]   临时关键词(is_regular=0): {temp_keywords}")

    history: dict = load_json(HISTORY_FILE, {})
    current_month = datetime.now().strftime("%Y-%m")

    for platform in platforms:
        platform_history: dict = history.setdefault(platform, {})

        for kw in keywords:
            # 检查该关键词本月是否已抓取过
            if platform_history.get(kw) == current_month:
                print(f"[REALTIME SKIP] {platform} / {kw}  (本月已抓取)")
                continue

            # 抓取开始前更新 remark
            update_remark([kw], "正在实时抓取")

            ok = run_crawl(platform, [kw])
            if ok:
                print(f"[REALTIME DONE] {platform} / {kw}")
                platform_history[kw] = current_month
                save_json(HISTORY_FILE, history)
                update_remark([kw], "实时抓取完成")
            else:
                print(f"[REALTIME FAIL] {platform} / {kw}")
                update_remark([kw], "实时抓取失败，等待重新抓取")

    # 所有平台都完成后，将 is_regular=0 的临时关键词 status 置为 0
    # 只有全部平台都成功的才禁用（失败的保留 status=1 等下次重试）
    success_temp_keywords = []
    for kw in temp_keywords:
        all_done = all(
            history.get(p, {}).get(kw) == current_month for p in platforms
        )
        if all_done:
            success_temp_keywords.append(kw)
    disable_temp_keywords(success_temp_keywords)
    if success_temp_keywords:
        print(f"[REALTIME] 已将临时关键词 status 置为 0: {success_temp_keywords}")


def run_regular_check(platforms: list, keyword_rows: list) -> dict:
    """Run regular crawls and checkpoint each completed platform/keyword pair."""
    db_keywords = [row["keyword"] for row in keyword_rows]
    one_time_keywords = [row["keyword"] for row in keyword_rows if row["is_one_time"]]

    history: dict = load_json(HISTORY_FILE, {})
    current_month = datetime.now().strftime("%Y-%m")
    total = skipped = success = failed = 0

    for platform in platforms:
        platform_history: dict = history.setdefault(platform, {})
        pending_keywords = []
        for keyword in db_keywords:
            total += 1
            if platform_history.get(keyword) == current_month:
                print(f"[SKIP] {platform} / {keyword}  (already crawled in {current_month})")
                skipped += 1
            else:
                pending_keywords.append(keyword)

        if not pending_keywords:
            continue

        completed_keywords = set()

        def checkpoint_keyword(keyword: str) -> None:
            nonlocal success
            if keyword in completed_keywords:
                return

            completed_keywords.add(keyword)
            platform_history[keyword] = current_month
            save_json(HISTORY_FILE, history)
            success += 1
            print(f"[DONE] {platform} / {keyword}  (history checkpoint saved)")

        process_ok = run_crawl(
            platform,
            pending_keywords,
            on_keyword_completed=checkpoint_keyword,
        )
        incomplete_keywords = [
            keyword for keyword in pending_keywords if keyword not in completed_keywords
        ]
        if incomplete_keywords:
            failed += len(incomplete_keywords)
            state = "exit code non-zero" if not process_ok else "no completion checkpoint"
            print(
                f"[FAIL] {platform} / {incomplete_keywords}  "
                f"({state}, will retry next run)"
            )

    completed_one_time_keywords = [
        keyword
        for keyword in one_time_keywords
        if all(history.get(platform, {}).get(keyword) == current_month for platform in PLATFORMS)
    ]
    disable_one_time_keywords(completed_one_time_keywords)
    if completed_one_time_keywords:
        print(f"[REGULAR] 已将一次性关键词 status 置为 0: {completed_one_time_keywords}")

    summary = {
        "total": total,
        "skipped": skipped,
        "success": success,
        "failed": failed,
    }
    print(f"\n{'='*60}")
    print(
        f"Summary: total={summary['total']}  skipped={summary['skipped']}  "
        f"success={summary['success']}  failed={summary['failed']}"
    )
    print(f"{'='*60}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="按平台批量抓取关键词")
    parser.add_argument("--platform", "-p", type=str, default=None,
                        help="指定要运行的平台（如 bili, xhs, dy, wb），不指定则运行所有平台")
    parser.add_argument("--mode", "-m", type=str, default="regular",
                        choices=["regular", "realtime"],
                        help="运行模式: regular=常规月度抓取, realtime=实时关键词检查抓取")
    args = parser.parse_args()

    # 确定要运行的平台列表
    if args.platform:
        if args.platform not in PLATFORMS:
            print(f"[ERROR] Platform '{args.platform}' not supported. Available: {', '.join(PLATFORMS)}")
            sys.exit(1)
        platforms = [args.platform]
    else:
        platforms = PLATFORMS

    if not ensure_cdp_browser_idle(args.mode.upper()):
        return

    # 实时模式：检查并抓取实时关键词
    if args.mode == "realtime":
        run_realtime_check(platforms)
        return

    # === 以下为常规模式（regular）===
    # 常规定期关键词，以及 regular 模式下的一次性关键词。
    keyword_rows = get_regular_keywords_with_flag()
    if not keyword_rows:
        print("[WARN] crawler_keyword 表中没有可供常规模式抓取的关键词")
    run_regular_check(platforms, keyword_rows)


if __name__ == "__main__":
    main()
