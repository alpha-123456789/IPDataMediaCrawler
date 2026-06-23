# custom/keyword_insight/repository.py

from custom.db import get_conn


class KeywordRepository:

    def get_keywords(self):
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT source_keyword
                    FROM xhs_note
                    WHERE source_keyword IS NOT NULL
                    AND source_keyword <> ''
                """)
                return [r["source_keyword"] for r in cur.fetchall()]
        finally:
            conn.close()

    def load_data(self, keyword):
        conn = get_conn()
        try:
            with conn.cursor() as cur:

                cur.execute("""
                    SELECT * FROM xhs_note
                    WHERE source_keyword=%s
                """, (keyword,))
                notes = cur.fetchall()

                cur.execute("""
                    SELECT c.*
                    FROM xhs_note_comment c
                    JOIN xhs_note n ON c.note_id=n.note_id
                    WHERE n.source_keyword=%s
                """, (keyword,))
                comments = cur.fetchall()

                cur.execute("""
                    SELECT DISTINCT c.*
                    FROM xhs_creator c
                    JOIN xhs_note n ON c.user_id=n.user_id
                    WHERE n.source_keyword=%s
                """, (keyword,))
                creators = cur.fetchall()

            return notes, comments, creators

        finally:
            conn.close()