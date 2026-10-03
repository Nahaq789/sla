# slack-issue-agent

Slack で bot に依頼 → 整理役 Lambda が Issue 案を作成 → 確認後に GitHub Issue 作成、という仕組みのフェーズ1 インフラです。
n8n（自宅 PC セルフホスト）が段取り役として整理役 Lambda を呼び出します。

## アーキテクチャ（フェーズ1）

```
Slack → n8n (自宅PC) → Lambda (整理役) → n8n → GitHub Issue
```

---

## 初回セットアップ

### 前提条件

- AWS CLI が設定済みであること（`aws sts get-caller-identity` で確認）
- Terraform >= 1.9 がインストール済みであること

### 手順

```bash
# 1. リポジトリルートに移動
cd /path/to/slack-issue-agent

# 2. tfvars を作成
cp infra/terraform.tfvars.example infra/terraform.tfvars
# terraform.tfvars を編集して各変数に値を入力

# 3. 初期化
cd infra
terraform init

# 4. 差分確認（apply は後述の鍵投入後に行う）
terraform plan
```

> **注意**: `terraform apply` を実行する前に Langfuse 鍵の投入（下記参照）は不要です。
> apply 後に SSM パラメータが作成されるので、その後で上書きしてください。

```bash
# 5. apply
terraform apply
```

---

## Langfuse 鍵の投入

apply 後、ダミー値が入った SSM パラメータに本物の値を上書きします。

```bash
# 公開鍵
aws ssm put-parameter \
  --name "/slack-issue-agent/langfuse/public_key" \
  --value "pk-lf-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
  --type SecureString \
  --overwrite \
  --region ap-northeast-1

# 秘密鍵
aws ssm put-parameter \
  --name "/slack-issue-agent/langfuse/secret_key" \
  --value "sk-lf-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
  --type SecureString \
  --overwrite \
  --region ap-northeast-1
```

> Terraform の `lifecycle { ignore_changes = [value] }` により、次回 `terraform apply` を実行しても上書きした値は保護されます。

---

## n8n 用アクセスキーの発行

アクセスキーは Terraform state に平文で残るため、Terraform では作成していません。
AWS CLI で手動発行してください。

```bash
# アクセスキーを発行（出力に SecretAccessKey が含まれる。この時しか取得できない）
aws iam create-access-key \
  --user-name slack-issue-agent-n8n \
  --region ap-northeast-1
```

出力例:
```json
{
    "AccessKey": {
        "UserName": "slack-issue-agent-n8n",
        "AccessKeyId": "AKIAXXXXXXXXXXXXXXXX",
        "Status": "Active",
        "SecretAccessKey": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "CreateDate": "2025-01-01T00:00:00+00:00"
    }
}
```

`AccessKeyId` と `SecretAccessKey` を n8n の AWS 認証情報に設定してください。

---

## 動作確認（aws lambda invoke）

フェーズ1 はフェーズ1固定レスポンスを返します。

```bash
aws lambda invoke \
  --function-name slack-issue-agent-organizer \
  --payload '{"message": "テスト依頼", "thread_ts": "1234567890.123456", "repo": "myorg/myrepo"}' \
  --cli-binary-format raw-in-base64-out \
  --region ap-northeast-1 \
  /tmp/response.json && cat /tmp/response.json
```

期待するレスポンス:
```json
{
  "status": "ready",
  "repo": "myorg/myrepo",
  "issue": {
    "title": "仮タイトル（フェーズ1 固定レスポンス）",
    "background": "背景情報をここに記載します",
    "tasks": ["タスク1", "タスク2"],
    "acceptance_criteria": ["完了条件1", "完了条件2"],
    "labels": ["enhancement"]
  },
  "questions": []
}
```

---

## 削除手順

### 1. terraform destroy でリソースを削除

```bash
cd infra
terraform destroy
```

> 予算アクションが発動して `slack-issue-agent-deny-bedrock` ポリシーが Lambda ロールに自動アタッチされていた場合でも、Lambda 実行ロールに `force_detach_policies = true` を設定しているため、Terraform が destroy 時に自動デタッチして問題なく削除できます。

### 2. Tag Editor で残骸確認

`terraform destroy` が完了した後、AWS コンソールの **Resource Groups & Tag Editor** でタグ `Project = slack-issue-agent` のリソースが残っていないか確認してください。

1. AWS コンソール → **Resource Groups & Tag Editor** → **Tag Editor**
2. リージョン: `ap-northeast-1`（+ `us-east-1`、Budgets はグローバルサービスのため）
3. タグキー: `Project`、タグ値: `slack-issue-agent` で検索
4. 残存リソースがあれば手動削除する

> SSM パラメータは Tag Editor に表示されないことがあります。以下のコマンドでも確認してください。
>
> ```bash
> aws ssm describe-parameters \
>   --filters "Key=Path,Values=/slack-issue-agent" \
>   --region ap-northeast-1
> ```
