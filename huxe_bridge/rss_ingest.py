"""
huxe-bridge RSS ingest core
============================
公式RSSをポーリングして content/<cat>/<slug>.md として転載する。
要約はしない (huxe Live Station 側で要約される)。
de-dup は content/<cat>/.ingest-index.json の guid 辞書で行う。
bootstrap: 初回 index 不在時は最新 1 件のみ取り込み、残りは index に
処理済み扱いで記録。事故防止のため。bootstrap_fetch=N 明示時のみ N 件取得。
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import feedparser
import requests

from huxe_bridge.core import CONFIG, CONTENT
from huxe_bridge.frontmatter import write_frontmatter
from huxe_bridge.sources import list_sources

log = logging.getLogger("huxe_bridge.rss_ingest")

USER_AGENT = "huxe-bridge/0.1 (+https://hirotakakaminishi.github.io/huxe-bridge)"
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_DESC_BYTES = 64 * 1024
JST = ZoneInfo("Asia/Tokyo")
INDEX_FILENAME = ".ingest-index.json"


@dataclass(frozen=True)
class FeedItem:
    guid: str
    link: str
    title: str
    description_html: str
    published_at: datetime  # tz-aware (UTC)


@dataclass
class IngestResult:
    category_id: str
    fetched: int = 0
    added: int = 0
    skipped_dup: int = 0
    skipped_quota: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _fetch_with_retry(url: str, *, ua: str = USER_AGENT, timeout: float = DEFAULT_TIMEOUT, max_tries: int = 3) -> bytes:
    """1s, 4s backoff で最大 3 試行。403/404 は retry しない (bot block 永久化を回避)。"""
    backoff = [0.0, 1.0, 4.0]
    last_err: Exception | None = None
    headers = {"User-Agent": ua, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"}
    for attempt in range(max_tries):
        if backoff[attempt] > 0:
            time.sleep(backoff[attempt])
        try:
            res = requests.get(url, headers=headers, timeout=timeout)
            if res.status_code in (403, 404):
                raise requests.HTTPError(f"{res.status_code} for {url}")
            res.raise_for_status()
            return res.content
        except requests.HTTPError as e:
            if "403" in str(e) or "404" in str(e):
                raise
            last_err = e
        except requests.RequestException as e:
            last_err = e
    raise RuntimeError(f"fetch failed after {max_tries} tries: {url}: {last_err}")


def _extract_pubdate(entry: Any) -> datetime:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return datetime.now(timezone.utc)


def _parse_feed(content: bytes) -> list[FeedItem]:
    parsed = feedparser.parse(content)
    items: list[FeedItem] = []
    for entry in parsed.entries:
        link = entry.get("link", "")
        guid = entry.get("id") or entry.get("guid") or link
        if not guid:
            continue
        title = html.unescape(entry.get("title", "")).strip()
        desc_raw = (
            entry.get("description")
            or entry.get("summary")
            or (entry.get("content", [{}])[0].get("value") if entry.get("content") else None)
            or ""
        )
        description = html.unescape(desc_raw)
        if len(description.encode("utf-8")) > DEFAULT_MAX_DESC_BYTES:
            truncated = description.encode("utf-8")[:DEFAULT_MAX_DESC_BYTES].decode("utf-8", errors="ignore")
            description = truncated + "\n\n…[truncated]"
        items.append(FeedItem(guid=guid, link=link, title=title, description_html=description, published_at=_extract_pubdate(entry)))
    return items


def fetch_feed(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> list[FeedItem]:
    """1 source を fetch して FeedItem の list を返す。"""
    raw = _fetch_with_retry(url, timeout=timeout)
    return _parse_feed(raw)


def _index_path(category_id: str):
    return CONTENT / category_id / INDEX_FILENAME


def _load_index(category_id: str) -> dict[str, Any]:
    path = _index_path(category_id)
    if not path.exists():
        return {"version": 1, "updated_at": None, "items": {}}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("items", {})
    return data


def _save_index(category_id: str, idx: dict[str, Any]) -> None:
    cdir = CONTENT / category_id
    cdir.mkdir(parents=True, exist_ok=True)
    idx["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _index_path(category_id).open("w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2, sort_keys=True)


def _guid_key(guid: str) -> str:
    return hashlib.sha1(guid.encode("utf-8")).hexdigest()


def _make_slug(item: FeedItem) -> str:
    """YYYY-MM-DD-<sha1(guid)[:10]> (日付は JST)."""
    return f"{item.published_at.astimezone(JST).strftime('%Y-%m-%d')}-{_guid_key(item.guid)[:10]}"


def _render_md(item: FeedItem, *, source_url: str) -> str:
    meta = {
        "source": "rss",
        "source_guid": item.guid,
        "source_url": source_url,
        "source_link": item.link,
        "published_at": item.published_at.astimezone(timezone.utc).isoformat(),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "title": item.title,
    }
    body = f"# {item.title}\n\n{item.description_html}\n\n[元記事を読む]({item.link})\n"
    return write_frontmatter(meta, body)


def ingest_category(category_id: str, *, dry_run: bool = False, bootstrap_fetch: int | None = None) -> IngestResult:
    """カテゴリ単位 ingest。ソース単位 try/except で 1 ソース失敗が他を巻き込まない。"""
    result = IngestResult(category_id=category_id)
    sources = [s for s in list_sources(category_id) if s.get("enabled", True)]
    if not sources:
        return result

    idx = _load_index(category_id)
    is_bootstrap = not _index_path(category_id).exists() or not idx.get("items")
    cdir = CONTENT / category_id

    for src in sources:
        url = src["url"]
        per_run_limit = int(src.get("max_items_per_run", 5))
        try:
            items = fetch_feed(url)
        except Exception as e:  # noqa: BLE001 - 単一ソース失敗を他へ波及させない
            msg = f"{url}: {type(e).__name__}: {e}"
            log.warning("fetch error: %s", msg)
            result.errors.append(msg)
            continue
        result.fetched += len(items)

        # 新しい順にソート (published_at desc)
        items_sorted = sorted(items, key=lambda x: x.published_at, reverse=True)

        # bootstrap 時の処理対象決定
        if is_bootstrap:
            take_n = bootstrap_fetch if bootstrap_fetch is not None else 1
            to_fetch = items_sorted[:take_n]
            to_mark = items_sorted[take_n:]
        else:
            to_fetch = items_sorted
            to_mark = []

        added_for_source = 0
        for item in to_fetch:
            key = _guid_key(item.guid)
            if key in idx["items"]:
                result.skipped_dup += 1
                continue
            if added_for_source >= per_run_limit:
                result.skipped_quota += 1
                continue
            slug = _make_slug(item)
            md_path = cdir / f"{slug}.md"
            if not dry_run:
                cdir.mkdir(parents=True, exist_ok=True)
                md_path.write_text(_render_md(item, source_url=url), encoding="utf-8")
            idx["items"][key] = {"slug": slug, "guid": item.guid, "url": url}
            result.added += 1
            added_for_source += 1

        # bootstrap で残った古いものは「処理済み」扱いで index にだけ詰める
        for item in to_mark:
            key = _guid_key(item.guid)
            if key not in idx["items"]:
                idx["items"][key] = {
                    "slug": None,
                    "guid": item.guid,
                    "url": url,
                    "bootstrap_skipped": True,
                }

    if not dry_run:
        _save_index(category_id, idx)
    return result


def ingest_all(*, dry_run: bool = False, bootstrap_fetch: int | None = None) -> dict[str, IngestResult]:
    """全カテゴリ ingest。category 単位の失敗は他へ波及させない。"""
    import yaml

    with CONFIG.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    out: dict[str, IngestResult] = {}
    for c in cfg.get("categories", []):
        if not c.get("active", True):
            continue
        cat_id = c["id"]
        try:
            out[cat_id] = ingest_category(cat_id, dry_run=dry_run, bootstrap_fetch=bootstrap_fetch)
        except Exception as e:  # noqa: BLE001
            r = IngestResult(category_id=cat_id)
            r.errors.append(f"category-level: {type(e).__name__}: {e}")
            out[cat_id] = r
    return out


def rebuild_index(category_id: str) -> dict[str, Any]:
    """md ファイルの frontmatter を読み直して .ingest-index.json を再構築。"""
    from huxe_bridge.frontmatter import read_frontmatter

    cdir = CONTENT / category_id
    items: dict[str, Any] = {}
    if cdir.exists():
        for md_path in cdir.glob("*.md"):
            raw = md_path.read_text(encoding="utf-8")
            meta, _ = read_frontmatter(raw)
            guid = meta.get("source_guid")
            url = meta.get("source_url", "")
            if not guid:
                continue
            items[_guid_key(str(guid))] = {
                "slug": md_path.stem,
                "guid": guid,
                "url": url,
            }
    idx = {"version": 1, "updated_at": None, "items": items}
    _save_index(category_id, idx)
    return {"category_id": category_id, "items": len(items)}
