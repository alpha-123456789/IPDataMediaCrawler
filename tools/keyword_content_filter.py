"""Match keywords against post text before saving content on any platform."""

from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Iterator, Optional

import config
from tools import utils
from var import source_keyword_var


_TEXT_FIELDS = {
    "title", "display_title", "preview_title", "item_title", "page_title",
    "desc", "description", "caption", "summary", "intro", "introduction",
    "text", "text_raw", "raw_text", "content", "content_text",
    "longTextContent", "full_text", "long_desc", "dynamic", "part",
    "excerpt", "short_title", "video_description", "video_desc",
}
_CONTENT_FIELDS = {
    "View", "photo", "mblog", "note_card", "aweme_info", "video",
    "page_info", "longText", "long_text", "retweeted_status",
    "desc_v2", "pages", "rich_text_note",
}
_TAG_FIELDS = {
    "tag_list": ("name",),
    "tags": ("name", "tag_name"),
    "Tags": ("tag_name",),
    "text_extra": ("hashtag_name",),
    "cha_list": ("cha_name",),
    "topics": ("name", "title"),
}


class _PostTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data):
        if not self.hidden_depth:
            self.parts.append(data)


def _plain_text(text: str) -> str:
    parser = _PostTextParser()
    parser.feed(text)
    parser.close()
    return "".join(parser.parts)


def _iter_post_text(content) -> Iterator[str]:
    if hasattr(content, "model_dump"):
        content = content.model_dump()
    if isinstance(content, str):
        yield _plain_text(content)
    elif isinstance(content, (list, tuple)):
        for item in content:
            yield from _iter_post_text(item)
    elif isinstance(content, Mapping):
        for field, value in content.items():
            if field in _TEXT_FIELDS or field in _CONTENT_FIELDS:
                yield from _iter_post_text(value)
            elif field in _TAG_FIELDS:
                tags = value if isinstance(value, (list, tuple)) else [value]
                for tag in tags:
                    if isinstance(tag, str):
                        yield _plain_text(tag)
                    elif isinstance(tag, Mapping):
                        for name in _TAG_FIELDS[field]:
                            if isinstance(tag.get(name), str):
                                yield _plain_text(tag[name])


def content_matches_keyword(content, keyword: Optional[str] = None) -> bool:
    """Require a match in one post field, excluding author and request metadata."""
    if keyword is None:
        if config.CRAWLER_TYPE == "search":
            keyword = source_keyword_var.get()
        if not keyword:
            keyword = config.KEYWORDS
    keywords = [value.strip() for value in keyword.split(",") if value.strip()]
    if any(
        word in text
        for text in _iter_post_text(content)
        for word in keywords
    ):
        return True
    utils.logger.info(
        "[keyword_content_filter] Skip content without keyword in post text: %s",
        keyword,
    )
    return False
