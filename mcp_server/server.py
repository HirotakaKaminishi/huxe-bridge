"""
huxe-bridge MCP server
======================
Claude Code / Claude Desktop から呼べるMCPサーバ。
実体は huxe_bridge.core / sources の関数を MCP tool として公開している (13 ツール)。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from huxe_bridge import core, huxe_metadata, sources as sources_mod

ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = ROOT / "scripts" / "build.py"

mcp = FastMCP("huxe-bridge")


@mcp.tool()
def list_categories() -> list[dict[str, Any]]:
    """全カテゴリを返す。activeフラグと記事数を含む。"""
    return core.list_categories()


@mcp.tool()
def add_category(
    id: str,
    name: str,
    description: str = "",
    tags: list[str] | None = None,
    active: bool = True,
) -> dict[str, Any]:
    """カテゴリ追加。idは ^[a-z0-9][a-z0-9-]*$ のみ。"""
    return core.add_category(id, name, description, tags, active)


@mcp.tool()
def remove_category(id: str, delete_files: bool = False) -> dict[str, Any]:
    """カテゴリ削除。delete_files=True で content/<id> も物理削除。"""
    return core.remove_category(id, delete_files)


@mcp.tool()
def toggle_category(id: str, active: bool) -> dict[str, Any]:
    """active切替(物理削除せずビルド対象から外す)。"""
    return core.toggle_category(id, active)


@mcp.tool()
def list_summaries(category_id: str) -> list[dict[str, Any]]:
    """カテゴリ内の要約一覧。"""
    return core.list_summaries(category_id)


@mcp.tool()
def add_summary(
    category_id: str,
    title: str,
    body_markdown: str,
    slug: str | None = None,
) -> dict[str, Any]:
    """要約Markdown追加。slug省略時は日時+タイトルから自動生成。"""
    return core.add_summary(category_id, title, body_markdown, slug)


@mcp.tool()
def remove_summary(category_id: str, slug: str) -> dict[str, Any]:
    """要約削除。"""
    return core.remove_summary(category_id, slug)


@mcp.tool()
def get_feed_urls(include_huxe: bool = False) -> dict[str, Any]:
    """huxe登録用RSS URL(activeのみ)。include_huxe=Trueで各エントリにshow metadataを含める。"""
    return core.get_feed_urls(include_huxe=include_huxe)


@mcp.tool()
def build() -> dict[str, Any]:
    """ローカルでビルドを実行。出力は dist/ に入る。"""
    res = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return {"returncode": res.returncode, "stdout": res.stdout, "stderr": res.stderr}


@mcp.tool()
def list_sources(category_id: str | None = None) -> list[dict[str, Any]]:
    """カテゴリ別 RSS ソース一覧。category_id 省略時は全カテゴリ。"""
    return sources_mod.list_sources(category_id)


@mcp.tool()
def add_source(
    category_id: str,
    rss_url: str,
    max_items_per_run: int = 5,
    enabled: bool = True,
) -> dict[str, Any]:
    """カテゴリに RSS ソースを追加。max_items_per_run はソース単位の per-run 上限。"""
    return sources_mod.add_source(category_id, rss_url, max_items_per_run, enabled)


@mcp.tool()
def remove_source(category_id: str, rss_url: str) -> dict[str, Any]:
    """カテゴリから RSS ソースを削除。"""
    return sources_mod.remove_source(category_id, rss_url)


@mcp.tool()
def set_huxe_metadata(
    category_id: str,
    show_title: str | None = None,
    show_description: str | None = None,
    custom_instructions: str | None = None,
) -> dict[str, Any]:
    """huxe Live Station Show の metadata を部分更新。None は既存値を維持。"""
    return huxe_metadata.set_metadata(
        category_id,
        show_title=show_title,
        show_description=show_description,
        custom_instructions=custom_instructions,
    )


@mcp.tool()
def get_huxe_setup(category_id: str) -> dict[str, Any]:
    """huxe 登録用 4 点セット (feed_url + title + description + custom_instructions) を返す。"""
    cfg = core._load()
    base = cfg["site"]["base_url"]
    return huxe_metadata.build_setup(category_id, base)


@mcp.tool()
def git_publish(message: str = "update via mcp") -> dict[str, Any]:
    """git add -A && commit && push。GitHub Actionsがビルド・デプロイする。"""
    def run(args: list[str]) -> dict[str, Any]:
        r = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True)
        return {"rc": r.returncode, "out": r.stdout, "err": r.stderr}
    return {
        "add": run(["git", "add", "-A"]),
        "commit": run(["git", "commit", "-m", message]),
        "push": run(["git", "push"]),
    }


if __name__ == "__main__":
    mcp.run()
