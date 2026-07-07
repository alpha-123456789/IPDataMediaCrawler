# -*- coding: utf-8 -*-
"""
Shared deduplication utility for skipping already-crawled notes/posts.

Simple rule: if the ID exists in BOTH content table and comment table,
AND the content record's add_ts is within the current month → skip.

Only works with DB-backed stores (db/sqlite/postgres); file-based stores
always return all IDs unchanged.
"""

import time
from typing import List, Tuple, Type

from sqlalchemy import BigInteger, Column, String, select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from database.db_session import get_session
from database.models import (
    BilibiliVideo,
    BilibiliVideoComment,
    DouyinAweme,
    DouyinAwemeComment,
    KuaishouVideo,
    KuaishouVideoComment,
    WeiboNote,
    WeiboNoteComment,
    XhsNote,
    XhsNoteComment,
)
from tools import utils

# Registry: platform -> (ContentModel, content_id_column, CommentModel, comment_note_fk_column)
_PLATFORM_REGISTRY: dict[str, Tuple[Type, Column, Type, Column]] = {
    "xhs": (XhsNote, XhsNote.note_id, XhsNoteComment, XhsNoteComment.note_id),
    "dy": (DouyinAweme, DouyinAweme.aweme_id, DouyinAwemeComment, DouyinAwemeComment.aweme_id),
    "ks": (KuaishouVideo, KuaishouVideo.video_id, KuaishouVideoComment, KuaishouVideoComment.video_id),
    "wb": (WeiboNote, WeiboNote.note_id, WeiboNoteComment, WeiboNoteComment.note_id),
    "bili": (BilibiliVideo, BilibiliVideo.video_id, BilibiliVideoComment, BilibiliVideoComment.video_id),
}


def _get_current_month_start_ts() -> int:
    """Return timestamp (milliseconds) for the 1st day of current month at 00:00:00."""
    now = time.localtime()
    first_day_sec = time.mktime((now.tm_year, now.tm_mon, 1, 0, 0, 0, 0, 0, -1))
    return int(first_day_sec * 1000)


def _cast_ids(ids: List[str], column: Column) -> list:
    """Cast string IDs to the column's expected type."""
    if isinstance(column.type, BigInteger):
        result = []
        for id_val in ids:
            try:
                result.append(int(id_val))
            except (ValueError, TypeError):
                continue
        return result
    # String columns — keep as-is
    return [str(id_val) for id_val in ids]


async def filter_uncrawled_note_ids(
    platform: str,
    note_ids: List[str],
) -> List[str]:
    """Return only note_ids that still need crawling.

    Skip rule: ID exists in content table AND comment table,
    AND content add_ts >= current month start → already crawled, skip.

    For non-DB stores (csv/json/jsonl/excel), returns all IDs unchanged.
    """
    if not note_ids:
        return []

    if config.SAVE_DATA_OPTION not in ("db", "sqlite", "postgres"):
        return note_ids

    registry_entry = _PLATFORM_REGISTRY.get(platform)
    if not registry_entry:
        utils.logger.warning(f"[crawl_dedup] Unknown platform '{platform}', skipping dedup")
        return note_ids

    content_model, content_id_col, comment_model, comment_note_fk_col = registry_entry
    typed_ids = _cast_ids(note_ids, content_id_col)
    if not typed_ids:
        return []

    try:
        month_start_ts = _get_current_month_start_ts()

        async with get_session() as session:
            # Step 1: Find IDs that exist in content table with add_ts in current month
            content_stmt = select(content_id_col, content_model.add_ts).where(
                content_id_col.in_(typed_ids),
            )
            content_result = await session.execute(content_stmt)
            content_rows = content_result.all()

            # Use str for all comparisons to avoid int/str mismatch
            recent_content_ids = set(
                str(row[0]) for row in content_rows if row[1] and row[1] >= month_start_ts
            )

            if not recent_content_ids:
                return list(note_ids)

            # Step 2: Among those, find which also have comments
            recent_list = list(recent_content_ids)
            comment_stmt = select(comment_note_fk_col).where(
                comment_note_fk_col.in_(recent_list)
            ).distinct()
            comment_result = await session.execute(comment_stmt)
            ids_with_comments = set(str(row[0]) for row in comment_result.all())

            # Only skip IDs that are in BOTH tables this month
            skipped_ids = recent_content_ids & ids_with_comments

            # Compare as strings against original note_ids
            skipped_set = skipped_ids
            uncrawled = [nid for nid in note_ids if str(nid) not in skipped_set]

            skipped_count = len(skipped_ids)
            if skipped_count > 0:
                utils.logger.info(
                    f"[crawl_dedup] Platform '{platform}': skipping {skipped_count} already-crawled notes (current month), "
                    f"{len(uncrawled)} remaining"
                )
            return uncrawled

    except Exception as e:
        utils.logger.warning(f"[crawl_dedup] Dedup check failed ({e}), proceeding with all IDs")
        return note_ids
