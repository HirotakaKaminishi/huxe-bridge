"""
huxe-bridge build script
========================
content/<category>/*.md を読み取って、dist/ 配下に以下を出力する:

  dist/
    index.html              全カテゴリのフィード一覧
    all.xml                 全カテゴリ統合RSS
    <category>.xml          カテゴリ別RSS
    <category>/<slug>.html  記事HTML

外部依存は markdown と pyyaml のみ。RSSは標準ライブラリで生成する。
"""
from __future__ import annotations

import html
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import markdown
import yaml

# huxe_bridge は editable install されている前提。scripts/ は package として
# 登録済みなので兄弟パッケージ import が可能。
from huxe_bridge.frontmatter import read_frontmatter

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "categories.yaml"
CONTENT = ROOT / "content"
DIST = ROOT / "dist"


@dataclass
class Article:
    category_id: str
    slug: str
    title: str
    body_html: str
    mtime: datetime


# ---------- config / loading ----------

def load_config() -> dict:
    if not CONFIG.exists():
        raise SystemExit(f"config not found: {CONFIG}")
    with CONFIG.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if "categories" not in cfg:
        raise SystemExit("config: 'categories' key is required")
    seen = set()
    for c in cfg["categories"]:
        cid = c.get("id", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", cid):
            raise SystemExit(f"invalid category id: {cid!r}")
        if cid in seen:
            raise SystemExit(f"duplicate category id: {cid}")
        seen.add(cid)
    return cfg


def slugify(stem: str) -> str:
    return re.sub(r"\s+", "-", stem.strip())


def load_articles(category_id: str) -> list[Article]:
    cdir = CONTENT / category_id
    if not cdir.exists():
        return []
    items: list[Article] = []
    for md_path in sorted(cdir.glob("*.md")):
        raw = md_path.read_text(encoding="utf-8")
        meta, text = read_frontmatter(raw)
        first = text.splitlines()[0] if text.strip() else ""
        if meta.get("title"):
            title = str(meta["title"])
            body_md = text.lstrip("\n")
            # frontmatter の title と body 1 行目の見出しが同一なら見出しを 1 回剥がす
            if first.startswith("#") and first.lstrip("#").strip() == title:
                body_md = "\n".join(text.splitlines()[1:]).lstrip("\n")
        elif first.startswith("#"):
            title = first.lstrip("#").strip()
            body_md = "\n".join(text.splitlines()[1:]).lstrip("\n")
        else:
            title = md_path.stem
            body_md = text
        body_html = markdown.markdown(
            body_md, extensions=["fenced_code", "tables"]
        )
        # frontmatter に published_at があれば優先 (RSS 取り込み記事用)
        if meta.get("published_at"):
            try:
                mtime = datetime.fromisoformat(str(meta["published_at"]))
                if mtime.tzinfo is None:
                    mtime = mtime.replace(tzinfo=timezone.utc)
            except ValueError:
                mtime = datetime.fromtimestamp(md_path.stat().st_mtime, tz=timezone.utc)
        else:
            mtime = datetime.fromtimestamp(md_path.stat().st_mtime, tz=timezone.utc)
        items.append(
            Article(
                category_id=category_id,
                slug=slugify(md_path.stem),
                title=title,
                body_html=body_html,
                mtime=mtime,
            )
        )
    items.sort(key=lambda a: a.mtime, reverse=True)
    return items


# ---------- RSS generation (stdlib only) ----------

def rss_xml(
    *,
    title: str,
    link: str,
    self_link: str,
    description: str,
    language: str,
    items: list[tuple[Article, str]],  # (article, display_title)
    base: str,
) -> str:
    """RSS 2.0 を依存なしで生成。"""
    now = datetime.now(timezone.utc)
    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '<channel>',
        f'<title>{xml_escape(title)}</title>',
        f'<link>{xml_escape(link)}</link>',
        f'<description>{xml_escape(description)}</description>',
        f'<language>{xml_escape(language)}</language>',
        f'<lastBuildDate>{format_datetime(now)}</lastBuildDate>',
        f'<atom:link href="{xml_escape(self_link)}" rel="self" type="application/rss+xml" />',
    ]
    for article, display_title in items:
        url = f"{base}/{article.category_id}/{article.slug}.html"
        parts.extend(
            [
                "<item>",
                f"<title>{xml_escape(display_title)}</title>",
                f"<link>{xml_escape(url)}</link>",
                f'<guid isPermaLink="true">{xml_escape(url)}</guid>',
                f"<pubDate>{format_datetime(article.mtime)}</pubDate>",
                f"<category>{xml_escape(article.category_id)}</category>",
                f"<description><![CDATA[{article.body_html}]]></description>",
                "</item>",
            ]
        )
    parts.extend(["</channel>", "</rss>"])
    return "\n".join(parts)


