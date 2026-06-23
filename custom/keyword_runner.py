import random
import subprocess
import time
from pathlib import Path

from custom.db import get_conn

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class KeywordRunner:

    def __init__(self, config):
        self.config = config

    def get_keywords(self):
        conn = get_conn()

        try:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT keyword
                    FROM crawler_keyword
                    WHERE status = 1
                """)

                rows = cursor.fetchall()

                return [
                    row['keyword'].strip()
                    for row in rows
                    if row['keyword'] and row['keyword'].strip()
                ]

        finally:
            conn.close()

    def get_current_month_keywords(self):
        conn = get_conn()

        try:
            with conn.cursor() as cursor:

                sql = f"""
                    SELECT DISTINCT
                        {self.config["keyword_field"]}
                    FROM
                        {self.config["keyword_table"]}
                    WHERE
                        {self.config["keyword_field"]} IS NOT NULL
                        AND {self.config["keyword_field"]} <> ''
                        AND {self.config["keyword_update_field"]} IS NOT NULL
                        AND YEAR(
                            FROM_UNIXTIME(
                                {self.config["keyword_update_field"]}/1000
                            )
                        ) = YEAR(CURDATE())
                        AND MONTH(
                            FROM_UNIXTIME(
                                {self.config["keyword_update_field"]}/1000
                            )
                        ) = MONTH(CURDATE())
                """

                cursor.execute(sql)

                return {
                    row[self.config["keyword_field"]].strip()
                    for row in cursor.fetchall()
                    if row[self.config["keyword_field"]]
                }

        finally:
            conn.close()

    def run_keyword(self, keyword):

        cmd = [
            "uv",
            "run",
            "main.py",
            "--platform",
            self.config["platform"],
            "--type",
            "search",
            "--keywords",
            keyword,
        ]

        cmd.extend(self.config["cmd_args"])

        print("=" * 80)
        print(f"开始执行关键词: {keyword}")
        print(" ".join(cmd))

        subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            check=True
        )

    def run(self):

        keywords = self.get_keywords()

        current_month_keywords = (
            self.get_current_month_keywords()
        )

        need_run_keywords = [
            keyword
            for keyword in keywords
            if keyword not in current_month_keywords
        ]

        print(f"本次需要抓取关键词数量: {len(need_run_keywords)}")

        total = len(need_run_keywords)

        for index, keyword in enumerate(
                need_run_keywords,
                start=1):

            print(f"\n[{index}/{total}]")

            self.run_keyword(keyword)

            if index < total:

                sleep_seconds = random.randint(
                    self.config["sleep_min"],
                    self.config["sleep_max"]
                )

                print(
                    f"等待 {sleep_seconds} 秒后继续..."
                )

                time.sleep(sleep_seconds)