# -*- coding: utf-8 -*-
"""
按自定义提示词和帖子筛选条件生成洞察报告。

用法：
  uv run -m custom.keyword_insight.custom_report ^
    --prompt "分析用户对产品品质和购买意愿的反馈，并给出建议" ^
    --start-date 2026-07-01 ^
    --end-date 2026-07-31

  uv run -m custom.keyword_insight.custom_report ^
    --prompt "总结争议点" ^
    --start-date 2026-07-01 ^
    --end-date 2026-07-31 ^
    --platform xhs ^
    --post-ids abc123 def456

--post-ids 仅接受 --platform 对应平台的原始帖子 ID。
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from custom.db import get_conn
from custom.keyword_insight.analyzer import Analyzer
from custom.keyword_insight.report_builder import AI_FAILURE_MESSAGE, generate_llm_report
from custom.keyword_insight.report_repository import CustomReportRepository
from custom.keyword_insight.sentiment import SentimentAnalyzer


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
PLATFORMS = ("xhs", "bili", "dy", "ks", "wb", "tieba", "zhihu")


def _pid(platform, raw_id):
    return f"{platform}_{raw_id}"


@dataclass(frozen=True)
class DateRange:
    start_date: str
    end_date: str
    start_ts: int
    end_ts: int
    end_exclusive_date: str


def parse_date_range(start_date, end_date):
    """校验日期，并将结束日期转换为左闭右开的查询边界。"""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=SHANGHAI_TZ)
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=SHANGHAI_TZ)
    except ValueError as exc:
        raise ValueError("日期必须为 YYYY-MM-DD 格式") from exc

    if start > end:
        raise ValueError("开始日期不能晚于结束日期")

    end_exclusive = end + timedelta(days=1)
    return DateRange(
        start_date=start_date,
        end_date=end_date,
        start_ts=int(start.timestamp()),
        end_ts=int(end_exclusive.timestamp()),
        end_exclusive_date=end_exclusive.strftime("%Y-%m-%d"),
    )


def parse_post_ids(values):
    """支持以空格、逗号或换行分隔的帖子 ID。"""
    post_ids = []
    for value in values or []:
        for post_id in re.split(r"[\s,]+", value.strip()):
            if post_id and post_id not in post_ids:
                post_ids.append(post_id)
    return post_ids


def _in_clause(column, values):
    if not values:
        return "", []
    placeholders = ",".join(["%s"] * len(values))
    return f" AND {column} IN ({placeholders})", values


def _timestamp_where(column, date_range, post_id_column, post_ids, multiplier=1):
    post_clause, post_params = _in_clause(post_id_column, post_ids)
    return (
        f"{column} >= %s AND {column} < %s{post_clause}",
        [
            date_range.start_ts * multiplier,
            date_range.end_ts * multiplier,
            *post_params,
        ],
    )


def _date_string_where(column, date_range, post_id_column, post_ids):
    post_clause, post_params = _in_clause(post_id_column, post_ids)
    return (
        f"{column} >= %s AND {column} < %s{post_clause}",
        [date_range.start_date, date_range.end_exclusive_date, *post_params],
    )


class FilteredPostRepository:
    """加载发布日期和帖子 ID 均符合条件的跨平台帖子及其关联数据。"""

    def __init__(self, date_range, platform, post_ids=None):
        self.date_range = date_range
        self.platform = platform
        self.post_ids = post_ids or []

    def load_data(self):
        loaders = (
            self._load_xhs,
            self._load_bilibili,
            self._load_douyin,
            self._load_kuaishou,
            self._load_weibo,
            self._load_tieba,
            self._load_zhihu,
        )
        all_notes, all_comments, all_creators = [], [], []
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                for loader in loaders:
                    notes, comments, creators = loader(cur)
                    all_notes.extend(notes)
                    all_comments.extend(comments)
                    all_creators.extend(creators)
        finally:
            conn.close()

        creator_count = len({note["user_id"] for note in all_notes if note.get("user_id")})
        return all_notes, all_comments, self._deduplicate_creators(all_creators), creator_count

    @staticmethod
    def _deduplicate_creators(creators):
        unique = {}
        for creator in creators:
            user_id = creator.get("user_id")
            if user_id:
                unique.setdefault(str(user_id), creator)
        return list(unique.values())

    @staticmethod
    def _normalize_timestamp(value):
        try:
            timestamp = int(value)
            return timestamp // 1000 if timestamp >= 1_000_000_000_000 else timestamp
        except (TypeError, ValueError):
            return None

    def _load_posts(self, cur, table, id_column, time_where, platform):
        if self.platform != platform:
            return []

        where_sql, params = time_where(id_column, self.post_ids)
        cur.execute(f"SELECT * FROM {table} WHERE {where_sql}", params)
        return cur.fetchall()

    @staticmethod
    def _load_comments(cur, table, foreign_key, raw_ids, normalizer):
        if not raw_ids:
            return []
        placeholders = ",".join(["%s"] * len(raw_ids))
        cur.execute(f"SELECT * FROM {table} WHERE {foreign_key} IN ({placeholders})", raw_ids)
        return [normalizer(item) for item in cur.fetchall()]

    @staticmethod
    def _load_creators(cur, table, user_ids, normalizer):
        if not user_ids:
            return []
        placeholders = ",".join(["%s"] * len(user_ids))
        cur.execute(f"SELECT * FROM {table} WHERE user_id IN ({placeholders})", user_ids)
        return [normalizer(item) for item in cur.fetchall()]

    def _load_xhs(self, cur):
        raw_notes = self._load_posts(
            cur,
            "xhs_note",
            "note_id",
            lambda id_column, ids: _timestamp_where(
                "time",
                self.date_range,
                id_column,
                ids,
                multiplier=1000,
            ),
            "xhs",
        )
        raw_ids = [item["note_id"] for item in raw_notes]
        notes = [{
            "note_id": _pid("xhs", item["note_id"]),
            "user_id": item.get("user_id"),
            "title": item.get("title"),
            "desc": item.get("desc"),
            "liked_count": item.get("liked_count"),
            "collected_count": item.get("collected_count"),
            "comment_count": item.get("comment_count"),
            "share_count": item.get("share_count"),
            "ip_location": item.get("ip_location"),
            "tag_list": item.get("tag_list"),
            "time": self._normalize_timestamp(item.get("time")),
            "platform": "xhs",
        } for item in raw_notes]
        comments = self._load_comments(
            cur,
            "xhs_note_comment",
            "note_id",
            raw_ids,
            lambda item: {
                "content": item.get("content"),
                "like_count": item.get("like_count"),
                "sub_comment_count": item.get("sub_comment_count"),
                "create_time": item.get("create_time"),
                "note_id": _pid("xhs", item.get("note_id")),
                "ip_location": item.get("ip_location"),
            },
        )
        creators = self._load_creators(
            cur,
            "xhs_creator",
            list({item.get("user_id") for item in raw_notes if item.get("user_id")}),
            lambda item: {
                "user_id": item["user_id"],
                "nickname": item.get("nickname"),
                "gender": item.get("gender"),
                "fans": item.get("fans"),
                "interaction": item.get("interaction"),
            },
        )
        return notes, comments, creators

    def _load_bilibili(self, cur):
        raw_notes = self._load_posts(
            cur,
            "bilibili_video",
            "video_id",
            lambda id_column, ids: _timestamp_where("create_time", self.date_range, id_column, ids),
            "bili",
        )
        raw_ids = [item["video_id"] for item in raw_notes]
        notes = [{
            "note_id": _pid("bili", item["video_id"]),
            "user_id": str(item.get("user_id", "")),
            "title": item.get("title"),
            "desc": item.get("desc"),
            "liked_count": item.get("liked_count"),
            "collected_count": item.get("video_favorite_count"),
            "comment_count": item.get("video_comment"),
            "share_count": item.get("video_share_count"),
            "ip_location": "",
            "tag_list": "",
            "time": item.get("create_time"),
            "platform": "bilibili",
        } for item in raw_notes]
        comments = self._load_comments(
            cur,
            "bilibili_video_comment",
            "video_id",
            raw_ids,
            lambda item: {
                "content": item.get("content"),
                "like_count": item.get("like_count"),
                "sub_comment_count": item.get("sub_comment_count"),
                "create_time": item.get("create_time"),
                "note_id": _pid("bili", item.get("video_id")),
                "ip_location": "",
            },
        )
        creators = self._load_creators(
            cur,
            "bilibili_up_info",
            list({str(item["user_id"]) for item in raw_notes if item.get("user_id")}),
            lambda item: {
                "user_id": str(item["user_id"]),
                "nickname": item.get("nickname"),
                "gender": item.get("sex"),
                "fans": item.get("total_fans"),
                "interaction": item.get("total_liked"),
            },
        )
        return notes, comments, creators

    def _load_douyin(self, cur):
        raw_notes = self._load_posts(
            cur,
            "douyin_aweme",
            "aweme_id",
            lambda id_column, ids: _timestamp_where("create_time", self.date_range, id_column, ids),
            "dy",
        )
        raw_ids = [item["aweme_id"] for item in raw_notes]
        notes = [{
            "note_id": _pid("dy", item["aweme_id"]),
            "user_id": item.get("user_id"),
            "title": item.get("title"),
            "desc": item.get("desc"),
            "liked_count": item.get("liked_count"),
            "collected_count": item.get("collected_count"),
            "comment_count": item.get("comment_count"),
            "share_count": item.get("share_count"),
            "ip_location": item.get("ip_location"),
            "tag_list": "",
            "time": item.get("create_time"),
            "platform": "douyin",
        } for item in raw_notes]
        comments = self._load_comments(
            cur,
            "douyin_aweme_comment",
            "aweme_id",
            raw_ids,
            lambda item: {
                "content": item.get("content"),
                "like_count": item.get("like_count"),
                "sub_comment_count": item.get("sub_comment_count"),
                "create_time": item.get("create_time"),
                "note_id": _pid("dy", item.get("aweme_id")),
                "ip_location": item.get("ip_location"),
            },
        )
        creators = self._load_creators(
            cur,
            "dy_creator",
            list({item.get("user_id") for item in raw_notes if item.get("user_id")}),
            lambda item: {
                "user_id": item["user_id"],
                "nickname": item.get("nickname"),
                "gender": item.get("gender"),
                "fans": item.get("fans"),
                "interaction": item.get("interaction"),
            },
        )
        return notes, comments, creators

    def _load_kuaishou(self, cur):
        raw_notes = self._load_posts(
            cur,
            "kuaishou_video",
            "video_id",
            lambda id_column, ids: _timestamp_where("create_time", self.date_range, id_column, ids),
            "ks",
        )
        raw_ids = [item["video_id"] for item in raw_notes]
        notes = [{
            "note_id": _pid("ks", item["video_id"]),
            "user_id": item.get("user_id"),
            "title": item.get("title"),
            "desc": item.get("desc"),
            "liked_count": item.get("liked_count"),
            "collected_count": "0",
            "comment_count": "0",
            "share_count": "0",
            "ip_location": "",
            "tag_list": "",
            "time": item.get("create_time"),
            "platform": "kuaishou",
        } for item in raw_notes]
        comments = self._load_comments(
            cur,
            "kuaishou_video_comment",
            "video_id",
            raw_ids,
            lambda item: {
                "content": item.get("content"),
                "like_count": "0",
                "sub_comment_count": item.get("sub_comment_count"),
                "create_time": item.get("create_time"),
                "note_id": _pid("ks", item.get("video_id")),
                "ip_location": "",
            },
        )
        return notes, comments, []

    def _load_weibo(self, cur):
        raw_notes = self._load_posts(
            cur,
            "weibo_note",
            "note_id",
            lambda id_column, ids: _timestamp_where("create_time", self.date_range, id_column, ids),
            "wb",
        )
        raw_ids = [item["note_id"] for item in raw_notes]
        notes = [{
            "note_id": _pid("wb", item["note_id"]),
            "user_id": item.get("user_id"),
            "title": "",
            "desc": item.get("content"),
            "liked_count": item.get("liked_count"),
            "collected_count": "0",
            "comment_count": item.get("comments_count"),
            "share_count": item.get("shared_count"),
            "ip_location": item.get("ip_location"),
            "tag_list": "",
            "time": item.get("create_time"),
            "platform": "weibo",
        } for item in raw_notes]
        comments = self._load_comments(
            cur,
            "weibo_note_comment",
            "note_id",
            raw_ids,
            lambda item: {
                "content": item.get("content"),
                "like_count": item.get("comment_like_count"),
                "sub_comment_count": item.get("sub_comment_count"),
                "create_time": item.get("create_time"),
                "note_id": _pid("wb", item.get("note_id")),
                "ip_location": item.get("ip_location"),
            },
        )
        creators = self._load_creators(
            cur,
            "weibo_creator",
            list({item.get("user_id") for item in raw_notes if item.get("user_id")}),
            lambda item: {
                "user_id": item["user_id"],
                "nickname": item.get("nickname"),
                "gender": item.get("gender"),
                "fans": item.get("fans"),
                "interaction": "0",
            },
        )
        return notes, comments, creators

    def _load_tieba(self, cur):
        raw_notes = self._load_posts(
            cur,
            "tieba_note",
            "note_id",
            lambda id_column, ids: _date_string_where("publish_time", self.date_range, id_column, ids),
            "tieba",
        )
        raw_ids = [item["note_id"] for item in raw_notes]
        notes = [{
            "note_id": _pid("tieba", item["note_id"]),
            "user_id": item.get("user_link") or item.get("user_nickname"),
            "title": item.get("title"),
            "desc": item.get("desc"),
            "liked_count": "0",
            "collected_count": "0",
            "comment_count": str(item.get("total_replay_num") or 0),
            "share_count": "0",
            "ip_location": item.get("ip_location"),
            "tag_list": "",
            "time": None,
            "platform": "tieba",
        } for item in raw_notes]
        comments = self._load_comments(
            cur,
            "tieba_comment",
            "note_id",
            raw_ids,
            lambda item: {
                "content": item.get("content"),
                "like_count": "0",
                "sub_comment_count": str(item.get("sub_comment_count") or 0),
                "create_time": None,
                "note_id": _pid("tieba", item.get("note_id")),
                "ip_location": item.get("ip_location"),
            },
        )
        return notes, comments, []

    def _load_zhihu(self, cur):
        if self.platform != "zhihu":
            raw_notes = []
        else:
            post_clause, post_params = _in_clause("content_id", self.post_ids)
            cur.execute(
                f"""
                SELECT *
                FROM zhihu_content
                WHERE (
                    (
                        created_time REGEXP '^[0-9]{{10}}$'
                        AND CAST(created_time AS UNSIGNED) >= %s
                        AND CAST(created_time AS UNSIGNED) < %s
                    )
                    OR (
                        created_time REGEXP '^[0-9]{{13}}$'
                        AND CAST(created_time AS UNSIGNED) >= %s
                        AND CAST(created_time AS UNSIGNED) < %s
                    )
                    OR (
                        created_time >= %s
                        AND created_time < %s
                    )
                ){post_clause}
                """,
                [
                    self.date_range.start_ts,
                    self.date_range.end_ts,
                    self.date_range.start_ts * 1000,
                    self.date_range.end_ts * 1000,
                    self.date_range.start_date,
                    self.date_range.end_exclusive_date,
                    *post_params,
                ],
            )
            raw_notes = cur.fetchall()

        raw_ids = [item["content_id"] for item in raw_notes]
        notes = [{
            "note_id": _pid("zhihu", item["content_id"]),
            "user_id": item.get("user_id"),
            "title": item.get("title"),
            "desc": item.get("content_text") or item.get("desc"),
            "liked_count": str(item.get("voteup_count") or 0),
            "collected_count": "0",
            "comment_count": str(item.get("comment_count") or 0),
            "share_count": "0",
            "ip_location": "",
            "tag_list": "",
            "time": self._zhihu_timestamp(item.get("created_time")),
            "platform": "zhihu",
        } for item in raw_notes]
        comments = self._load_comments(
            cur,
            "zhihu_comment",
            "content_id",
            raw_ids,
            lambda item: {
                "content": item.get("content"),
                "like_count": str(item.get("like_count") or 0),
                "sub_comment_count": str(item.get("sub_comment_count") or 0),
                "create_time": None,
                "note_id": _pid("zhihu", item.get("content_id")),
                "ip_location": item.get("ip_location"),
            },
        )
        creators = self._load_creators(
            cur,
            "zhihu_creator",
            list({item.get("user_id") for item in raw_notes if item.get("user_id")}),
            lambda item: {
                "user_id": item["user_id"],
                "nickname": item.get("user_nickname"),
                "gender": item.get("gender"),
                "fans": str(item.get("fans") or 0),
                "interaction": str(item.get("get_voteup_count") or 0),
            },
        )
        return notes, comments, creators

    @staticmethod
    def _zhihu_timestamp(value):
        try:
            timestamp = int(value)
            return timestamp // 1000 if timestamp >= 1_000_000_000_000 else timestamp
        except (TypeError, ValueError):
            return None


def _safe_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _positive_int_env(name, default):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _build_llm_source(notes, comments, max_posts=None, max_comments=None):
    # 统计分析仍使用全部数据；发给模型的正文长度受限，避免代理的响应超时。
    max_posts = max_posts or _positive_int_env("LLM_SOURCE_MAX_POSTS", 100)
    max_comments = max_comments or _positive_int_env("LLM_SOURCE_MAX_COMMENTS", 100)
    max_post_text = _positive_int_env("LLM_SOURCE_MAX_POST_TEXT", 350)
    max_comment_text = _positive_int_env("LLM_SOURCE_MAX_COMMENT_TEXT", 220)
    ranked_notes = sorted(
        notes,
        key=lambda item: _safe_int(item.get("liked_count")) + _safe_int(item.get("comment_count")),
        reverse=True,
    )[:max_posts]
    ranked_comments = sorted(
        comments,
        key=lambda item: _safe_int(item.get("like_count")) + _safe_int(item.get("sub_comment_count")),
        reverse=True,
    )[:max_comments]
    return {
        "posts": [{
            "id": item.get("note_id"),
            "platform": item.get("platform"),
            "title": (item.get("title") or "")[:max_post_text],
            "content": (item.get("desc") or "")[:max_post_text],
            "likes": _safe_int(item.get("liked_count")),
            "comments": _safe_int(item.get("comment_count")),
        } for item in ranked_notes],
        "comments": [{
            "post_id": item.get("note_id"),
            "content": (item.get("content") or "")[:max_comment_text],
            "likes": _safe_int(item.get("like_count")),
            "replies": _safe_int(item.get("sub_comment_count")),
        } for item in ranked_comments],
    }


def _build_report_metadata(
    date_range,
    platform,
    post_ids,
    notes,
    comments,
    creators,
    creator_count,
    topics,
    concerns,
    sentiment,
    engagement,
):
    compact_topics = [
        {
            key: item.get(key)
            for key in ("topic", "count", "percent", "matched_keywords", "top_keywords")
            if key in item
        }
        for item in topics[:10]
    ]
    compact_concerns = []
    for item in concerns[:10]:
        compact_concerns.append({
            "concern": item.get("concern"),
            "count": item.get("count", 0),
            "views": item.get("views", []),
            "subclusters": [
                {
                    key: subcluster.get(key)
                    for key in ("name", "count", "percent", "top_keywords")
                    if key in subcluster
                }
                for subcluster in item.get("subclusters", [])
            ],
        })
    compact_sentiment = {
        "distribution": sentiment.get("distribution", {}),
        "emotion_subcategories": {
            name: {"count": value.get("count", 0)}
            for name, value in sentiment.get("emotion_subcategories", {}).items()
        },
    }
    return {
        "post_publish_date": f"{date_range.start_date} 至 {date_range.end_date}",
        "platform": platform,
        "post_ids": post_ids or "全部符合日期条件的帖子",
        "note_count": len(notes),
        "comment_count": len(comments),
        "creator_count": creator_count,
        "total_likes": engagement.get("total_likes", 0),
        "topics": compact_topics,
        "concerns": compact_concerns,
        "sentiment": compact_sentiment,
        "loaded_creator_profiles": len(creators),
    }


def _build_final_llm_prompt(prompt, metadata, source_data=None, batch_summaries=None):
    if batch_summaries is None:
        evidence_section = f"""代表性帖子和关联评论（帖子按互动量、评论按点赞和回复数排序；统计结论仍基于全部已筛选数据）：
{json.dumps(source_data, ensure_ascii=False)}"""
    else:
        evidence_section = f"""全部帖子已按批次完成分析。以下是各批次的结构化摘要，每篇帖子只属于一个批次：
{json.dumps(batch_summaries, ensure_ascii=False, indent=2)}

