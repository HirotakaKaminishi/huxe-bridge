"""tests for huxe_bridge.frontmatter"""
from __future__ import annotations

import pytest

from huxe_bridge.frontmatter import read_frontmatter, write_frontmatter


def test_no_frontmatter_returns_empty_meta_and_original_body():
    text = "# title\n\nbody line\n"
    meta, body = read_frontmatter(text)
    assert meta == {}
    assert body == text


def test_reads_simple_frontmatter():
    src = "---\ntitle: hello\nsource: rss\n---\n# hello\n\nbody\n"
    meta, body = read_frontmatter(src)
    assert meta == {"title": "hello", "source": "rss"}
    assert body == "# hello\n\nbody\n"


def test_empty_body_after_frontmatter():
    src = "---\ntitle: only\n---\n"
    meta, body = read_frontmatter(src)
    assert meta == {"title": "only"}
    assert body == ""


def test_crlf_line_endings_handled():
    src = "---\r\ntitle: win\r\n---\r\nbody\r\n"
    meta, body = read_frontmatter(src)
    assert meta == {"title": "win"}
    assert "body" in body


def test_missing_closing_delimiter_is_treated_as_plain_md():
    src = "---\ntitle: broken\n\nno closing\n"
    meta, body = read_frontmatter(src)
    assert meta == {}
    assert body == src


def test_invalid_yaml_raises():
    src = "---\ntitle: : broken: : :\n  - bad\nlist: [unterminated\n---\nbody\n"
    with pytest.raises(ValueError):
        read_frontmatter(src)


def test_non_mapping_frontmatter_raises():
    src = "---\n- one\n- two\n---\nbody\n"
    with pytest.raises(ValueError):
        read_frontmatter(src)


def test_empty_string_input():
    meta, body = read_frontmatter("")
    assert meta == {}
    assert body == ""


def test_roundtrip_write_then_read():
    meta = {"title": "テスト", "source": "rss", "tags": ["a", "b"]}
    body = "# テスト\n\n本文\n"
    out = write_frontmatter(meta, body)
    meta2, body2 = read_frontmatter(out)
    assert meta2 == meta
    assert body2 == body


def test_write_with_empty_meta_returns_body_only():
    assert write_frontmatter({}, "hello\n") == "hello\n"


def test_html_entities_in_frontmatter_preserved():
    meta = {"title": "A & B"}
    body = "x\n"
    out = write_frontmatter(meta, body)
    meta2, _ = read_frontmatter(out)
    assert meta2["title"] == "A & B"
