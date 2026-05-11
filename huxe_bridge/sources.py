"""
huxe-bridge sources CRUD
========================
``config/categories.yaml`` の各カテゴリに紐付く RSS source の登録/削除/一覧。

core.py の関数群と同列の薄い CRUD 層。yaml の構造は次の通り:

    categories:
      - id: anime-music
        ...
        sources:                # 新規キー、無くてもエラーにしない
          - url: https://lisani.jp/feed/
            max_items_per_run: 5
            enabled: true

URL は正規化 (scheme 小文字化のみ) して比較する。trailing slash は
意味ある区別 (たまにある) なので残す。
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

from huxe_bridge.atomic_io import atomic_write_text
from huxe_bridge.core import CONFIG


def _load() -> dict:
    with CONFIG.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _save(cfg: dict) -> None:
    payload = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)
    atomic_write_text(CONFIG, payload)


def _normalize_url(url: str) -> str:
    """scheme/host を lowercase。path / query は触らない。"""
    parts = urlsplit(url.strip())
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, parts.fragment)
    )


def _find_category(cfg: dict, category_id: str) -> dict:
    for c in cfg.get("categories", []):
        if c["id"] == category_id:
            return c
    raise ValueError(f"category not found: {category_id}")


def list_sources(category_id: str | None = None) -> list[dict[str, Any]]:
    """カテゴリ別 source 一覧。``category_id=None`` で全カテゴリを舐めて返す。

    返り値の各 dict には ``category_id`` キーを必ず付ける (CLI/MCP で識別用)。
    """
    cfg = _load()
    out: list[dict[str, Any]] = []
    for c in cfg.get("categories", []):
        if category_id is not None and c["id"] != category_id:
            continue
        for s in c.get("sources") or []:
            out.append({"category_id": c["id"], **s})
    if category_id is not None and not any(
        c["id"] == category_id for c in cfg.get("categories", [])
    ):
        raise ValueError(f"category not found: {category_id}")
    return out


def add_source(
    category_id: str,
    rss_url: str,
    max_items_per_run: int = 5,
    enabled: bool = True,
) -> dict[str, Any]:
    """カテゴリに RSS source を追加。

    URL 正規化後に既存と重複したら ``ValueError``。
    ``max_items_per_run`` は **そのソース単位** の per-run 上限。
    """
    if max_items_per_run < 1:
        raise ValueError(f"max_items_per_run must be >= 1, got {max_items_per_run}")
    normalized = _normalize_url(rss_url)
    cfg = _load()
    cat = _find_category(cfg, category_id)
    sources = cat.setdefault("sources", [])
    if not isinstance(sources, list):
        raise ValueError(
            f"category {category_id}: 'sources' must be a list, got {type(sources).__name__}"
        )
    for s in sources:
        if _normalize_url(s.get("url", "")) == normalized:
            raise ValueError(f"source already exists: {normalized}")
    new = {
        "url": normalized,
        "max_items_per_run": max_items_per_run,
        "enabled": enabled,
    }
    sources.append(new)
    _save(cfg)
    return {"category_id": category_id, "added": new}


def remove_source(category_id: str, rss_url: str) -> dict[str, Any]:
    """``category_id`` から URL 一致の source を 1 件削除。"""
    normalized = _normalize_url(rss_url)
    cfg = _load()
    cat = _find_category(cfg, category_id)
    sources = cat.get("sources") or []
    before = len(sources)
    cat["sources"] = [
        s for s in sources if _normalize_url(s.get("url", "")) != normalized
    ]
    if len(cat["sources"]) == before:
        raise ValueError(f"source not found: {normalized}")
    _save(cfg)
    return {"category_id": category_id, "removed_url": normalized}
