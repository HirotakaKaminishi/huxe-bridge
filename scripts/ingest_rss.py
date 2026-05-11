"""
huxe-bridge ingest_rss.py
==========================
公式RSSを取り込んで content/<cat>/<slug>.md に書き出す CLI。

usage:
  python scripts/ingest_rss.py [--dry-run] [--category <id>]
                               [--bootstrap-fetch N] [--strict]
                               [--rebuild-index]
"""
from __future__ import annotations

import argparse
import sys

from huxe_bridge import rss_ingest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="huxe-bridge-ingest", description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="fetch のみ、md/index は書かない")
    p.add_argument("--category", help="特定カテゴリのみ ingest")
    p.add_argument("--bootstrap-fetch", type=int, default=None, metavar="N",
                   help="初回 ingest 時に最新 N 件まで取得 (default: 1)")
    p.add_argument("--strict", action="store_true", help="1 ソースでも失敗があれば exit 1")
    p.add_argument("--rebuild-index", action="store_true",
                   help="既存 md から .ingest-index.json を再構築して終了")
    args = p.parse_args(argv)

    if args.rebuild_index:
        if not args.category:
            print("ERROR: --rebuild-index requires --category", file=sys.stderr)
            return 2
        res = rss_ingest.rebuild_index(args.category)
        print(f"[rebuild] {res['category_id']}: {res['items']} item(s)")
        return 0

    has_error = False
    if args.category:
        r = rss_ingest.ingest_category(
            args.category, dry_run=args.dry_run, bootstrap_fetch=args.bootstrap_fetch
        )
        results = {args.category: r}
    else:
        results = rss_ingest.ingest_all(
            dry_run=args.dry_run, bootstrap_fetch=args.bootstrap_fetch
        )

    for cat_id, r in results.items():
        print(
            f"[{cat_id}] fetched={r.fetched} added={r.added} "
            f"skipped_dup={r.skipped_dup} skipped_quota={r.skipped_quota} "
            f"errors={len(r.errors)}"
        )
        for err in r.errors:
            print(f"  ERROR: {err}", file=sys.stderr)
            has_error = True

    if args.strict and has_error:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
