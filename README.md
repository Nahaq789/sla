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
- Terraform（`.terraform-version` のバージョン。tfenv なら `tfenv install` で入る）がインストール済みであること
- [uv](https://docs.astral.sh/uv/) と [just](https://github.com/casey/just) がインストール済みであること

> **注意**: Lambda の zip は `scripts/build_organizer.sh` が作る `build/organizer/` から生成します。
> `terraform` を直接実行する場合は、先に `just build` を実行してください（`just plan` / `just apply` は自動でビルドします）。
> 整理役の単体テストは `just test` で実行できます。

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

## 別の PC で環境を構築する

AWS のリソースと CI はすでに動いている前提で、開発用の PC を新しく用意するときの手順です。
Git に入っていないもの（tfvars、n8n のデータ）は作り直し、秘密の値は KeePass から取り出して登録します。

### 必要な秘密の値

| 値 | 使う場所 | 保管場所 |
| --- | --- | --- |
| AWS のログイン（自分の IAM ユーザー） | AWS CLI（`just invoke` など） | `aws login` でログインし直す |
| GitHub への push の認証（SSH キーなど） | git | 今の PC と同じ方法で用意する |
| Slack の Bot User OAuth Token（`xoxb-`） | n8n の Slack API 認証情報 | KeePass（Slack App の OAuth & Permissions でも確認できる） |
| Slack の Signing Secret | n8n の Slack API 認証情報 | KeePass（Slack App の Basic Information でも確認できる） |
| n8n 用 IAM ユーザーのアクセスキー | n8n の AWS 認証情報 | KeePass（発行し直す必要はない） |

Langfuse の鍵（SSM に保存済み）、CI の Variables / Secrets（GitHub に登録済み）、Bedrock のユースケース申請（AWS アカウント単位）は、PC を変えても不要です。

### 1. ツールを入れる

- git、Docker（Docker Desktop の場合は、使う WSL ディストロで WSL integration をオンにする）
- AWS CLI v2、[uv](https://docs.astral.sh/uv/)、[just](https://github.com/casey/just)
- [tfenv](https://github.com/tfutils/tfenv)（Terraform のバージョンは `.terraform-version` で固定している）

```bash
git clone git@github.com:Nahaq789/sla.git
cd sla
tfenv install          # .terraform-version のバージョンが入る
aws login              # 自分の IAM ユーザーでログイン（ap-northeast-1）
aws sts get-caller-identity
```

### 2. Terraform とテストを動かせるようにする

```bash
cp infra/terraform.tfvars.example infra/terraform.tfvars
# alert_email を予算アラートの通知先に書き換える（他は example のままでよい）

just init
just plan    # 差分なし（No changes）になれば OK
just test
```

apply は CI（main へのマージ）で行うため、ローカルでは plan までで十分です。

### 3. n8n を起動してオーナーアカウントを作る

n8n のデータ（アカウント、認証情報、実行履歴）は PC の Docker ボリュームにしか入っていないため、新しい PC では作り直します。

```bash
just n8n-local    # トンネルなしで起動
```

http://localhost:5678 を開き、オーナーアカウントを作成します（パスワードは KeePass に保存）。
「Connect a model」の画面はスキップします（n8n では LLM を使わない）。

### 4. 認証情報を登録する

n8n の **Create Credential** から、次の 2 つを登録します。名前はワークフローの JSON に合わせておくと、取り込み後に選び直す手間が減ります。

| 種類 | 名前 | 入力する値 |
| --- | --- | --- |
| Slack API | `Slack issue-agent` | Access Token: Bot User OAuth Token / Signature Secret: Signing Secret |
| AWS | `AWS slack-issue-agent-n8n` | Region: `ap-northeast-1` / Access Key ID・Secret Access Key: n8n 用 IAM ユーザーのアクセスキー |

### 5. ワークフローを取り込む

1. n8n で新しいワークフローを開き、右上の **…** → **Import from File** で `n8n/workflows/slack-issue-agent.json` を選ぶ
2. Slack Trigger と AWS Lambda のノードを開き、認証情報が手順 4 で登録したものになっているか確認する（なっていなければ選び直す）
3. **Save** する（まだ Publish しない）

### 6. トンネルを張り、Slack に URL を登録する

> **注意**: Slack に登録できる Request URL は 1 つだけです。古い PC の n8n は先に止めてください（`just n8n-down`）。

```bash
just n8n-up    # Quick Tunnel を起動し、公開 URL を WEBHOOK_URL に設定して n8n を起動し直す
```

1. n8n でワークフローを **Publish** する
2. Slack Trigger ノードの **Production URL**（`https://<ランダム>.trycloudflare.com/webhook/...`）をコピーする
3. https://api.slack.com/apps → Issue Agent → **Event Subscriptions** の **Request URL** に貼り付け、Verified になったら **Save Changes**

Quick Tunnel の URL はトンネルを起動し直すたびに変わります。`just n8n-up` が「公開 URL が変わりました」と表示したら、手順 2〜3 をやり直してください。

### 7. 動作確認

Slack の `#casino-issue` で `@issue-agent <依頼>` と投稿し、n8n の **Executions** に実行が記録されることを確認します。

### ワークフローを変更したら

n8n の画面で変更したワークフローは自動では Git に入りません。区切りの良いところで書き出してコミットします。

```bash
just n8n-export    # n8n/workflows/ に書き出す（ピン留めしたテストデータは取り除く）
```

---

## CI（GitHub Actions）

`.github/workflows/terraform.yml` で `infra/` を plan / apply します。

- Pull Request: `terraform fmt` / `validate` / `plan`（結果はジョブのサマリーに出力）
- main への push: `terraform apply`

state は aws-bootstrap で作成した S3 バケット（`sla/terraform.tfstate`）に置き、AWS へは OIDC で aws-bootstrap が作成したロールを引き受けて接続します。

Settings → Secrets and variables → Actions に以下を登録してください。

| 種類 | 名前 | 値 |
| --- | --- | --- |
| Variable | `AWS_REGION` | `ap-northeast-1` |
| Variable | `AWS_PLAN_ROLE_ARN` | aws-bootstrap の `terraform output` で確認した plan 用ロールの ARN |
| Variable | `AWS_APPLY_ROLE_ARN` | aws-bootstrap の `terraform output` で確認した apply 用ロールの ARN |
| Variable | `BEDROCK_MODEL_ID` | `terraform.tfvars` の `bedrock_model_id` と同じ値 |
| Variable | `LANGFUSE_HOST` | `terraform.tfvars` の `langfuse_host` と同じ値 |
| Secret | `ALERT_EMAIL` | `terraform.tfvars` の `alert_email` と同じ値 |

> **注意**: CI の Terraform バージョンはワークフローの `TERRAFORM_VERSION` で、ローカルのバージョンはリポジトリルートの `.terraform-version`（tfenv が参照）で固定しています。上げる場合は両方を合わせてください（新しいバージョンで書いた state は古いバージョンで読めなくなります）。

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

## 動作確認（整理役 Lambda を直接呼び出す）

n8n や Slack を通さずに、整理役 Lambda だけを確認できます。Bedrock を実際に呼び出すため、数秒〜10 秒ほどかかります。

```bash
# 引数: リポジトリ、依頼文（省略時は Nahaq789/casino-simulator、「テスト依頼」）
just invoke Nahaq789/casino-simulator "ログイン画面のエラーメッセージが英語なので日本語にしたい"
```

`thread_ts` は実行ごとに新しい値になるため、毎回新しい会話として扱われます（同じ `thread_ts` で呼ぶと、DynamoDB に保存された会話の続きになります）。

レスポンスは次の 3 種類です（詳細は `docs/PROJECT.md` の入出力の節）。

| `status` | 意味 | 主な中身 |
| --- | --- | --- |
| `ready` | Issue 案を作れた | `issue`（`title`、`background`、`tasks`、`acceptance_criteria`、`labels`） |
| `need_more_info` | 情報が足りない | `questions`（最大 3 つ）。`issue` は `null` |
| `error` | 失敗した | `error.code`（`invalid_request`、`invalid_model_output`、`bedrock_access_denied`、`conflict`）と `error.message` |

レスポンスの例（`need_more_info`）:
```json
{
  "repo": "Nahaq789/casino-simulator",
  "thread_ts": "1792363917.157979",
  "status": "need_more_info",
  "issue": null,
  "questions": [
    "残高がマイナスになるのはどのゲームや操作のときですか？（例：ベット時、特定のゲーム終了時、全ゲーム共通、など）"
  ]
}
```

呼び出しの記録は Langfuse（https://jp.cloud.langfuse.com）の Traces に `organizer` という名前で残ります（Session ID は `thread_ts`）。

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
