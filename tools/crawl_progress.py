"""Keyword-level progress events exchanged between batch parent and crawler child."""

import json
import os
from typing import Optional


PROGRESS_ENV = "CRAWL_PROGRESS_STDOUT"
PROGRESS_PREFIX = "__CRAWL_KEYWORD_PROGRESS__="


def emit_keyword_completed(platform: str, keyword: str) -> None:
    """Emit a machine-readable completion event when batch progress is enabled."""
    if os.environ.get(PROGRESS_ENV) != "1":
        return

    event = {
        "event": "keyword_completed",
        "platform": platform,
        "keyword": keyword,
    }
    print(
        f"{PROGRESS_PREFIX}{json.dumps(event, ensure_ascii=False, separators=(',', ':'))}",
        flush=True,
    )


def parse_keyword_completed_event(line: str) -> Optional[dict[str, str]]:
    """Return a validated completion event, or None for normal crawler output."""
    if not line.startswith(PROGRESS_PREFIX):
        return None

    try:
        event = json.loads(line[len(PROGRESS_PREFIX):])
    except json.JSONDecodeError:
        return None

    if (
        event.get("event") != "keyword_completed"
        or not isinstance(event.get("platform"), str)
        or not isinstance(event.get("keyword"), str)
    ):
        return None
    return event
