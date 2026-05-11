"""
huxe-bridge CLI
===============
MCPサーバが立たない環境(CI、デバッグ、初期セットアップ)向けのCLI。
MCPサーバと同じcore操作を直接叩く。

usage:
  huxe-bridge cats                              # カテゴリ一覧
  huxe-bridge add-cat <id> <name> [-d desc]     # カテゴリ追加
  huxe-bridge rm-cat <id> [--delete-files]      # カテゴリ削除
  huxe-bridge toggle <id> on|off                # active切替
  huxe-bridge summaries <category_id>           # 要約一覧
  huxe-bridge add <category_id> "<title>" -f file.md
  huxe-bridge feeds                             # huxe登録用URL
  huxe-bridge build                             # ローカルビルド
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from huxe_bridge import core


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="huxe-bridge")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("cats", help="list categories")

    s = sub.add_parser("add-cat", help="add category")
    s.add_argument("id")
    s.add_argument("name")
    s.add_argument("-d", "--description", default="")
    s.add_argument("-t", "--tags", nargs="*", default=[])

    s = sub.add_parser("rm-cat", help="remove category")
    s.add_argument("id")
    s.add_argument("--delete-files", action="store_true")

    s = sub.add_parser("toggle", help="enable/disable category")
    s.add_argument("id")
    s.add_argument("state", choices=["on", "off"])

    s = sub.add_parser("summaries", help="list summaries in category")
    s.add_argument("category_id")

    s = sub.add_parser("add", help="add summary")
    s.add_argument("category_id")
    s.add_argument("title")
    s.add_argument("-f", "--file", help="read body from file (default: stdin)")
    s.add_argument("--slug")

    s = sub.add_parser("rm", help="remove summary")
    s.add_argument("category_id")
    s.add_argument("slug")

    sub.add_parser("feeds", help="show huxe RSS URLs")
    sub.add_parser("build", help="build dist/")

    args = p.parse_args(argv)

    if args.cmd == "cats":
        _print(core.list_categories())
    elif args.cmd == "add-cat":
        _print(core.add_category(args.id, args.name, args.description, args.tags))
    elif args.cmd == "rm-cat":
        _print(core.remove_category(args.id, args.delete_files))
    elif args.cmd == "toggle":
        _print(core.toggle_category(args.id, args.state == "on"))
    elif args.cmd == "summaries":
        _print(core.list_summaries(args.category_id))
    elif args.cmd == "add":
        body = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
        _print(core.add_summary(args.category_id, args.title, body, args.slug))
    elif args.cmd == "rm":
        _print(core.remove_summary(args.category_id, args.slug))
    elif args.cmd == "feeds":
        _print(core.get_feed_urls())
    elif args.cmd == "build":
        root = Path(__file__).resolve().parent.parent
        r = subprocess.run(
            [sys.executable, str(root / "scripts" / "build.py")],
            cwd=str(root),
        )
        return r.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
