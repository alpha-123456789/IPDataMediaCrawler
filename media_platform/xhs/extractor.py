# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/xhs/extractor.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

import json
import re
from typing import Dict, Optional

import humps


_INITIAL_STATE_MARKER = "window.__INITIAL_STATE__"
_JS_IDENTIFIER_CHARS = frozenset("_$")
_NON_JSON_LITERALS = ("undefined", "NaN", "Infinity")
_JS_SET_CONSTRUCTOR = re.compile(r"new\s+Set\s*\(")


def _is_identifier_char(char: str) -> bool:
    return char.isalnum() or char in _JS_IDENTIFIER_CHARS


def _extract_call_argument(source: str, open_paren_index: int) -> Optional[tuple[str, int]]:
    """Return a JavaScript call argument and the index after its closing parenthesis."""
    depth = 1
    quote = ""
    escaped = False

    for index in range(open_paren_index + 1, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue

        if char in {'"', "'"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return source[open_paren_index + 1:index], index + 1

    return None


def _extract_initial_state_source(html: str) -> Optional[str]:
    """Extract the first complete object assigned to window.__INITIAL_STATE__."""
    marker_index = html.find(_INITIAL_STATE_MARKER)
    if marker_index < 0:
        return None

    start = marker_index + len(_INITIAL_STATE_MARKER)
    while start < len(html) and html[start].isspace():
        start += 1
    if start >= len(html) or html[start] != "=":
        return None
    start += 1
    while start < len(html) and html[start].isspace():
        start += 1
    if start >= len(html) or html[start] not in "{[":
        return None

    closing_brackets = {"{": "}", "[": "]"}
    stack = [closing_brackets[html[start]]]
    quote = ""
    escaped = False

    for index in range(start + 1, len(html)):
        char = html[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue

        if char in {'"', "'"}:
            quote = char
        elif char in closing_brackets:
            stack.append(closing_brackets[char])
        elif char in "}]":
            if not stack or char != stack[-1]:
                return None
            stack.pop()
            if not stack:
                return html[start:index + 1]

    return None


def _replace_non_json_literals(source: str) -> str:
    """Replace JavaScript-only value literals without touching quoted strings."""
    result = []
    index = 0
    quote = ""
    escaped = False

    while index < len(source):
        char = source[index]
        if quote:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            index += 1
            continue

        if char == '"':
            quote = char
            result.append(char)
            index += 1
            continue

        set_match = _JS_SET_CONSTRUCTOR.match(source, index)
        previous = source[index - 1] if index > 0 else ""
        if set_match and (not previous or not _is_identifier_char(previous)):
            call = _extract_call_argument(source, set_match.end() - 1)
            if call is not None:
                argument, call_end = call
                result.append(_replace_non_json_literals(argument) if argument.strip() else "[]")
                index = call_end
                continue

        matched_literal = None
        if source.startswith("-Infinity", index):
            matched_literal = "-Infinity"
        else:
            for literal in _NON_JSON_LITERALS:
                if source.startswith(literal, index):
                    matched_literal = literal
                    break

        if matched_literal:
            literal_end = index + len(matched_literal)
            previous = source[index - 1] if index > 0 else ""
            following = source[literal_end] if literal_end < len(source) else ""
            if (
                (not previous or not _is_identifier_char(previous))
                and (not following or not _is_identifier_char(following))
            ):
                result.append("null")
                index = literal_end
                continue

        result.append(char)
        index += 1

    return "".join(result)


def _extract_initial_state(html: str) -> Optional[Dict]:
    source = _extract_initial_state_source(html)
    if source is None:
        return None
    return json.loads(_replace_non_json_literals(source), strict=False)


class XiaoHongShuExtractor:
    def __init__(self):
        pass

    def extract_note_detail_from_html(self, note_id: str, html: str) -> Optional[Dict]:
        """Extract note details from HTML

        Args:
            html (str): HTML string

        Returns:
            Dict: Note details dictionary
        """
        if "noteDetailMap" not in html:
            # Either a CAPTCHA appeared or the note doesn't exist
            return None

        state = _extract_initial_state(html)
        if state:
            note_dict = humps.decamelize(state)
            return note_dict["note"]["note_detail_map"][note_id]["note"]
        return None

    def extract_creator_info_from_html(self, html: str) -> Optional[Dict]:
        """Extract user information from HTML

        Args:
            html (str): HTML string

        Returns:
            Dict: User information dictionary
        """
        info = _extract_initial_state(html)
        if not isinstance(info, dict):
            return None
        user = info.get("user")
        if not isinstance(user, dict):
            return None
        return user.get("userPageData")
