---
name: huxe-bridge
description: NotebookLMの要約MarkdownをhuxeのLive StationにRSS経由で配信するためのワークフロー管理スキル。要約の追加、カテゴリ管理(追加・削除・有効/無効切り替え)、RSSビルド、GitHub Pagesへの公開までを一貫して扱う。ユーザーが「huxeに新しい要約を追加」「カテゴリを追加/削除」「フィードを更新」「NotebookLMの要約を流し込む」「huxeのLive StationのRSSが欲しい」「興味カテゴリを整理したい」といった話題を出したとき、また NotebookLM の要約や `categories.yaml` や `content/` ディレクトリに言及があったときは必ずこのスキルを使うこと。
---

# huxe-bridge

NotebookLMで作った要約Markdownを、huxeのLive Stationが取り込めるRSSフィードに変換して配信するためのパーソナルパイプライン。

## このシステムの全体像

```
[NotebookLM] → Markdown要約
                  ↓ (人 or MCP経由で追加)
            content/<category>/*.md
                  ↓ (git push)
            GitHub Actions → build.py
                  ↓
            GitHub Pages
                  ↓
            <base>/<category>.xml ← huxeのLive Stationに登録
```

huxeはGoogle Drive直結機能を持たず、ソースとして受け入れるのはURL/RSS/X/subredditなど。RSSが最も継続運用に適しているので、このスキルはRSS出力を一級市民として扱う。

## ディレクトリ構造

```
huxe-bridge/
├── config/categories.yaml       ← ★ 唯一の設定。これを編集すれば反映
├── content/<category-id>/*.md   ← ★ 要約はここに置く
├── scripts/build.py             ← md→HTML+RSSビルダー
├── mcp_server/server.py         ← MCPサーバ実装
└── dist/                        ← ビルド成果物(gitignore)
```

## 操作の原則

ユーザーが何かを依頼してきたら、**直接ファイルを編集するのではなくMCPツール経由で操作する**。理由は3つ:

1. categories.yamlのバリデーション(id重複、命名規則)をサーバ側で集約
2. ディレクトリ作成と設定更新の原子性を担保
3. 操作ログがツール呼び出しとして残る

MCPが利用できない環境では、ファイル直接編集にフォールバックするが、その場合も以下の制約を必ず守る:

- カテゴリidは `^[a-z0-9][a-z0-9-]*$` のみ
- 同じidを2回登録しない
- カテゴリを削除するときは `content/<id>` の扱いをユーザーに確認

## 典型タスクの進め方

### 1. 要約を追加する

ユーザーが「NotebookLMで作ったこの要約を追加して」と言ってきたら:

1. どのカテゴリに入れるかを `list_categories` で確認・提示
2. カテゴリが存在しない場合は `add_category` で作成提案
3. `add_summary(category_id, title, body_markdown)` を呼ぶ
4. ローカル確認したい場合は `build` を実行
5. 公開するなら `git_publish` を呼ぶ

要約本文がH1タイトル行で始まっている場合、`add_summary` のtitle引数とH1が重複しないよう注意する(自動でH1が付与される)。

### 2. カテゴリを追加する

ユーザーが「○○というカテゴリを追加したい」と言ってきたら:

1. id案を提案(英小文字・ハイフンへ正規化、例: 「機械学習」→ `machine-learning`)
2. ユーザーに確認を取る
3. `add_category(id, name, description, tags)` を呼ぶ
4. 既存と重複したらエラーを返してユーザーに別案を促す

### 3. カテゴリを一時停止する

「○○は当分使わない」と言われたら、`remove_category` ではなく `toggle_category(id, active=False)` を使う。後で復活させやすい。完全削除を求められた場合だけ `remove_category` を提案し、`delete_files` の挙動(content配下を消すかどうか)を必ず確認する。

### 4. huxe側に登録するURLを聞かれた

`get_feed_urls` を呼んで結果を提示する。出力にはall_feedとカテゴリごとのRSS URLが含まれるので、ユーザーは目的に応じて選べる。Live Stationの「ソースを追加」→「RSS feed」を選ぶ、という操作を案内する。

### 5. 「今すぐ公開して」

`git_publish` を呼ぶ。これは `git add -A && git commit && git push` を順に走らせる。pushされるとGitHub Actionsがビルドし、数十秒〜数分でPagesに反映される。huxe側のRSSポーリング間隔はhuxe側の都合なので、即時反映は期待しない。

## ベストプラクティスと落とし穴

### content/ に置くMarkdownの書き方

- 1行目を `# タイトル` にする(無くてもよいが、あればRSSのタイトルになる)
- NotebookLMからコピーした要約はそのまま貼ってよい
- ファイル名は日付プレフィクスを推奨: `2026-05-11-aws-glacier-migration.md`
- 画像参照は絶対URLで(GitHubに置いた画像をraw URLで参照、など)

### カテゴリidの命名

人間が読むのはnameのほう。idはURLとファイルパスに使われるので、後から変えるとhuxe側に登録済みのRSS URLが死ぬ。**idは確定したら変更しない**。リネームしたい場合は、新id作成 → 移行 → 旧id削除、の手順を踏み、ユーザーに「huxe側のRSS再登録が必要」と必ず伝える。

### 公開リポジトリ前提

GitHub PagesはPublic必須(無料プラン)。content/ に置くものは**世界に公開されてよい情報のみ**であることを毎回確認する。業務情報や顧客データを置こうとしているそぶりがあれば、必ず止めて指摘する。Cloudflare Pages + Private repoの代替を提案してもよい。

### ビルドが失敗したら

`build` ツールのstderrを見る。よくある原因:

- categories.yamlの構文エラー(yamlインデント崩れ)
- カテゴリid重複
- feedgen / markdown / pyyaml が未インストール

依存は `pip install -e .` または `pip install feedgen markdown pyyaml` で入る。

## このスキルを使わない場面

- 「huxeとは何か」「NotebookLMとは何か」の純粋な質問
- huxeアプリ自体の操作方法(このリポジトリは関与しない)
- 一般的なRSS/GitHub Pagesの解説

上記はスキル本体を読み込まず、通常の知識で答えてよい。
