import subprocess
from pathlib import Path

from custom.db import get_conn

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CreatorRunner:

    def __init__(self, config):
        self.config = config

    def get_source_user_ids(self):

        conn = get_conn()

        try:
            with conn.cursor() as cursor:

                sql = f"""
                    SELECT DISTINCT
                        {self.config["source_user_id_field"]}
                    FROM
                        {self.config["source_table"]}
                    WHERE
                        {self.config["source_user_id_field"]} IS NOT NULL
                        AND {self.config["source_user_id_field"]} <> ''
                """

                cursor.execute(sql)

                return [
                    str(row[self.config["target_user_id_field"]]).strip()
                    for row in cursor.fetchall()
                    if row[self.config["target_user_id_field"]]
                ]

        finally:
            conn.close()

    def get_current_month_user_ids(self):

        conn = get_conn()

        try:
            with conn.cursor() as cursor:

                sql = f"""
                    SELECT DISTINCT
                        {self.config["target_user_id_field"]}
                    FROM
                        {self.config["target_table"]}
                    WHERE
                        {self.config["target_user_id_field"]} IS NOT NULL
                        AND {self.config["target_user_id_field"]} <> ''
                        AND {self.config["target_update_field"]} IS NOT NULL
                        AND YEAR(
                            FROM_UNIXTIME(
                                {self.config["target_update_field"]}/1000
                            )
                        ) = YEAR(CURDATE())
                        AND MONTH(
                            FROM_UNIXTIME(
                                {self.config["target_update_field"]}/1000
                            )
                        ) = MONTH(CURDATE())
                """

                cursor.execute(sql)

                return {
                    str(row[self.config["target_user_id_field"]]).strip()
                    for row in cursor.fetchall()
                    if row[self.config["target_user_id_field"]]
                }

        finally:
            conn.close()

    def chunk(self, items, size):

        for i in range(0, len(items), size):
            yield items[i:i + size]

    def run_batch(self, user_ids):

        creator_ids = ",".join(user_ids)

        cmd = [
            "uv",
            "run",
            "main.py",
            "--platform",
            self.config["platform"],
            "--type",
            "creator",
            "--creator_id",
            creator_ids,
        ]

        print("=" * 80)
        print(f"开始执行，共 {len(user_ids)} 个账号")

        subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            check=True
        )

    def run(self):

        source_ids = self.get_source_user_ids()

        current_month_ids = (
            self.get_current_month_user_ids()
        )

        need_crawl_ids = [
            user_id
            for user_id in source_ids
            if user_id not in current_month_ids
        ]

        print(
            f"本次需要抓取账号数量: {len(need_crawl_ids)}"
        )

        if not need_crawl_ids:
            return

        for batch in self.chunk(
            need_crawl_ids,
            self.config["batch_size"]
        ):
            self.run_batch(batch)