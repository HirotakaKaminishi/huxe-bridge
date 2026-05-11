"""tests for huxe_bridge.atomic_io."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from huxe_bridge.atomic_io import atomic_write_text


def test_atomic_write_creates_and_overwrites(tmp_path: Path):
    target = tmp_path / "out.txt"
    atomic_write_text(target, "first")
    atomic_write_text(target, "second 日本語")
    assert target.read_text(encoding="utf-8") == "second 日本語"
    # tmp ファイルが残っていない
    leftovers = [p for p in tmp_path.iterdir() if p.name != "out.txt"]
    assert leftovers == []


def test_atomic_write_preserves_target_when_replace_fails(tmp_path: Path):
    """os.replace が失敗しても元 target が破壊されず tmp も後始末される。"""
    target = tmp_path / "out.txt"
    target.write_text("original", encoding="utf-8")

    with patch("huxe_bridge.atomic_io.os.replace", side_effect=OSError("boom")):
        with pytest.raises(OSError, match="boom"):
            atomic_write_text(target, "should not land")

    assert target.read_text(encoding="utf-8") == "original"
    leftovers = [p for p in tmp_path.iterdir() if p.name != "out.txt"]
    assert leftovers == []


def test_atomic_write_tmp_in_same_dir(tmp_path: Path):
    """tmp は target と同一ディレクトリに作る (cross-fs rename 回避)。"""
    target = tmp_path / "sub" / "out.txt"
    target.parent.mkdir()
    captured: dict[str, Path] = {}

    def spy(src, dst):
        captured["src"] = Path(src)
        captured["dst"] = Path(dst)
        import os as _os
        _os.rename(src, dst)

    with patch("huxe_bridge.atomic_io.os.replace", side_effect=spy):
        atomic_write_text(target, "x")

    assert captured["src"].parent == captured["dst"].parent == target.parent
