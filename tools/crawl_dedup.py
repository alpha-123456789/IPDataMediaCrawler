# -*- coding: utf-8 -*-
"""
Shared deduplication utility for skipping already-crawled notes/posts.

Any content row already stored in the database is skipped.

Only works with DB-backed stores (db/sqlite/postgres); file-based stores
always return all IDs unchanged.
"""

from typing import List, Optional, Tuple, Type

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

# Registry: platform -> (ContentModel, content_id_column, CommentModel,
#                        comment_note_fk_column, stored_comment_count_column)
_PLATFORM_REGISTRY: dict[str, Tuple[Type, Column, Type, Column, Optional[Column]]] = {
    "xhs": (XhsNote, XhsNote.note_id, XhsNoteComment, XhsNoteComment.note_id, XhsNote.comment_count),
    "dy": (DouyinAweme, DouyinAweme.aweme_id, DouyinAwemeComment, DouyinAwemeComment.aweme_id, DouyinAweme.comment_count),
    "ks": (KuaishouVideo, KuaishouVideo.video_id, KuaishouVideoComment, KuaishouVideoComment.video_id, None),
    "wb": (WeiboNote, WeiboNote.note_id, WeiboNoteComment, WeiboNoteComment.note_id, WeiboNote.comments_count),
    "bili": (BilibiliVideo, BilibiliVideo.video_id, BilibiliVideoComment, BilibiliVideoComment.video_id, BilibiliVideo.video_comment),
}


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

    Skip rule: any existing content record is skipped before detail, update,
    media, and comment requests.

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

    content_model, content_id_col, _, _, _ = registry_entry
    typed_ids = _cast_ids(note_ids, content_id_col)
    if not typed_ids:
        return []

    try:
        async with get_session() as session:
            content_stmt = select(content_id_col).where(
                content_id_col.in_(typed_ids),
            )
            content_result = await session.execute(content_stmt)
            existing_content_ids = {str(row[0]) for row in content_result.all()}
            uncrawled = [
                note_id for note_id in note_ids
                if str(note_id) not in existing_content_ids
            ]

            skipped_count = len(existing_content_ids)
            if skipped_count > 0:
                utils.logger.info(
                    f"[crawl_dedup] Platform '{platform}': skipping {skipped_count} already-crawled notes, "
                    f"{len(uncrawled)} remaining"
                )
            return uncrawled

    except Exception as e:
        utils.logger.warning(f"[crawl_dedup] Dedup check failed ({e}), proceeding with all IDs")
        return note_ids


async def filter_note_ids_for_comment_crawl(
    platform: str,
    note_ids: List[str],
) -> List[str]:
    """Return IDs that should enter the comment crawl queue.

    Only newly discovered notes fetch comments. Existing content is never
    refreshed through the comment queue.
    """
    if not note_ids:
        return []

    if config.SAVE_DATA_OPTION not in ("db", "sqlite", "postgres"):
        return note_ids

    registry_entry = _PLATFORM_REGISTRY.get(platform)
    if not registry_entry:
        utils.logger.warning(
            f"[crawl_dedup] Unknown platform '{platform}', skipping comment queue filtering"
        )
        return note_ids

    _, content_id_col, _, _, _ = registry_entry
    typed_ids = _cast_ids(note_ids, content_id_col)
    if not typed_ids:
        return []

    try:
        async with get_session() as session:
            content_stmt = select(content_id_col).where(
                content_id_col.in_(typed_ids),
            )
            content_result = await session.execute(content_stmt)
            existing_content_ids = {str(row[0]) for row in content_result.all()}
            filtered_ids = [
                note_id for note_id in note_ids
                if str(note_id) not in existing_content_ids
            ]

            if existing_content_ids:
                utils.logger.info(
                    f"[crawl_dedup] Platform '{platform}': skipping comments for "
                    f"{len(existing_content_ids)} existing notes"
                )
            return filtered_ids

    except Exception as e:
        utils.logger.warning(
            f"[crawl_dedup] Comment queue filter failed ({e}), proceeding with all IDs"
        )
        return note_ids


def _has_positive_comment_count(comment_count: object) -> bool:
    """Return whether a persisted comment count is a positive integer."""
    try:
        return int(str(comment_count).strip()) > 0
    except (TypeError, ValueError):
        return False


async def filter_note_ids_needing_comment_recovery(
    platform: str,
    note_ids: List[str],
) -> List[str]:
    """Return existing posts whose comments need a one-time recovery crawl.

    A post qualifies only when its persisted comment count is positive and
    there are no associated rows in the platform's comment table. It is
    intentionally separate from content deduplication so no detail, media, or
    post update request is made for the recovered post.
    """
    if not note_ids or config.SAVE_DATA_OPTION not in ("db", "sqlite", "postgres"):
        return []

    registry_entry = _PLATFORM_REGISTRY.get(platform)
    if not registry_entry:
        utils.logger.warning(
            f"[crawl_dedup] Unknown platform '{platform}', skipping comment recovery"
        )
        return []

    _, content_id_col, _, comment_note_fk_col, comment_count_col = registry_entry
    if comment_count_col is None:
        return []

    typed_ids = _cast_ids(note_ids, content_id_col)
    if not typed_ids:
        return []

    try:
        async with get_session() as session:
            content_stmt = select(content_id_col, comment_count_col).where(
                content_id_col.in_(typed_ids),
            )
            content_result = await session.execute(content_stmt)
            existing_ids_with_comments = {
                str(row[0])
                for row in content_result.all()
                if _has_positive_comment_count(row[1])
            }
            if not existing_ids_with_comments:
                return []

            comment_stmt = select(comment_note_fk_col).where(
                comment_note_fk_col.in_(
                    _cast_ids(list(existing_ids_with_comments), comment_note_fk_col)
                )
            ).distinct()
            comment_result = await session.execute(comment_stmt)
            ids_with_saved_comments = {str(row[0]) for row in comment_result.all()}
            recovery_ids = [
                note_id
                for note_id in note_ids
                if str(note_id) in existing_ids_with_comments
                and str(note_id) not in ids_with_saved_comments
            ]
            if recovery_ids:
                utils.logger.info(
                    f"[crawl_dedup] Platform '{platform}': recovering comments for "
                    f"{len(recovery_ids)} existing notes with missing comment rows"
                )
            return recovery_ids
    except Exception as e:
        utils.logger.warning(
            f"[crawl_dedup] Comment recovery check failed ({e}), skipping recovery"
        )
        return []