合并要求：
- 汇总所有批次后再下结论，不要只采用前几个批次
- 相同主题、诉求和风险需要跨批次合并去重
- 数量和比例以“数据筛选条件与统计”中的全量本地统计为准
- 批次摘要中的频次仅代表对应批次，应累加后比较，不要把每批等权处理
- 少数意见应标明是少量反馈，不要夸大为普遍结论"""

    return f"""你是资深社媒数据分析师。请严格按“分析要求”生成中文报告，所有结论仅基于下面的筛选数据；数据不足时请明确说明，不要虚构。

分析要求：
{prompt}

数据筛选条件与统计：
{json.dumps(metadata, ensure_ascii=False, indent=2)}

{evidence_section}

请直接输出报告正文，不要复述任务或数据输入。"""


def _generate_batch_summaries(prompt, notes, comments, batch_size):
    ranked_notes = sorted(
        notes,
        key=lambda item: _safe_int(item.get("liked_count")) + _safe_int(item.get("comment_count")),
        reverse=True,
    )
    comments_by_post = {}
    for comment in comments:
        comments_by_post.setdefault(comment.get("note_id"), []).append(comment)

    batches = [
        ranked_notes[index:index + batch_size]
        for index in range(0, len(ranked_notes), batch_size)
    ]
    summaries = []
    summary_max_tokens = _positive_int_env("LLM_BATCH_SUMMARY_MAX_TOKENS", 700)
    max_comments = _positive_int_env("LLM_SOURCE_MAX_COMMENTS", 100)

    for batch_index, batch_notes in enumerate(batches, start=1):
        batch_comments = [
            comment
            for note in batch_notes
            for comment in comments_by_post.get(note.get("note_id"), [])
        ]
        source_data = _build_llm_source(
            batch_notes,
            batch_comments,
            max_posts=batch_size,
            max_comments=max_comments,
        )
        batch_prompt = f"""你是资深社媒数据分析师。下面是完整数据集的第 {batch_index}/{len(batches)} 批，本批包含 {len(batch_notes)} 篇帖子。

