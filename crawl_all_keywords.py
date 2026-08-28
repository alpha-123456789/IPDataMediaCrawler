# -*- coding: utf-8 -*-
"""
按平台批量抓取关键词。
常规模式自动跳过本月已抓取的关键词，实时模式每次都重新抓取。
关键词来源：数据库 crawler_keyword 表（status=1 为启用）
历史记录：crawl_history.json（自动生成）
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime
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
                SELECT keyword, is_regular, is_realtime, start_date, end_date,
                       sort_mode, filter_note_time, max_note_count
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
                    "start_date": row["start_date"],
                    "end_date": row["end_date"],
                    "sort_mode": row.get("sort_mode", 0),
                    "filter_note_time": row.get("filter_note_time", 0),
                    "max_note_count": row.get("max_note_count"),
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
                SELECT keyword, is_regular, start_date, end_date,
                       sort_mode, filter_note_time, max_note_count
                FROM crawler_keyword
                WHERE status = 1 AND is_realtime = 1
            """)
            rows = cursor.fetchall()
            return [
                {
                    "keyword": row['keyword'].strip(),
                    "is_regular": row['is_regular'],
                    "start_date": row["start_date"],
                    "end_date": row["end_date"],
                    "sort_mode": row.get("sort_mode", 0),
                    "filter_note_time": row.get("filter_note_time", 0),
                    "max_note_count": row.get("max_note_count"),
                }
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


def disable_realtime_for_regular_keywords(keywords: list):
    """关闭定期关键词的实时抓取标记，保持 status 不变。"""
    if not keywords:
        return
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            placeholders = ",".join(["%s"] * len(keywords))
            cursor.execute(f"""
                UPDATE crawler_keyword
                SET is_realtime = 0
                WHERE keyword IN ({placeholders})
                  AND is_regular = 1
                  AND is_realtime = 1
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


def _format_date(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def build_keyword_date_ranges(keyword_rows: list) -> dict[str, dict[str, str]]:
    """Build a JSON-safe per-keyword date range map for the crawler subprocess."""
    date_ranges = {}
    for row in keyword_rows:
        start_date = _format_date(row.get("start_date"))
        end_date = _format_date(row.get("end_date"))
        if not start_date and not end_date:
            continue
        keyword = row["keyword"]
        if start_date and end_date and start_date > end_date:
            raise ValueError(
                f"crawler_keyword 中关键词 '{keyword}' 的 start_date 不能晚于 end_date"
            )
        date_ranges[keyword] = {
            "start_date": start_date,
            "end_date": end_date,
        }
    return date_ranges


def build_keyword_sort_modes(keyword_rows: list) -> dict[str, int]:
    """Build per-keyword search sort modes, defaulting to comprehensive."""
    return {
        row["keyword"]: int(row.get("sort_mode") or 0)
        for row in keyword_rows
        if row.get("keyword")
    }


def build_keyword_filter_note_times(keyword_rows: list) -> dict[str, int]:
    """Build per-keyword XHS note-time filters."""
    return {
        row["keyword"]: int(row.get("filter_note_time") or 0)
        for row in keyword_rows
        if row.get("keyword")
    }


def build_keyword_max_note_counts(keyword_rows: list) -> dict[str, int]:
    """Build explicit per-keyword limits; missing values use the global fallback."""
    max_note_counts = {}
    for row in keyword_rows:
        keyword = row.get("keyword")
        value = row.get("max_note_count")
        if not keyword or value is None or str(value).strip() == "":
            continue
        try:
            count = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"crawler_keyword 中关键词 '{keyword}' 的 max_note_count 必须是正整数"
            ) from exc
        if count <= 0 or str(value).strip() != str(count):
            raise ValueError(
                f"crawler_keyword 中关键词 '{keyword}' 的 max_note_count 必须是正整数"
            )
        max_note_counts[keyword] = count
    return max_note_counts


def run_crawl(
    platform: str,
    keywords: list,
    on_keyword_completed=None,
    keyword_date_ranges: dict | None = None,
    keyword_sort_modes: dict | None = None,
    keyword_filter_note_times: dict | None = None,
    keyword_max_note_counts: dict | None = None,
) -> bool:
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
    if keyword_date_ranges:
        cmd.extend(
            ["--keyword_date_ranges", json.dumps(keyword_date_ranges, ensure_ascii=False)]
        )
    if keyword_sort_modes:
        cmd.extend(
            ["--keyword_sort_modes", json.dumps(keyword_sort_modes, ensure_ascii=False)]
        )
    if platform == "xhs" and keyword_filter_note_times:
        cmd.extend(
            [
                "--keyword_filter_note_times",
                json.dumps(keyword_filter_note_times, ensure_ascii=False),
            ]
        )
    if keyword_max_note_counts:
        cmd.extend(
            [
                "--keyword_max_note_counts",
                json.dumps(keyword_max_note_counts, ensure_ascii=False),
            ]
        )

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
    keyword_date_ranges = build_keyword_date_ranges(keyword_rows)
    keyword_sort_modes = build_keyword_sort_modes(keyword_rows)
    keyword_filter_note_times = build_keyword_filter_note_times(keyword_rows)
    keyword_max_note_counts = build_keyword_max_note_counts(keyword_rows)
    regular_keywords = [r["keyword"] for r in keyword_rows if r["is_regular"] == 1]
    temp_keywords = [r["keyword"] for r in keyword_rows if r["is_regular"] == 0]

    print(f"[REALTIME] 发现 {len(keywords)} 个实时关键词: {keywords}")
    if regular_keywords:
        print(f"[REALTIME]   定期关键词(is_regular=1): {regular_keywords}")
    if temp_keywords:
        print(f"[REALTIME]   临时关键词(is_regular=0): {temp_keywords}")

    successful_crawls = set()

    for platform in platforms:
        for kw in keywords:
            # 抓取开始前更新 remark
            update_remark([kw], "正在实时抓取")

            crawl_kwargs = {}
            if kw in keyword_date_ranges:
                crawl_kwargs["keyword_date_ranges"] = {
                    kw: keyword_date_ranges[kw]
                }
            crawl_kwargs["keyword_sort_modes"] = {kw: keyword_sort_modes[kw]}
            if platform == "xhs":
                crawl_kwargs["keyword_filter_note_times"] = {
                    kw: keyword_filter_note_times[kw]
                }
            if kw in keyword_max_note_counts:
                crawl_kwargs["keyword_max_note_counts"] = {
                    kw: keyword_max_note_counts[kw]
                }
            ok = run_crawl(platform, [kw], **crawl_kwargs)
            if ok:
                print(f"[REALTIME DONE] {platform} / {kw}")
                successful_crawls.add((platform, kw))
                update_remark([kw], "实时抓取完成")
            else:
                print(f"[REALTIME FAIL] {platform} / {kw}")
                update_remark([kw], "实时抓取失败，等待重新抓取")

    # 只有本次全部平台都成功，才关闭对应关键词的实时任务。
    success_regular_keywords = [
        kw
        for kw in regular_keywords
        if all((platform, kw) in successful_crawls for platform in platforms)
    ]
    disable_realtime_for_regular_keywords(success_regular_keywords)
    if success_regular_keywords:
        print(
            "[REALTIME] 已关闭定期关键词的实时抓取标记，status 保持不变: "
            f"{success_regular_keywords}"
        )

    # 临时关键词全部平台成功后直接停用，失败则保留等待下次重试。
    success_temp_keywords = []
    for kw in temp_keywords:
        all_done = all((platform, kw) in successful_crawls for platform in platforms)
        if all_done:
            success_temp_keywords.append(kw)
    disable_temp_keywords(success_temp_keywords)
    if success_temp_keywords:
        print(f"[REALTIME] 已将临时关键词 status 置为 0: {success_temp_keywords}")


def run_regular_check(platforms: list, keyword_rows: list) -> dict:
    """Run regular crawls and checkpoint each completed platform/keyword pair."""
    db_keywords = [row["keyword"] for row in keyword_rows]
    keyword_date_ranges = build_keyword_date_ranges(keyword_rows)
    keyword_sort_modes = build_keyword_sort_modes(keyword_rows)
    keyword_filter_note_times = build_keyword_filter_note_times(keyword_rows)
    keyword_max_note_counts = build_keyword_max_note_counts(keyword_rows)
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

        crawl_kwargs = {"on_keyword_completed": checkpoint_keyword}
        pending_date_ranges = {
            keyword: keyword_date_ranges[keyword]
            for keyword in pending_keywords
            if keyword in keyword_date_ranges
        }
        if pending_date_ranges:
            crawl_kwargs["keyword_date_ranges"] = pending_date_ranges
        crawl_kwargs["keyword_sort_modes"] = {
            keyword: keyword_sort_modes[keyword]
            for keyword in pending_keywords
        }
        if platform == "xhs":
            crawl_kwargs["keyword_filter_note_times"] = {
                keyword: keyword_filter_note_times[keyword]
                for keyword in pending_keywords
            }
        pending_max_note_counts = {
            keyword: keyword_max_note_counts[keyword]
            for keyword in pending_keywords
            if keyword in keyword_max_note_counts
        }
        if pending_max_note_counts:
            crawl_kwargs["keyword_max_note_counts"] = pending_max_note_counts
        process_ok = run_crawl(platform, pending_keywords, **crawl_kwargs)
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
