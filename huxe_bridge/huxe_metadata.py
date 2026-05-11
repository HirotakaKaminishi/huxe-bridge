"""
huxe-bridge huxe metadata
=========================
huxe Live Station Show の 4 点セット (feed_url + show_title +
show_description + custom_instructions) を ``config/categories.yaml`` の
各カテゴリ下 ``huxe:`` ブロックとして永続化する。
既存 13 ツール の signature を一切触らずに 2 ツール追加するため別モジュール。
"""
from __future__ import annotations

from typing import Any

import yaml

from huxe_bridge.atomic_io import atomic_write_text
from huxe_bridge.core import CONFIG


def _load() -> dict:
    with CONFIG.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _save(cfg: dict) -> None:
    atomic_write_text(CONFIG, yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))


def _find_category(cfg: dict, category_id: str) -> dict:
    for c in cfg.get("categories", []):
        if c["id"] == category_id:
            return c
    raise ValueError(f"category not found: {category_id}")


def get_metadata(category_id: str) -> dict[str, Any] | None:
    """``huxe:`` ブロックを返す。未設定なら ``None`` (例外は category 不在のみ)。"""
    cat = _find_category(_load(), category_id)
    huxe = cat.get("huxe")
    return dict(huxe) if isinstance(huxe, dict) else None


def set_metadata(
    category_id: str,
    show_title: str | None = None,
    show_description: str | None = None,
    custom_instructions: str | None = None,
) -> dict[str, Any]:
    """部分更新。``None`` は既存値を維持する。書き込みは atomic_io 経由。"""
    cfg = _load()
    cat = _find_category(cfg, category_id)
    huxe = dict(cat.get("huxe") or {})
    for k, v in (
        ("show_title", show_title),
        ("show_description", show_description),
        ("custom_instructions", custom_instructions),
    ):
        if v is not None:
            huxe[k] = v
    cat["huxe"] = huxe
    _save(cfg)
    return {"category_id": category_id, "huxe": huxe}


def build_setup(category_id: str, base_url: str) -> dict[str, Any]:
    """huxe 登録用 4 点セット。metadata 未設定 3 フィールドは ``None``。"""
    cat = _find_category(_load(), category_id)
    huxe = cat.get("huxe") or {}
    return {
        "category_id": category_id,
        "feed_url": f"{base_url.rstrip('/')}/{category_id}.xml",
        "show_title": huxe.get("show_title"),
        "show_description": huxe.get("show_description"),
        "custom_instructions": huxe.get("custom_instructions"),
    }
