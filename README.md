# huxe-bridge

NotebookLMで作成した要約Markdownを、huxeのLive StationにRSS経由で取り込むためのパーソナルパイプライン。すべて**無料**(GitHub Free + Pages + Actions)で完結する。

## アーキテクチャ

```
[NotebookLM] → 要約Markdown
                  ↓
            content/<category>/*.md
                  ↓ git push
            GitHub Actions (build.py)
                  ↓
            GitHub Pages
                  ↓ RSS取得
            huxe Live Station
```

huxeのLive Stationが受け付けるソース形式は URL / テキスト / X / RSS / subreddit のみで、Google Drive直結は不可。本リポジトリは**RSS**を一級市民として扱う。

## セットアップ

### 1. リポジトリを用意

```bash
gh repo create huxe-bridge --public --source=. --remote=origin --push
```

(Privateにしたい場合はCloudflare Pagesを使う。後述。)

### 2. `config/categories.yaml` を編集

`site.base_url` を自分のPages URLに書き換える。例:

```yaml
site:
  base_url: "https://kaminishi.github.io/huxe-bridge"
```

### 3. GitHub Pagesを有効化

リポジトリの `Settings → Pages → Source` を **GitHub Actions** に設定。

### 4. 初回push

```bash
git add -A && git commit -m "init" && git push
```

数十秒後、`https://<user>.github.io/huxe-bridge/` で `index.html` が見えるようになる。ここに各カテゴリのRSS URLが列挙される。

### 5. huxeのLive Stationに登録

huxeアプリで Live Station を作成 → ソース追加 → **RSS feed** → `https://<user>.github.io/huxe-bridge/<category>.xml` を入力。

## 日常運用

### A. 手で要約を追加する場合

```bash
# 1. NotebookLMで要約を作って Markdownでコピー
# 2. ファイルとして保存
cat > content/aws-infra/2026-05-11-glacier-migration.md <<'EOF'
# Glacier Vault から S3 Glacier への移行ベストプラクティス

## 背景
...
EOF

# 3. push
git add -A && git commit -m "add: glacier migration summary" && git push
```

### B. Claude Code経由(MCPサーバ)で操作する場合

1. ローカルでMCPサーバを起動できるようにする:

   ```bash
   pip install -e .
   ```

2. Claude Code の `~/.config/claude-code/mcp.json` (またはClaude Desktopの設定) に追加:

   ```json
   {
     "mcpServers": {
       "huxe-bridge": {
         "command": "python",
         "args": ["-m", "mcp_server.server"],
         "cwd": "/absolute/path/to/huxe-bridge"
       }
     }
   }
   ```

3. Claude Code を再起動。以後、自然言語で:

   - 「huxe-bridgeにmachine-learningカテゴリを追加して」
   - 「この要約をaws-infraに入れて」
   - 「フィードのURL教えて」
   - 「公開して」

   等が動く。`skills/huxe-bridge/SKILL.md` がClaude Codeに読み込まれていれば、操作手順は自律的に判断される。

### C. ローカルで確認したい場合

```bash
python scripts/build.py
python -m http.server -d dist 8000
# → http://localhost:8000 で確認
```

## MCPサーバが公開するツール一覧 (13ツール)

| ツール | 用途 |
|---|---|
| `list_categories` | カテゴリ一覧 + 記事数 |
| `add_category` | カテゴリ追加 |
| `remove_category` | カテゴリ削除(`delete_files`オプションあり) |
| `toggle_category` | active切り替え |
| `list_summaries` | カテゴリ内の要約一覧 |
| `add_summary` | 要約Markdown追加 |
| `remove_summary` | 要約削除 |
| `get_feed_urls` | huxe登録用URL一覧 |
| `build` | ローカルビルド実行 |
| `list_sources` | カテゴリ別RSSソース一覧 |
| `add_source` | RSSソース追加 |
| `remove_source` | RSSソース削除 |
| `git_publish` | add+commit+push |

## 公式RSSの日次自動取り込み

要約は手動投入の他に、**公式RSSを毎日 JST 03:00 (UTC 18:00) に自動取り込み**する仕組みがある。
要約は huxe Live Station 側で行うため、本ブリッジは公式RSSの `title` + `link` + `pubDate` + `<description>` をそのまま転載する単なるリレー役。

### 仕組み

1. `.github/workflows/daily-ingest.yml` が `cron: '0 18 * * *'` (UTC) で起動
2. `scripts/ingest_rss.py` が `config/categories.yaml` の `sources:` を舐めて公式RSSを fetch
3. `content/<cat>/.ingest-index.json` の guid 辞書で de-dup
4. 新着 item を `content/<cat>/YYYY-MM-DD-<hash>.md` として書き出し
5. `git commit && git push` → 既存 `build.yml` が `content/**` push を検知して Pages を再デプロイ

### 初回ingestの安全装置

初回 (index 不在時) は **最新 1 件のみ取り込む**。大量バックフィルの事故防止。
明示的にバックフィルしたい時は GitHub Actions の workflow_dispatch から `bootstrap_fetch=N` を渡す。

### 初期登録ソース

- **aws-infra**: AWS What's New (公式)
- **anime-music**: lisani.jp / animeanime.jp / SPICE (eplus)
- **fido-auth**: FIDO Alliance / Chrome Developer Blog

ソースの追加/削除は MCP ツール (`add_source` / `remove_source` / `list_sources`) か CLI (`huxe-bridge add-source` 等) で行える。

### 運用 tips

- 1 ソース失敗 (404/timeout) は他ソースを巻き込まず、`IngestResult.errors` にログとして残る
- 取り込み記事は frontmatter (`source: rss`, `source_guid: ...`, `published_at: ...`) を持つ
- 重複検出は `source_guid` (RSS `<guid>` or `<link>`) ベース。md ファイル直接編集も可、`huxe-bridge ingest --rebuild-index` で index 再構築できる
- 半年に 1 回ソース URL の生存確認を推奨 (404 化、403 化があり得る)

## カテゴリ追加・削除のセマンティクス

- **追加** : `categories.yaml` に追記され、`content/<id>/` ディレクトリが作られる
- **一時停止** : `active: false` にするだけ。物理ファイルは残る。`build`の対象外になる
- **完全削除** : `categories.yaml` から削除。`delete_files=true` なら `content/<id>/` も消す

`id` は一度公開したら変更しないこと。変更するとhuxe側に登録済みのRSS URLが死ぬ。

## Cloudflare Pagesで運用する場合

Private repoで運用したい場合や、グローバルCDNが欲しい場合はCloudflare Pagesが代替になる。設定:

1. Cloudflare Dashboard → Workers & Pages → Pages → "Connect to Git"
2. ビルドコマンド: `pip install -e . && python scripts/build.py`
3. ビルド出力ディレクトリ: `dist`
4. 環境変数: `PYTHON_VERSION=3.12`

`base_url` を `https://<project>.pages.dev` (またはカスタムドメイン)に書き換える。GitHub Actionsはこの場合不要なので削除してよい。

## 制約と注意

- **公開リポジトリ前提**: GitHub Pages Freeはpublic repoのみ。`content/`に置く要約は世界公開される
- **業務情報・顧客データは絶対に置かない**
- **huxeのRSSポーリング頻度は非公開**: pushしてすぐhuxeに反映されるわけではない
- **NotebookLM非公式APIには依存しない**: 要約のコピペは手動 or Claude経由が原則

## ライセンス

個人利用前提のスケルトンとして提供。MIT相当の自由利用を想定。
