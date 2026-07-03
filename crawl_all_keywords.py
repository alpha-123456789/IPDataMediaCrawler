# -*- coding: utf-8 -*-
"""
按平台批量抓取关键词，自动跳过本月已抓取的关键词。
配置文件：keywords_config.json
历史记录：crawl_history.json（自动生成）
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CONFIG_FILE = Path("keywords_config.json")
HISTORY_FILE = Path("crawl_history.json")


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_crawl(platform: str, platform_cfg: dict, keywords: list) -> bool:
    """Run a single crawl session for a platform with multiple keywords (comma-separated)."""
    lt = platform_cfg.get("lt", "qrcode")
    max_notes = platform_cfg.get("crawler_max_notes_count", 20)
    get_comment = platform_cfg.get("get_comment", False)
    get_sub_comment = platform_cfg.get("get_sub_comment", False)
    max_comments = platform_cfg.get("max_comments_count_singlenotes", 20)

    cmd = [
        "uv", "run", "main.py",
        "--platform", platform,
        "--lt", lt,
        "--type", "search",
        "--keywords", ",".join(keywords),
        "--crawler_max_notes_count", str(max_notes),
        "--get_comment", str(get_comment),
        "--get_sub_comment", str(get_sub_comment),
        "--max_comments_count_singlenotes", str(max_comments),
    ]

    print(f"\n{'='*60}")
    print(f"[RUN] platform={platform}  keywords={keywords}")
    print(f"      cmd: {' '.join(cmd)}")
    print(f"{'='*60}")

    result = subprocess.run(cmd)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="按平台批量抓取关键词")
    parser.add_argument("--platform", "-p", type=str, default=None,
                        help="指定要运行的平台（如 bili, xhs, dy, wb），不指定则运行所有平台")
    args = parser.parse_args()

    config: dict = load_json(CONFIG_FILE, {})
    if not config:
        print(f"[ERROR] {CONFIG_FILE} not found or empty.")
        sys.exit(1)

    # Filter platforms if specified
    if args.platform:
        if args.platform not in config:
            print(f"[ERROR] Platform '{args.platform}' not found in {CONFIG_FILE}. Available: {', '.join(config.keys())}")
            sys.exit(1)
        config = {args.platform: config[args.platform]}

    history: dict = load_json(HISTORY_FILE, {})
    current_month = datetime.now().strftime("%Y-%m")

    total = skipped = success = failed = 0

    for platform, platform_cfg in config.items():
        keywords: list = platform_cfg.get("keywords", [])
        platform_history: dict = history.setdefault(platform, {})

        # Filter out already-crawled keywords for this month
        pending_keywords = []
        for keyword in keywords:
            total += 1
            if platform_history.get(keyword) == current_month:
                print(f"[SKIP] {platform} / {keyword}  (already crawled in {current_month})")
                skipped += 1
            else:
                pending_keywords.append(keyword)

        if not pending_keywords:
            continue

        # Run all pending keywords in a single session (shared browser)
        ok = run_crawl(platform, platform_cfg, pending_keywords)

        if ok:
            for keyword in pending_keywords:
                platform_history[keyword] = current_month
                success += 1
            save_json(HISTORY_FILE, history)
            print(f"[DONE] {platform} / {pending_keywords}")
        else:
            for keyword in pending_keywords:
                failed += 1
            print(f"[FAIL] {platform} / {pending_keywords}  (exit code non-zero, will retry next run)")

    print(f"\n{'='*60}")
    print(f"Summary: total={total}  skipped={skipped}  success={success}  failed={failed}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