# ---------- HTML rendering ----------

def render_article_html(site: dict, category: dict, article: Article) -> str:
    base = site["base_url"].rstrip("/")
    return f"""<!doctype html>
<html lang="{html.escape(site.get('language', 'ja'))}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(article.title)} - {html.escape(category['name'])}</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 720px;
         margin: 2em auto; padding: 0 1em; line-height: 1.7; color: #222; }}
  h1, h2, h3 {{ line-height: 1.3; }}
  code {{ background: #f4f4f4; padding: 0.1em 0.3em; border-radius: 3px;
          font-size: 0.92em; }}
  pre code {{ display: block; padding: 1em; overflow-x: auto; }}
  nav a {{ color: #06c; text-decoration: none; }}
  nav a:hover {{ text-decoration: underline; }}
  small {{ color: #666; }}
</style>
</head>
<body>
<nav><a href="{base}/">← all feeds</a></nav>
<article>
<h1>{html.escape(article.title)}</h1>
<p><small>{html.escape(category['name'])} / {article.mtime.strftime('%Y-%m-%d %H:%M UTC')}</small></p>
{article.body_html}
</article>
</body>
</html>
"""


def render_index_html(site: dict, active_categories: list[dict]) -> str:
    base = site["base_url"].rstrip("/")
    rows = []
    for c in active_categories:
        rows.append(
            "<li>"
            f"<strong>{html.escape(c['name'])}</strong><br>"
            f"<small>{html.escape(c.get('description', ''))}</small><br>"
            f'<a href="{base}/{c["id"]}.xml">RSS</a> '
            f'<code>{base}/{c["id"]}.xml</code>'
            "</li>"
        )
    rows_html = "\n".join(rows) or "<li><em>(no active categories)</em></li>"
    return f"""<!doctype html>
<html lang="{html.escape(site.get('language', 'ja'))}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(site['title'])}</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 720px;
         margin: 2em auto; padding: 0 1em; line-height: 1.7; }}
  li {{ margin-bottom: 1.2em; }}
  code {{ background: #f4f4f4; padding: 0.1em 0.3em; border-radius: 3px;
          font-size: 0.85em; word-break: break-all; }}
</style>
</head>
<body>
<h1>{html.escape(site['title'])}</h1>
<p>{html.escape(site.get('description', ''))}</p>
<h2>カテゴリ別フィード</h2>
<p>下記URLをhuxeのLive Stationに「RSS feed」として登録してください。</p>
<ul>
{rows_html}
</ul>
<h2>統合フィード</h2>
<p><a href="{base}/all.xml">{base}/all.xml</a> — 全カテゴリをまとめて受信したい場合。</p>
</body>
</html>
"""


# ---------- main ----------

def main() -> int:
    cfg = load_config()
    site = cfg["site"]
    base = site["base_url"].rstrip("/")
    categories = cfg["categories"]

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    active = [c for c in categories if c.get("active", True)]
    all_items: list[tuple[Article, str]] = []

    for cat in active:
        cid = cat["id"]
        articles = load_articles(cid)
        cat_dir = DIST / cid
        cat_dir.mkdir(exist_ok=True)
        for a in articles:
            (cat_dir / f"{a.slug}.html").write_text(
                render_article_html(site, cat, a), encoding="utf-8"
            )
            all_items.append((a, f"[{cat['name']}] {a.title}"))
        xml_doc = rss_xml(
            title=f"{site['title']} - {cat['name']}",
            link=f"{base}/",
            self_link=f"{base}/{cid}.xml",
            description=cat.get("description", ""),
            language=site.get("language", "ja"),
            items=[(a, a.title) for a in articles],
            base=base,
        )
        (DIST / f"{cid}.xml").write_text(xml_doc, encoding="utf-8")
        print(f"[built] {cid}: {len(articles)} article(s)")

    all_items.sort(key=lambda x: x[0].mtime, reverse=True)
    all_xml = rss_xml(
        title=site["title"],
        link=f"{base}/",
        self_link=f"{base}/all.xml",
        description=site.get("description", ""),
        language=site.get("language", "ja"),
        items=all_items,
        base=base,
    )
    (DIST / "all.xml").write_text(all_xml, encoding="utf-8")

    (DIST / "index.html").write_text(
        render_index_html(site, active), encoding="utf-8"
    )
    (DIST / ".nojekyll").write_text("", encoding="utf-8")

    print(f"[done] total {len(all_items)} article(s) in {len(active)} category(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
