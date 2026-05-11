# Glacier Vault から S3 Glacier への移行ノート

## 背景

AWS Glacier Vault リソースは Terraform から段階的に deprecated 扱いになっており、
`oca-proxy-prd` のようなレガシー環境を `terraform plan` するだけで警告が出る。
新規ワークロードは S3 Glacier ストレージクラス (Glacier Instant Retrieval /
Flexible Retrieval / Deep Archive) を使うのが現行のベストプラクティス。

## 移行方針

1. 既存 Vault の中身をリストアップ(`aws glacier list-jobs` でインベントリJobを起動)
2. インベントリ完了後に S3 へ転送 (Glacier 直 → S3 は1段経由が必要)
3. S3 側でライフサイクルポリシーを切って Glacier Flexible Retrieval に落とす
4. Vault 側を空にして削除
5. Terraform から `aws_glacier_vault` 定義を撤去

## ハマりどころ

- Vault の retrieval は **Standard で 3-5 時間** かかる。1日仕事で見積もる
- IAM ロールを S3 と Glacier 両方に向ける必要がある
- Vault Lock がかかっていると消せない。先に Lock 解除が必要

## サンプル
