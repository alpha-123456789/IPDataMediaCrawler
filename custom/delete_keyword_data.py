import sys

from custom.db import get_conn


def delete_keyword_data(keyword: str):
    conn = get_conn()

    try:
        with conn.cursor() as cursor:

            # 查询关联 note_id、user_id
            cursor.execute(
                """
                SELECT DISTINCT note_id, user_id
                FROM xhs_note
                WHERE source_keyword = %s
                """,
                (keyword,)
            )

            rows = cursor.fetchall()

            if not rows:
                print(f"未找到关键词数据: {keyword}")
                return

            note_ids = {
                str(row['note_id']).strip()
                for row in rows
                if row['note_id']
            }

            user_ids = {
                str(row['user_id']).strip()
                for row in rows
                if row['user_id']
            }

            print("=" * 80)
            print(f"关键词: {keyword}")
            print(f"关联笔记数量: {len(note_ids)}")
            print(f"关联创作者数量: {len(user_ids)}")
            print("=" * 80)

            # ------------------------------------------------------------------
            # 删除评论
            # ------------------------------------------------------------------

            comment_deleted = 0

            if note_ids:
                placeholders = ",".join(["%s"] * len(note_ids))

                sql = f"""
                    DELETE
                    FROM xhs_note_comment
                    WHERE note_id IN ({placeholders})
                """

                comment_deleted = cursor.execute(
                    sql,
                    list(note_ids)
                )

            print(f"删除评论数量: {comment_deleted}")

            # ------------------------------------------------------------------
            # 删除笔记
            # ------------------------------------------------------------------

            note_deleted = cursor.execute(
                """
                DELETE
                FROM xhs_note
                WHERE source_keyword = %s
                """,
                (keyword,)
            )

            print(f"删除笔记数量: {note_deleted}")

            # ------------------------------------------------------------------
            # 安全删除创作者
            # ------------------------------------------------------------------

            creator_deleted = 0

            for user_id in user_ids:

                cursor.execute(
                    """
                    SELECT COUNT(1) AS cnt
                    FROM xhs_note
                    WHERE user_id = %s
                    """,
                    (user_id,)
                )

                remain_count = cursor.fetchone()['cnt']

                if remain_count == 0:

                    creator_deleted += cursor.execute(
                        """
                        DELETE
                        FROM xhs_creator
                        WHERE user_id = %s
                        """,
                        (user_id,)
                    )

            print(f"删除创作者数量: {creator_deleted}")

            # ------------------------------------------------------------------
            # 删除关键词报告
            # ------------------------------------------------------------------

            report_deleted = cursor.execute(
                """
                DELETE
                FROM keyword_report
                WHERE keyword = %s
                """,
                (keyword,)
            )

            print(f"删除关键词报告数量: {report_deleted}")

        conn.commit()

        print("=" * 80)
        print("删除完成")
        print("=" * 80)

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print(
            "用法:\n"
            "python custom/delete_keyword_data.py 猴子警长"
        )
        sys.exit(1)

    delete_keyword_data(sys.argv[1])