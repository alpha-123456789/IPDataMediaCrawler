import json
from custom.db import get_conn


class ReportRepository:

    def save(self, keyword, notes, comments, creators,
             topics, roles, concerns, questions,
             sentiment, report,
             engagement, geography, creator_analysis,
             tags, time_trend, mode="template"):

        conn = get_conn()

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO keyword_report
                    (keyword,note_count,comment_count,creator_count,
                     topics_json,roles_json,concerns_json,
                     questions_json,sentiment_json,report_content,
                     engagement_json,geography_json,creators_analysis_json,
                     tags_json,time_trend_json,mode)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                    note_count=VALUES(note_count),
                    comment_count=VALUES(comment_count),
                    creator_count=VALUES(creator_count),
                    topics_json=VALUES(topics_json),
                    roles_json=VALUES(roles_json),
                    concerns_json=VALUES(concerns_json),
                    questions_json=VALUES(questions_json),
                    sentiment_json=VALUES(sentiment_json),
                    report_content=VALUES(report_content),
                    engagement_json=VALUES(engagement_json),
                    geography_json=VALUES(geography_json),
                    creators_analysis_json=VALUES(creators_analysis_json),
                    tags_json=VALUES(tags_json),
                    time_trend_json=VALUES(time_trend_json),
                    mode=VALUES(mode)
                """, (
                    keyword,
                    len(notes),
                    len(comments),
                    len(creators),
                    json.dumps(topics, ensure_ascii=False),
                    json.dumps(roles, ensure_ascii=False),
                    json.dumps(concerns, ensure_ascii=False),
                    json.dumps(questions, ensure_ascii=False),
                    json.dumps(sentiment, ensure_ascii=False),
                    report,
                    json.dumps(engagement, ensure_ascii=False),
                    json.dumps(geography, ensure_ascii=False),
                    json.dumps(creator_analysis, ensure_ascii=False),
                    json.dumps(tags, ensure_ascii=False),
                    json.dumps(time_trend, ensure_ascii=False),
                    mode,
                ))

            conn.commit()

        finally:
            conn.close()
