# WebAuthn の timeout はクライアントへのヒントに過ぎない

# WebAuthn の timeout はクライアントへのヒントに過ぎない

## ポイント

`PublicKeyCredentialCreationOptions.timeout` / `PublicKeyCredentialRequestOptions.timeout` は **ブラウザへの推奨値（ヒント）** であり、ブラウザ・認証器が独自にクランプしてよいと W3C 仕様に明記されている。サーバ側で「タイムアウトに依存した制御」をしてはならない。

## 仕様レベルの規定

- WebAuthn Level 3 では推奨範囲が示されている
  - **discoverable credential（パスキー）**: 300_000 ms (5分) を上限ヒントとして許容、下限は 30_000 ms
  - **non-discoverable**: 同様に 30s〜300s
- 仕様: "The client may use this hint to display a prompt... The client MAY override this value."

## 実装上の落とし穴

1. **ブラウザ毎にクランプが違う**: Chrome は概ね尊重、Safari は内部上限あり、Firefox は古い実装で 60s 程度に丸めるケースが過去あり
2. **タイムアウト時のエラーは `NotAllowedError`**: ユーザがキャンセルした場合と区別できない。仕様上もこれは privacy 配慮による意図的な仕様
3. **サーバ challenge の TTL とは別物**: timeout で UI を閉じても、サーバ側 challenge がまだ有効なら別経路で悪用される可能性。サーバ側 TTL（通常 60〜120s）で確実に失効させる

## 推奨設定

| シナリオ | timeout |
|---|---|
| 既存ユーザ認証 (`get()`) | 60_000 ms |
| 新規パスキー登録 (`create()`) | 120_000 ms |
| プラットフォーム認証器（Face ID/Touch ID）が確実な場合 | 60_000 ms |
| セキュリティキー利用想定 | 120_000 ms（PIN 入力を考慮） |

## まとめ

- timeout はあくまで UX のヒント。セキュリティ境界はサーバ側 challenge TTL で引く
- タイムアウトとキャンセルが `NotAllowedError` で区別できない前提でリトライ UX を設計する
- 短すぎる値（30s 未満）はブラウザがクランプして無視するので意味がない

