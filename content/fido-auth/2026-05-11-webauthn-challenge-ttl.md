# WebAuthn Challenge の有効期限はサーバ側で持つべき

## 結論

W3C WebAuthn Level 3 仕様の Section 13.4.3 に基づき、Challenge の有効期限は
**Relying Party 側**で決定する。クライアント(ブラウザ/Authenticator)側の
timeout は単なる UX 制御で、サーバ側の検証期限を兼ねるものではない。

## 根拠

- W3C WebAuthn L3 §13.4.3: "The challenge SHOULD be at least 16 bytes long and
  SHOULD have a reasonable expiration time on the server"
- NIST SP 800-63B §5.2.5: Authentication intent verification の文脈で、
  Challenge の rolling reuse を禁止し、サーバ側で nonce 管理することを要請

## TrustBind仕様への影響

- TrustBindが「クライアント側 timeout = challenge有効期限」と主張するのは誤読
- サーバ側の challenge store (Redis等) の TTL こそが正であるべき
- 推奨: サーバTTL 5分、クライアントtimeout 2分(UXのため短く)

