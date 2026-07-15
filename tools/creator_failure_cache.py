from __future__ import annotations

"""Persistent skip lists for creator IDs that failed to fetch."""

import json
from pathlib import Path
from typing import Iterable, TypeVar


CACHE_DIR = Path("cache") / "creator_failures"
T = TypeVar("T")


def _path(platform: str) -> Path:
    return CACHE_DIR / f"{platform}_creator_failures.json"


def _load(platform: str) -> set[str]:
    try:
        data = json.loads(_path(platform).read_text(encoding="utf-8"))
        return {str(item) for item in data} if isinstance(data, list) else set()
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()


def get_failed_creator_ids(platform: str) -> set[str]:
    """Return IDs manually marked as failed for a platform."""
    return _load(platform)


def filter_failed_creator_ids(platform: str, creator_ids: Iterable[T]) -> list[T]:
    failed_ids = get_failed_creator_ids(platform)
    return [creator_id for creator_id in creator_ids if str(creator_id) not in failed_ids]


def record_creator_failure(platform: str, creator_id: str | int) -> None:
    failed_ids = _load(platform)
    if str(creator_id) in failed_ids:
        return
    failed_ids.add(str(creator_id))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _path(platform)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(sorted(failed_ids), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(path)