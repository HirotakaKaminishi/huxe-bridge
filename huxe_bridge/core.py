"""
huxe-bridge core operations
===========================
MCPサーバとCLIから共通利用する操作ロジック。
ファイルI/Oに閉じた純粋関数群。
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "categories.yaml"
CONTENT = ROOT / "content"


def _load() -> dict:
    with CONFIG.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _save(cfg: dict) -> None:
    with CONFIG.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


def _valid_id(cid: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]*", cid))


def list_categories() -> list[dict[str, Any]]:
    cfg = _load()
    out = []
    for c in cfg["categories"]:
        cdir = CONTENT / c["id"]
        count = len(list(cdir.glob("*.md"))) if cdir.exists() else 0
        out.append({**c, "article_count": count})
    return out


def add_category(
    id: str,
    name: str,
    description: str = "",
    tags: list[str] | None = None,
    active: bool = True,
) -> dict[str, Any]:
    if not _valid_id(id):
        raise ValueError(f"invalid id: {id!r}")
    cfg = _load()
    if any(c["id"] == id for c in cfg["categories"]):
        raise ValueError(f"category already exists: {id}")
    new = {
        "id": id,
        "name": name,
        "description": description,
        "active": active,
        "tags": tags or [],
    }
    cfg["categories"].append(new)
    _save(cfg)
    (CONTENT / id).mkdir(parents=True, exist_ok=True)
    return {"added": new}


def remove_category(id: str, delete_files: bool = False) -> dict[str, Any]:
    cfg = _load()
    before = len(cfg["categories"])
    cfg["categories"] = [c for c in cfg["categories"] if c["id"] != id]
    if len(cfg["categories"]) == before:
        raise ValueError(f"category not found: {id}")
    _save(cfg)
    removed_files = False
    cdir = CONTENT / id
    if delete_files and cdir.exists():
        shutil.rmtree(cdir)
        removed_files = True
    return {"removed_id": id, "deleted_files": removed_files}


def toggle_category(id: str, active: bool) -> dict[str, Any]:
    cfg = _load()
    for c in cfg["categories"]:
        if c["id"] == id:
            c["active"] = active
            _save(cfg)
            return {"id": id, "active": active}
    raise ValueError(f"category not found: {id}")


def list_summaries(category_id: str) -> list[dict[str, Any]]:
    cdir = CONTENT / category_id
    if not cdir.exists():
        return []
    items = []
    for p in sorted(cdir.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        first = text.splitlines()[0] if text.strip() else ""
        title = first.lstrip("#").strip() if first.startswith("#") else p.stem
        items.append({
            "slug": p.stem,
            "title": title,
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            "size_bytes": p.stat().st_size,
        })
    return items


def add_summary(
    category_id: str,
    title: str,
    body_markdown: str,
    slug: str | None = None,
) -> dict[str, Any]:
    cfg = _load()
    if not any(c["id"] == category_id for c in cfg["categories"]):
        raise ValueError(f"category not found: {category_id}")
    cdir = CONTENT / category_id
    cdir.mkdir(parents=True, exist_ok=True)
    if slug is None:
        safe = re.sub(r"[^a-zA-Z0-9-]+", "-", title).strip("-").lower()[:40] or "untitled"
        slug = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{safe}"
    path = cdir / f"{slug}.md"
    if path.exists():
        raise ValueError(f"already exists: {path.name}")
    content = f"# {title}\n\n{body_markdown}\n"
    path.write_text(content, encoding="utf-8")
    return {"category_id": category_id, "slug": slug, "path": str(path)}


def remove_summary(category_id: str, slug: str) -> dict[str, Any]:
    path = CONTENT / category_id / f"{slug}.md"
    if not path.exists():
        raise ValueError(f"not found: {path}")
    path.unlink()
    return {"removed": str(path)}


def get_feed_urls(include_huxe: bool = False) -> dict[str, Any]:
    """huxe登録用 RSS URL 一覧。

    ``include_huxe=True`` の時は各 feed entry に Show metadata 3 フィールド
    (``show_title`` / ``show_description`` / ``custom_instructions``) を含める。
    metadata 未設定カテゴリでは ``None`` を入れる。デフォルト ``False`` で
    既存呼び出し側に対し後方互換。
    """
    cfg = _load()
    base = cfg["site"]["base_url"].rstrip("/")
    feeds = []
    for c in cfg["categories"]:
        if not c.get("active", True):
            continue
        entry: dict[str, Any] = {
            "category_id": c["id"],
            "name": c["name"],
            "rss_url": f"{base}/{c['id']}.xml",
        }
        if include_huxe:
            huxe = c.get("huxe") or {}
            entry["show_title"] = huxe.get("show_title")
            entry["show_description"] = huxe.get("show_description")
            entry["custom_instructions"] = huxe.get("custom_instructions")
        feeds.append(entry)
    return {"all_feed": f"{base}/all.xml", "feeds": feeds}
