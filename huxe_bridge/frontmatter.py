"""
huxe-bridge frontmatter utility
================================
md ファイルの YAML frontmatter (``---`` で挟むブロック) を読み書きする。

- frontmatter なしの旧 md と完全後方互換 (meta は空 dict、body は全文)
- CRLF / LF どちらでも正しく扱う
- 不正な YAML は ``ValueError`` で fail-fast (silent ignore しない)
"""
from __future__ import annotations

from typing import Any

import yaml

_DELIM = "---"


def read_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """frontmatter を抜き出して ``(meta, body)`` を返す。

    frontmatter が無い場合は ``({}, text)`` を返す。
    body の先頭の余計な改行は剥がさない (titleの直前空行も含めて呼び出し側で扱う)。
    """
    if not text:
        return {}, text
    # 行頭の BOM だけ取り除き、改行種別は LF に揃える
    normalized = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != _DELIM:
        return {}, text
    # closing delimiter を探す
    for i in range(1, len(lines)):
        if lines[i].strip() == _DELIM:
            yaml_block = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :])
            # body 先頭の単発改行は取り除く (frontmatter と本文の境界の空行 1 個)
            if body.startswith("\n"):
                body = body[1:]
            try:
                meta = yaml.safe_load(yaml_block) or {}
            except yaml.YAMLError as e:
                raise ValueError(f"invalid yaml frontmatter: {e}") from e
            if not isinstance(meta, dict):
                raise ValueError(
                    f"frontmatter must be a yaml mapping, got {type(meta).__name__}"
                )
            return meta, body
    # 閉じ ``---`` が無い場合は frontmatter として扱わない (素の md とみなす)
    return {}, text


def write_frontmatter(meta: dict[str, Any], body: str) -> str:
    """``meta`` を YAML frontmatter として ``body`` の前に貼って 1 つの文字列にする。

    ``meta`` が空 dict の場合は frontmatter を出力せず body のみ返す。
    """
    if not meta:
        return body
    yaml_block = yaml.safe_dump(
        meta,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).rstrip("\n")
    return f"{_DELIM}\n{yaml_block}\n{_DELIM}\n{body}"
