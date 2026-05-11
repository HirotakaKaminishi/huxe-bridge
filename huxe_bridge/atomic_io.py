"""
huxe-bridge atomic file I/O helpers
===================================
途中で kill されても target ファイルが truncated にならないよう
``tmp + os.replace`` パターンで書き込む。

POSIX の ``rename(2)`` は同一ファイルシステム内で atomic なので、
tmp ファイルは必ず target と同じディレクトリに作成する。
"""
from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """``path`` に ``content`` を atomic に書き込む。

    同一ディレクトリに ``<name>.tmp.<pid>`` を作成し、書き込み完了後
    ``os.replace`` で target を差し替える。書き込み中に例外が出た場合は
    tmp ファイルを後始末する (target は触らない)。
    """
    path = Path(path)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(content, encoding=encoding)
        os.replace(tmp, path)
    except Exception:
        # 書き込み途中で失敗したら tmp を消す。target はそのまま (壊さない)。
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