最终报告的分析要求：
{prompt}

本批帖子和关联评论：
{json.dumps(source_data, ensure_ascii=False)}

请只分析本批数据并输出紧凑的结构化摘要，供后续跨批次合并。必须包括：
1. 与分析要求相关的主要主题、诉求、风险和情感倾向
2. 每项结论在本批中的大致出现次数
3. 少数但重要的异常或负面反馈
4. 能支撑结论的简短原文证据

不要生成最终报告，不要推断其他批次，不要使用 Markdown 代码块。"""
        print(
            f"[LLM] 正在汇总第 {batch_index}/{len(batches)} 批："
            f"帖子 {len(batch_notes)} 篇，关联评论 {len(batch_comments)} 条",
            flush=True,
        )
        summary = generate_llm_report(batch_prompt, max_tokens=summary_max_tokens)
        if not summary:
            print(f"[LLM] 第 {batch_index}/{len(batches)} 批汇总失败", flush=True)
            return None
        summaries.append({
            "batch": batch_index,
            "post_count": len(batch_notes),
            "comment_count": len(batch_comments),
            "summary": summary,
        })

    return summaries


def build_custom_report(
    prompt,
    date_range,
    platform,
    post_ids,
    notes,
    comments,
    creators,
    creator_count,
    use_llm=True,
):
    analyzer = Analyzer()
    texts = [
        analyzer.clean_text((item.get("title") or "") + (item.get("desc") or ""))
        for item in notes
    ] + [
        analyzer.clean_text(item.get("content") or "")
        for item in comments
    ]
    topics = analyzer.analyze_topics(texts)
    roles = analyzer.analyze_roles(texts, "自定义筛选")
    concerns = analyzer.analyze_concerns(notes, comments)
    questions = analyzer.analyze_questions(notes, comments)
    sentiment = analyzer.analyze_sentiment(texts, SentimentAnalyzer)
    engagement = analyzer.analyze_engagement(notes)
    geography = analyzer.analyze_geography(notes, comments)
    creator_analysis = analyzer.analyze_creators(creators)
    tags = analyzer.analyze_tags(notes)
    time_trend = analyzer.analyze_time_trend(notes, comments)

    print("[LLM] 正在整理报告输入数据", flush=True)
    report = _generate_custom_llm_report(
        prompt,
        date_range,
        platform,
        post_ids,
        notes,
        comments,
        creators,
        creator_count,
        topics,
        concerns,
        sentiment,
        engagement,
    )
    if report is None:
        report = AI_FAILURE_MESSAGE

    return (
        report,
        topics,
        roles,
        concerns,
        questions,
        sentiment,
        engagement,
        geography,
        creator_analysis,
        tags,
        time_trend,
    )


def _generate_custom_llm_report(
    prompt,
    date_range,
    platform,
    post_ids,
    notes,
    comments,
    creators,
    creator_count,
    topics,
    concerns,
    sentiment,
    engagement,
):
    """使用调用方给出的 prompt 生成报告；不可用时返回 None。"""
    batch_size = _positive_int_env("LLM_REPORT_BATCH_SIZE", 100)
    metadata = _build_report_metadata(
        date_range,
        platform,
        post_ids,
        notes,
        comments,
        creators,
        creator_count,
        topics,
        concerns,
        sentiment,
        engagement,
    )
    if len(notes) <= batch_size:
        print(f"[LLM] 帖子数未超过 {batch_size}，直接生成最终报告", flush=True)
        source_data = _build_llm_source(
            notes,
            comments,
            max_posts=batch_size,
        )
        llm_prompt = _build_final_llm_prompt(
            prompt,
            metadata,
            source_data=source_data,
        )
    else:
        total_batches = (len(notes) + batch_size - 1) // batch_size
        print(
            f"[LLM] 帖子数 {len(notes)} 超过 {batch_size}，"
            f"将分为 {total_batches} 批汇总",
            flush=True,
        )
        batch_summaries = _generate_batch_summaries(
            prompt,
            notes,
            comments,
            batch_size,
        )
        if not batch_summaries:
            return None
        print("[LLM] 所有批次汇总完成，正在生成最终报告", flush=True)
        llm_prompt = _build_final_llm_prompt(
            prompt,
            metadata,
            batch_summaries=batch_summaries,
        )

    max_tokens = _positive_int_env("LLM_REPORT_MAX_TOKENS", 1200)
    return generate_llm_report(llm_prompt, max_tokens=max_tokens)


def main():
    parser = argparse.ArgumentParser(description="按自定义提示词、发布日期和帖子 ID 生成洞察报告")
    parser.add_argument(
        "--prompt",
        "--pompt",
        dest="prompt",
        required=True,
        help="报告分析要求（必传；--pompt 为兼容拼写）",
    )
    parser.add_argument(
        "--keyword",
        default="",
        help="报告归属的来源关键词；传入后可在管理后台按该关键词查看报告",
    )
    parser.add_argument("--report-name", required=True, help="报告名称，全局唯一；同名报告将被覆盖")
    parser.add_argument("--start-date", required=True, help="帖子发布日期开始日期，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="帖子发布日期结束日期，格式 YYYY-MM-DD，包含当天")
    parser.add_argument(
        "--platform",
        required=True,
        choices=PLATFORMS,
        help="数据平台：xhs、bili、dy、ks、wb、tieba 或 zhihu",
    )
    parser.add_argument(
        "--post-ids",
        nargs="*",
        default=[],
        help="可选的当前平台帖子 ID 集合，支持空格或逗号分隔；未传时使用全部符合日期条件的帖子",
    )
    parser.add_argument("--llm", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    prompt = args.prompt.strip()
    if not prompt:
        parser.error("--prompt 不能为空")
    report_name = args.report_name.strip()
    if not report_name:
        parser.error("--report-name 不能为空")
    if len(report_name) > 100:
        parser.error("--report-name 不能超过100个字符")
    try:
        date_range = parse_date_range(args.start_date, args.end_date)
    except ValueError as exc:
        parser.error(str(exc))

    post_ids = parse_post_ids(args.post_ids)
    print(f"[筛选] 帖子发布日期：{date_range.start_date} 至 {date_range.end_date}")
    print(f"[筛选] 平台：{args.platform}")
    print(f"[筛选] 帖子 ID：{len(post_ids)} 个" if post_ids else "[筛选] 帖子 ID：全部")
    print("[生成] 使用大模型")

    try:
        print("[数据] 正在查询帖子和评论数据", flush=True)
        notes, comments, creators, creator_count = FilteredPostRepository(
            date_range,
            args.platform,
            post_ids,
        ).load_data()
    except Exception as exc:
        print(f"[错误] 查询数据库失败：{exc}")
        sys.exit(1)

    if not notes:
        print("[错误] 未找到符合筛选条件的帖子，未生成报告")
        sys.exit(1)

    print(
        f"[数据] 帖子 {len(notes)} 篇 | 关联评论 {len(comments)} 条 | "
        f"创作者 {creator_count} 位",
        flush=True,
    )
    (
        report,
        topics,
        roles,
        concerns,
        questions,
        sentiment,
        engagement,
        geography,
        creator_analysis,
        tags,
        time_trend,
    ) = build_custom_report(
        prompt,
        date_range,
        args.platform,
        post_ids,
        notes,
        comments,
        creators,
        creator_count,
        use_llm=True,
    )

    if report == AI_FAILURE_MESSAGE:
        print("[错误] AI 报告生成失败，未保存失败占位内容", file=sys.stderr, flush=True)
        sys.exit(2)

    CustomReportRepository().save(
        report_name=report_name,
        platform=args.platform,
        source_keyword=args.keyword.strip(),
        start_date=date_range.start_date,
        end_date=date_range.end_date,
        post_ids=",".join(post_ids),
        prompt=prompt,
        report_content=report,
    )
    print(f"[完成] 报告已保存：{report_name}", flush=True)
    print("\n" + report, flush=True)


if __name__ == "__main__":
    main()
