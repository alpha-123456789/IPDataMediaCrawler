# -*- coding: utf-8 -*-
"""
批量生成关键词洞察报告。

用法：
  # 生成所有关键词的报告
  uv run custom/keyword_insight/batch_report.py

  # 只生成指定关键词
  uv run custom/keyword_insight/batch_report.py 猴子警长 小鸡敦敦 弗兰熊

  # 按分组生成（使用 config.py 中 IP_KEYWORDS 的分组名）
  uv run custom/keyword_insight/batch_report.py --group 猴子警长系列

  # 使用参考资料生成 AI 报告
  uv run custom/keyword_insight/batch_report.py --ref reference.txt

  # 列出数据库中所有可用关键词
  uv run custom/keyword_insight/batch_report.py --list
"""

import argparse
import sys
import time
from datetime import datetime

from custom.keyword_insight.config import IP_KEYWORDS
from custom.keyword_insight.generator import Generator
from custom.keyword_insight.report_repository import ReportRepository
from custom.keyword_insight.repository import KeywordRepository


def main():
    parser = argparse.ArgumentParser(description="批量生成关键词洞察报告")
    parser.add_argument("keywords", nargs="*", help="指定关键词，不传则生成全部")
    parser.add_argument("--group", "-g", type=str, default=None,
                        help="按 config.py 中的分组名筛选（如 '猴子警长系列'）")
    parser.add_argument("--llm", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--ref", type=str, default="", help="参考资料文件路径")
    parser.add_argument("--list", "-l", action="store_true", help="列出数据库中所有可用关键词")
    parser.add_argument("--force", "-f", action="store_true", help="强制重新生成已有报告的关键词（默认跳过）")
    parser.add_argument("--month", type=str, default=datetime.now().strftime("%Y-%m"), help="报告月份，格式 YYYY-MM，默认当前月")
    args = parser.parse_args()
    try:
        datetime.strptime(args.month, "%Y-%m")
    except ValueError:
        parser.error("--month 必须为 YYYY-MM")

    # 加载参考资料
    reference_content = ""
    if args.ref:
        try:
            with open(args.ref, encoding="utf-8") as f:
                reference_content = f.read().strip()
            print(f"[参考资料] 已加载：{args.ref}（{len(reference_content)} 字）")
        except Exception as e:
            print(f"[错误] 参考文件读取失败：{e}")
            sys.exit(1)

    repo = KeywordRepository()
    db_keywords = repo.get_keywords()

    # --list: 打印可用关键词后退出
    if args.list:
        print(f"数据库中共 {len(db_keywords)} 个关键词：")
        for kw in sorted(db_keywords):
            print(f"  - {kw}")
        return

    # 确定要生成的关键词列表
    if args.keywords:
        target_keywords = args.keywords
    elif args.group:
        if args.group not in IP_KEYWORDS:
            available = ", ".join(IP_KEYWORDS.keys())
            print(f"[错误] 未知分组 '{args.group}'，可用分组：{available}")
            sys.exit(1)
        target_keywords = IP_KEYWORDS[args.group]
        print(f"[分组] {args.group} → {len(target_keywords)} 个关键词")
    else:
        target_keywords = list(db_keywords)
        print(f"[全部] 共 {len(target_keywords)} 个关键词")

    # 过滤出数据库中实际存在的关键词
    valid_keywords = [kw for kw in target_keywords if kw in db_keywords]
    missing = [kw for kw in target_keywords if kw not in db_keywords]

    if missing:
        print(f"[跳过] 以下关键词在数据库中无数据：{missing}")

    if not valid_keywords:
        print("[结束] 没有可生成的关键词")
        return

    print(f"\n{'='*60}")
    print(f"待生成报告：{len(valid_keywords)} 个关键词")
    print("LLM 模式：开启")
    print(f"{'='*60}\n")

    generator = Generator()
    report_repo = ReportRepository()
    success = 0
    failed = 0
    skipped = 0
    start_time = time.time()

    for i, keyword in enumerate(valid_keywords, 1):
        if not args.force and report_repo.exists(keyword, args.month):
            print(f"\n[{i}/{len(valid_keywords)}] 跳过已有报告：{keyword}（使用 --force 强制重新生成）")
            skipped += 1
            continue

        print(f"\n[{i}/{len(valid_keywords)}] 生成报告：{keyword}")
        print("-" * 40)
        try:
            generator.run_one(keyword, use_llm=True, reference_content=reference_content, report_month=args.month)
            success += 1
        except Exception as e:
            print(f"[失败] {keyword}: {e}")
            failed += 1

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"完成！成功={success}  跳过={skipped}  失败={failed}  耗时={elapsed:.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
