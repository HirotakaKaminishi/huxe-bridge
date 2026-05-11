"""
huxe-bridge MCP server
======================
Claude Code / Claude Desktop から呼べるMCPサーバ。
実体は huxe_bridge.core の関数を MCP tool として公開しているだけ。
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from huxe_bridge import core

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
def get_feed_urls() -> dict[str, Any]:
    """huxe登録用RSS URL(activeのみ)。"""
    return core.get_feed_urls()


@mcp.tool()
def build() -> dict[str, Any]:
    """ローカルでビルドを実行。出力は dist/ に入る。"""
    res = subprocess.run(
        ["python", str(BUILD_SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return {"returncode": res.returncode, "stdout": res.stdout, "stderr": res.stderr}


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
