# custom/keyword_insight/repository.py

from custom.db import get_conn


def _pid(platform, raw_id):
    """为 note_id 加平台前缀，避免跨平台 ID 碰撞"""
    return f"{platform}_{raw_id}"


class KeywordRepository:

    # ──────────────────────────────────────────────
    # 公共接口
    # ──────────────────────────────────────────────

    def get_keywords(self):
        """从所有平台表收集去重关键词"""
        tables = [
            "xhs_note",
            "bilibili_video",
            "douyin_aweme",
            "kuaishou_video",
            "weibo_note",
            "tieba_note",
            "zhihu_content",
        ]
        conn = get_conn()
        try:
            keywords = set()
            with conn.cursor() as cur:
                for table in tables:
                    try:
                        cur.execute(f"""
                            SELECT DISTINCT source_keyword
                            FROM {table}
                            WHERE source_keyword IS NOT NULL
                            AND source_keyword <> ''
                        """)
                        for r in cur.fetchall():
                            keywords.add(r["source_keyword"])
                    except Exception:
                        pass
            return list(keywords)
        finally:
            conn.close()

    def load_data(self, keyword):
        """从所有平台加载并归一化数据，返回 (notes, comments, creators, creator_count)"""
        loaders = [
            self._load_xhs,
            self._load_bilibili,
            self._load_douyin,
            self._load_kuaishou,
            self._load_weibo,
            self._load_tieba,
            self._load_zhihu,
        ]
        conn = get_conn()
        try:
            all_notes, all_comments, all_creators = [], [], []
            with conn.cursor() as cur:
                for loader in loaders:
                    try:
                        notes, comments, creators = loader(keyword, cur)
                        all_notes.extend(notes)
                        all_comments.extend(comments)
                        all_creators.extend(creators)
                    except Exception:
                        pass

            creator_count = len(set(
                n["user_id"] for n in all_notes if n.get("user_id")
            ))
            return all_notes, all_comments, all_creators, creator_count
        finally:
            conn.close()

    # ──────────────────────────────────────────────
    # 各平台加载器（返回归一化字段）
    # ──────────────────────────────────────────────

    def _load_xhs(self, keyword, cur):
        cur.execute("SELECT * FROM xhs_note WHERE source_keyword=%s", (keyword,))
        raw_notes = cur.fetchall()
        if not raw_notes:
            return [], [], []

        notes = [{
            "note_id": _pid("xhs", n["note_id"]),
            "user_id": n.get("user_id"),
            "title": n.get("title"),
            "desc": n.get("desc"),
            "liked_count": n.get("liked_count"),
            "collected_count": n.get("collected_count"),
            "comment_count": n.get("comment_count"),
            "share_count": n.get("share_count"),
            "ip_location": n.get("ip_location"),
            "tag_list": n.get("tag_list"),
            "time": n.get("time"),
            "platform": "xhs",
        } for n in raw_notes]

        cur.execute("""
            SELECT c.*
            FROM xhs_note_comment c
            JOIN xhs_note n ON c.note_id=n.note_id
            WHERE n.source_keyword=%s
        """, (keyword,))
        comments = [{
            "content": c.get("content"),
            "like_count": c.get("like_count"),
            "sub_comment_count": c.get("sub_comment_count"),
            "create_time": c.get("create_time"),
            "note_id": _pid("xhs", c.get("note_id")),
            "ip_location": c.get("ip_location"),
        } for c in cur.fetchall()]

        cur.execute("""
            SELECT DISTINCT c.*
            FROM xhs_creator c
            JOIN xhs_note n ON c.user_id=n.user_id
            WHERE n.source_keyword=%s
        """, (keyword,))
        creators = [{
            "user_id": c["user_id"],
            "nickname": c.get("nickname"),
            "gender": c.get("gender"),
            "fans": c.get("fans"),
            "interaction": c.get("interaction"),
        } for c in cur.fetchall()]

        return notes, comments, creators

    def _load_bilibili(self, keyword, cur):
        cur.execute("SELECT * FROM bilibili_video WHERE source_keyword=%s", (keyword,))
        raw_notes = cur.fetchall()
        if not raw_notes:
            return [], [], []

        notes = [{
            "note_id": _pid("bili", n["video_id"]),
            "user_id": str(n.get("user_id", "")),
            "title": n.get("title"),
            "desc": n.get("desc"),
            "liked_count": n.get("liked_count"),
            "collected_count": n.get("video_favorite_count"),
            "comment_count": n.get("video_comment"),
            "share_count": n.get("video_share_count"),
            "ip_location": "",
            "tag_list": "",
            "time": n.get("create_time"),
            "platform": "bilibili",
        } for n in raw_notes]

        video_ids = [n["video_id"] for n in raw_notes]
        placeholders = ",".join(["%s"] * len(video_ids))
        cur.execute(
            f"SELECT * FROM bilibili_video_comment WHERE video_id IN ({placeholders})",
            video_ids
        )
        comments = [{
            "content": c.get("content"),
            "like_count": c.get("like_count"),
            "sub_comment_count": c.get("sub_comment_count"),
            "create_time": c.get("create_time"),
            "note_id": _pid("bili", c.get("video_id")),
            "ip_location": "",
        } for c in cur.fetchall()]

        user_ids = list(set(str(n["user_id"]) for n in raw_notes if n.get("user_id")))
        creators = []
        if user_ids:
            placeholders = ",".join(["%s"] * len(user_ids))
            cur.execute(
                f"SELECT * FROM bilibili_up_info WHERE user_id IN ({placeholders})",
                user_ids
            )
            creators = [{
                "user_id": str(c["user_id"]),
                "nickname": c.get("nickname"),
                "gender": c.get("sex"),
                "fans": c.get("total_fans"),
                "interaction": c.get("total_liked"),
            } for c in cur.fetchall()]

        return notes, comments, creators

    def _load_douyin(self, keyword, cur):
        cur.execute("SELECT * FROM douyin_aweme WHERE source_keyword=%s", (keyword,))
        raw_notes = cur.fetchall()
        if not raw_notes:
            return [], [], []

        notes = [{
            "note_id": _pid("dy", n["aweme_id"]),
            "user_id": n.get("user_id"),
            "title": n.get("title"),
            "desc": n.get("desc"),
            "liked_count": n.get("liked_count"),
            "collected_count": n.get("collected_count"),
            "comment_count": n.get("comment_count"),
            "share_count": n.get("share_count"),
            "ip_location": n.get("ip_location"),
            "tag_list": "",
            "time": n.get("create_time"),
            "platform": "douyin",
        } for n in raw_notes]

        aweme_ids = [n["aweme_id"] for n in raw_notes]
        placeholders = ",".join(["%s"] * len(aweme_ids))
        cur.execute(
            f"SELECT * FROM douyin_aweme_comment WHERE aweme_id IN ({placeholders})",
            aweme_ids
        )
        comments = [{
            "content": c.get("content"),
            "like_count": c.get("like_count"),
            "sub_comment_count": c.get("sub_comment_count"),
            "create_time": c.get("create_time"),
            "note_id": _pid("dy", c.get("aweme_id")),
            "ip_location": c.get("ip_location"),
        } for c in cur.fetchall()]

        user_ids = list(set(n["user_id"] for n in raw_notes if n.get("user_id")))
        creators = []
        if user_ids:
            placeholders = ",".join(["%s"] * len(user_ids))
            cur.execute(
                f"SELECT * FROM dy_creator WHERE user_id IN ({placeholders})",
                user_ids
            )
            creators = [{
                "user_id": c["user_id"],
                "nickname": c.get("nickname"),
                "gender": c.get("gender"),
                "fans": c.get("fans"),
                "interaction": c.get("interaction"),
            } for c in cur.fetchall()]

        return notes, comments, creators

    def _load_kuaishou(self, keyword, cur):
        cur.execute("SELECT * FROM kuaishou_video WHERE source_keyword=%s", (keyword,))
        raw_notes = cur.fetchall()
        if not raw_notes:
            return [], [], []

        notes = [{
            "note_id": _pid("ks", n["video_id"]),
            "user_id": n.get("user_id"),
            "title": n.get("title"),
            "desc": n.get("desc"),
            "liked_count": n.get("liked_count"),
            "collected_count": "0",
            "comment_count": "0",
            "share_count": "0",
            "ip_location": "",
            "tag_list": "",
            "time": n.get("create_time"),
            "platform": "kuaishou",
        } for n in raw_notes]

        video_ids = [n["video_id"] for n in raw_notes]
        placeholders = ",".join(["%s"] * len(video_ids))
        cur.execute(
            f"SELECT * FROM kuaishou_video_comment WHERE video_id IN ({placeholders})",
            video_ids
        )
        comments = [{
            "content": c.get("content"),
            "like_count": "0",
            "sub_comment_count": c.get("sub_comment_count"),
            "create_time": c.get("create_time"),
            "note_id": _pid("ks", c.get("video_id")),
            "ip_location": "",
        } for c in cur.fetchall()]

        return notes, comments, []

    def _load_weibo(self, keyword, cur):
        cur.execute("SELECT * FROM weibo_note WHERE source_keyword=%s", (keyword,))
        raw_notes = cur.fetchall()
        if not raw_notes:
            return [], [], []

        notes = [{
            "note_id": _pid("wb", n["note_id"]),
            "user_id": n.get("user_id"),
            "title": "",
            "desc": n.get("content"),
            "liked_count": n.get("liked_count"),
            "collected_count": "0",
            "comment_count": n.get("comments_count"),
            "share_count": n.get("shared_count"),
            "ip_location": n.get("ip_location"),
            "tag_list": "",
            "time": n.get("create_time"),
            "platform": "weibo",
        } for n in raw_notes]

        note_ids = [n["note_id"] for n in raw_notes]
        placeholders = ",".join(["%s"] * len(note_ids))
        cur.execute(
            f"SELECT * FROM weibo_note_comment WHERE note_id IN ({placeholders})",
            note_ids
        )
        comments = [{
            "content": c.get("content"),
            "like_count": c.get("comment_like_count"),
            "sub_comment_count": c.get("sub_comment_count"),
            "create_time": c.get("create_time"),
            "note_id": _pid("wb", c.get("note_id")),
            "ip_location": c.get("ip_location"),
        } for c in cur.fetchall()]

        user_ids = list(set(n["user_id"] for n in raw_notes if n.get("user_id")))
        creators = []
        if user_ids:
            placeholders = ",".join(["%s"] * len(user_ids))
            cur.execute(
                f"SELECT * FROM weibo_creator WHERE user_id IN ({placeholders})",
                user_ids
            )
            creators = [{
                "user_id": c["user_id"],
                "nickname": c.get("nickname"),
                "gender": c.get("gender"),
                "fans": c.get("fans"),
                "interaction": "0",
            } for c in cur.fetchall()]

        return notes, comments, creators

    def _load_tieba(self, keyword, cur):
        cur.execute("SELECT * FROM tieba_note WHERE source_keyword=%s", (keyword,))
        raw_notes = cur.fetchall()
        if not raw_notes:
            return [], [], []

        notes = [{
            "note_id": _pid("tieba", n["note_id"]),
            "user_id": n.get("user_link") or n.get("user_nickname"),
            "title": n.get("title"),
            "desc": n.get("desc"),
            "liked_count": "0",
            "collected_count": "0",
            "comment_count": str(n.get("total_replay_num") or 0),
            "share_count": "0",
            "ip_location": n.get("ip_location"),
            "tag_list": "",
            "time": None,
            "platform": "tieba",
        } for n in raw_notes]

        note_ids = [n["note_id"] for n in raw_notes]
        placeholders = ",".join(["%s"] * len(note_ids))
        cur.execute(
            f"SELECT * FROM tieba_comment WHERE note_id IN ({placeholders})",
            note_ids
        )
        comments = [{
            "content": c.get("content"),
            "like_count": "0",
            "sub_comment_count": str(c.get("sub_comment_count") or 0),
            "create_time": None,
            "note_id": _pid("tieba", c.get("note_id")),
            "ip_location": c.get("ip_location"),
        } for c in cur.fetchall()]

        return notes, comments, []

    def _load_zhihu(self, keyword, cur):
        cur.execute("SELECT * FROM zhihu_content WHERE source_keyword=%s", (keyword,))
        raw_notes = cur.fetchall()
        if not raw_notes:
            return [], [], []

        notes = [{
            "note_id": _pid("zhihu", n["content_id"]),
            "user_id": n.get("user_id"),
            "title": n.get("title"),
            "desc": n.get("content_text") or n.get("desc"),
            "liked_count": str(n.get("voteup_count") or 0),
            "collected_count": "0",
            "comment_count": str(n.get("comment_count") or 0),
            "share_count": "0",
            "ip_location": "",
            "tag_list": "",
            "time": None,
            "platform": "zhihu",
        } for n in raw_notes]

        content_ids = [n["content_id"] for n in raw_notes]
        placeholders = ",".join(["%s"] * len(content_ids))
        cur.execute(
            f"SELECT * FROM zhihu_comment WHERE content_id IN ({placeholders})",
            content_ids
        )
        comments = [{
            "content": c.get("content"),
            "like_count": str(c.get("like_count") or 0),
            "sub_comment_count": str(c.get("sub_comment_count") or 0),
            "create_time": None,
            "note_id": _pid("zhihu", c.get("content_id")),
            "ip_location": c.get("ip_location"),
        } for c in cur.fetchall()]

        user_ids = list(set(n["user_id"] for n in raw_notes if n.get("user_id")))
        creators = []
        if user_ids:
            placeholders = ",".join(["%s"] * len(user_ids))
            cur.execute(
                f"SELECT * FROM zhihu_creator WHERE user_id IN ({placeholders})",
                user_ids
            )
            creators = [{
                "user_id": c["user_id"],
                "nickname": c.get("user_nickname"),
                "gender": c.get("gender"),
                "fans": str(c.get("fans") or 0),
                "interaction": str(c.get("get_voteup_count") or 0),
            } for c in cur.fetchall()]

        return notes, comments, creators
