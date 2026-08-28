import json
from custom.db import get_conn


class CustomReportRepository:
    """保存后台任务生成的自定义关键词报告。"""

    def save(
        self,
        report_name,
        platform,
        source_keyword,
        start_date,
        end_date,
        post_ids,
        prompt,
        report_content,
    ):
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id
                    FROM keyword_report
                    WHERE report_name = %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (report_name,),
                )
                existing_report = cur.fetchone()
                if existing_report:
                    cur.execute(
                        """
                        UPDATE keyword_report
                        SET platform = %s,
                            source_keyword = %s,
                            start_date = %s,
                            end_date = %s,
                            post_ids = %s,
                            prompt = %s,
                            report_content = %s,
                            update_time = UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000
                        WHERE report_name = %s
                        """,
                        (
                            platform,
                            source_keyword,
                            start_date,
                            end_date,
                            post_ids,
                            prompt,
                            report_content,
                            report_name,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO keyword_report
                        (
                            report_name,
                            platform,
                            source_keyword,
                            start_date,
                            end_date,
                            post_ids,
                            prompt,
                            report_content,
                            create_time,
                            update_time
                        )
                        VALUES
                        (
                            %s, %s, %s, %s, %s, %s, %s, %s,
                            UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000,
                            UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000
                        )
                        """,
                        (
                            report_name,
                            platform,
                            source_keyword,
                            start_date,
                            end_date,
                            post_ids,
                            prompt,
                            report_content,
                        ),
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


class ReportRepository:
    def exists(self, keyword, report_month):
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM keyword_report WHERE keyword=%s AND report_month=%s LIMIT 1", (keyword, report_month))
                return cur.fetchone() is not None
        finally:
            conn.close()

    def save(self, keyword, report_month, notes, comments, creators, topics, roles, concerns, questions, sentiment, report, engagement, geography, creator_analysis, tags, time_trend, mode="template"):
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO keyword_report
                    (keyword,report_month,note_count,comment_count,creator_count,topics_json,roles_json,concerns_json,questions_json,sentiment_json,report_content,engagement_json,geography_json,creators_analysis_json,tags_json,time_trend_json,mode)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                    note_count=VALUES(note_count), comment_count=VALUES(comment_count), creator_count=VALUES(creator_count), topics_json=VALUES(topics_json), roles_json=VALUES(roles_json), concerns_json=VALUES(concerns_json), questions_json=VALUES(questions_json), sentiment_json=VALUES(sentiment_json), report_content=VALUES(report_content), engagement_json=VALUES(engagement_json), geography_json=VALUES(geography_json), creators_analysis_json=VALUES(creators_analysis_json), tags_json=VALUES(tags_json), time_trend_json=VALUES(time_trend_json), mode=VALUES(mode)
                """, (keyword, report_month, len(notes), len(comments), len(creators), json.dumps(topics, ensure_ascii=False), json.dumps(roles, ensure_ascii=False), json.dumps(concerns, ensure_ascii=False), json.dumps(questions, ensure_ascii=False), json.dumps(sentiment, ensure_ascii=False), report, json.dumps(engagement, ensure_ascii=False), json.dumps(geography, ensure_ascii=False), json.dumps(creator_analysis, ensure_ascii=False), json.dumps(tags, ensure_ascii=False), json.dumps(time_trend, ensure_ascii=False), mode))
            conn.commit()
        finally:
            conn.close()
