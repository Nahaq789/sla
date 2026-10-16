# slack-issue-agent プロジェクト概要

このドキュメントはプロジェクトの全体像と、これまでに決めた設計判断をまとめたもの。
実装時はここに書かれた方針に従い、方針と食い違う変更が必要になった場合は実装前に確認すること。

---

## 1. 目的

Slack で bot に雑な依頼を投げると、完了条件まで書かれた GitHub Issue が作られ、
必要に応じてエージェントが PR まで作成する仕組みを作る。

- 個人の学習・ポートフォリオ用プロジェクト(お試し)
- 学習対象: AWS Bedrock AgentCore、n8n、Langfuse
- 実行頻度は月30回未満の想定。コストは月数百円程度を許容

## 2. 全体の流れ

```
Slack(チャンネルで bot にメンション)
  ↓ Events API
Cloudflare Tunnel → n8n(自宅PC)
  ↓ チャンネルID → リポジトリを対応表で解決
  ↓ Lambda Invoke
整理役 Lambda(Bedrock Claude Sonnet)
  ↓ Issue 案(JSON)を返す
n8n → Slack スレッドに「この内容で作成しますか?」[作成][修正]
  ↓ 情報不足なら質問をスレッドに返して聞き返す
  ↓ [作成] 押下
n8n → GitHub に Issue 作成 → Slack に Issue リンクを通知 [PRも作る][自分でやる]
  ↓ [PRも作る] 押下(フェーズ2)
n8n → AgentCore Runtime(実装役)を起動
  ↓ clone → 修正 → テスト → Draft PR 作成
  ↓ 完了時に n8n の Webhook へコールバック
n8n → Slack スレッドに PR リンク・変更概要を通知
  ↓ GitHub Webhook(PR マージ / CI 結果)
n8n → Langfuse にスコア送信
```

レビューとマージは必ず GitHub 上で人間が行う。Slack のボタンでマージできる設計にはしない。

## 3. フェーズ

### フェーズ1: Issue 作成まで(現在の対象)
- 整理役 Lambda
- n8n ワークフロー(Slack 受信 → 整理役 → 確認ボタン → Issue 作成 → 通知)
- Langfuse で整理役のトレースが見える
- コスト制御(Budgets)

### フェーズ2: PR 作成
- 実装役を AgentCore Runtime で構築(コンテナを ECR に置く)
- AgentCore Gateway で GitHub 操作をツール化、Identity で GitHub トークンを保持
- DynamoDB で月次の使用量カウンター
- Slack の [PRも作る] ボタンから起動

### 将来の拡張(未着手・任意)
- PR レビューコメントが付いたら、Slack から「修正しますか?」→ 実装役に再修正させる
- Langfuse のデータセットで過去 Issue を流し、モデル・プロンプト変更時の成功率とコストを比較
- 簡単な Issue は安いモデル、難しいものは Sonnet、と難易度で振り分ける

## 4. コンポーネントと役割

| コンポーネント | 置き場所 | 役割 |
|---|---|---|
| Slack | SaaS | 依頼の入口、確認ボタン、通知 |
| n8n | 自宅PC(Docker Compose、WSL2) | 段取り役。トリガー受信、分岐、Slack・GitHub 連携、エージェント起動、スコア送信 |
| Cloudflare Tunnel | 自宅PC | n8n を外部公開(Slack イベント、AgentCore コールバック、GitHub Webhook の受信) |
| 整理役 | AWS Lambda | チャット → Issue 案の JSON。曖昧なら質問を返す |
| 実装役 | AWS AgentCore Runtime(フェーズ2) | コード修正・テスト・Draft PR 作成 |
| Bedrock | AWS | Claude Sonnet 4.6(日本国内の推論プロファイル `jp.`、プロンプトキャッシュ有効) |
| Langfuse | Langfuse Cloud(Hobby 無料プラン、日本リージョン) | トレース、コスト可視化、評価スコア |
| GitHub | SaaS | Issue、PR、CI |

### 責務の分け方
- **n8n はエージェントの外側の段取りだけを担当**し、LLM 呼び出しは行わない(n8n の LLM ノードは使わない)。トレースを Langfuse に一本化するため、LLM 呼び出しはすべて整理役・実装役側で行う
- **Slack と Issue 作成のトークンは n8n が持つ**。整理役 Lambda は GitHub を直接操作しない

## 5. 主要な設計判断と理由

| 判断 | 理由 |
|---|---|
| 整理役は Lambda | Bedrock を1回呼んで JSON を返すだけで、数秒〜十数秒で終わる。Runtime は過剰 |
| 実装役は AgentCore Runtime | clone → 修正 → テストを何十ターンも繰り返し15分を超えうる。作業環境を保持し、隔離された作業場が必要 |
| 実装役は「PRも作る」ボタン押下時のみ起動 | コストの大半が実装役のトークン代のため、使う場面を人が選ぶ |
| モデルは Claude Sonnet | お試し段階のため品質優先。利用頻度が低く、安価なモデルとの差は月数百円程度 |
| 推論は日本国内(`jp.` 推論プロファイル) | 日本国内で処理したいため。東京で使える `jp.` の Sonnet は 4.6 が最新(2026-10 時点)なので Claude Sonnet 4.6 を使う |
| n8n はセルフホスト | 無料。Slack 連携と承認ステップを GUI で組める |
| Langfuse は Cloud(Hobby) | セルフホストは Postgres・ClickHouse・Redis・S3 が必要で重い。AWS からトレースを送る経路も単純になる |
| Langfuse は日本リージョン(`https://jp.cloud.langfuse.com`) | トレースにはプロンプトと Issue 案の本文が残るため、推論と同様にデータも国内(東京)に置く。料金はリージョンによらず同じ。リージョンは後から変更できない(アカウントの作り直しが必要) |
| 1 Slack チャンネル = 1 リポジトリ | リポジトリを文章から推測しなくてよく、誤爆がない |
| リージョンは ap-northeast-1(東京) | |
| IaC は Terraform | `terraform destroy` で一括削除できるようにするため |

## 6. マルチリポジトリ対応

- n8n がチャンネル ID → リポジトリの対応表を持つ。キーはチャンネル名ではなく**チャンネル ID**
  ```json
  {
    "C0123ABCD": { "repo": "Nahaq789/pob" }
  }
  ```
- 対応表は当面 n8n のワークフロー内(Set / Code ノード)に直接書く。数が増えたら外部ストアへ移す
- 対応表にないチャンネルでメンションされたら「このチャンネルはリポジトリに紐づいていません」と返して終了
- 整理役はリポジトリを判定しない。渡された `repo` をそのまま Issue 案に載せる
- フェーズ2では、各リポジトリに `AGENTS.md`(言語、テストコマンド、規約)を置き、実装役が最初に読む

## 7. インターフェース

### 整理役 Lambda の入力
```json
{
  "message": "ログイン画面のエラーメッセージを日本語にして",
  "thread_ts": "1727770000.123456",
  "repo": "Nahaq789/pob"
}
```
スレッドで聞き返した後の再呼び出し時は、それまでの会話を渡せるようにすること(形式は実装時に決める)。

### 整理役 Lambda の出力
```json
{
  "status": "ready",
  "repo": "Nahaq789/pob",
  "issue": {
    "title": "ログイン画面のエラーメッセージを日本語化",
    "background": "...",
    "tasks": ["..."],
    "acceptance_criteria": ["..."],
    "labels": ["enhancement"]
  },
  "questions": []
}
```
- 情報が足りない場合は `status: "need_more_info"` とし、`questions` に質問を入れる
- 将来、難易度での振り分けに使うため、`difficulty` の追加を検討してよい

### ID の紐づけ
- Slack スレッドの `thread_ts` を `session_id` として使う
- Langfuse の trace、Issue 本文、PR 本文のすべてに同じ ID を入れ、後から「この依頼は最終的にマージされたか」を追えるようにする
- Langfuse の trace には `repo` もタグとして付ける

## 8. コスト制御

コストのほぼすべては実装役が呼ぶ Bedrock のトークン代。整理役は1回数円以下。

3段構えで止める。

| 層 | 止まるタイミング | 内容 | フェーズ |
|---|---|---|---|
| 1回あたりの上限 | 即時 | 実装役のループで毎ターンのトークン数を加算し、上限超過で打ち切って Slack に報告。ターン数にも上限 | 2 |
| 月の累計チェック | 次回起動時 | 1回ごとの使用量を DynamoDB に記録し、n8n が起動前に今月の累計を確認。超過なら起動しない | 2 |
| AWS Budgets | 数時間遅れ | 月 10 USD(約1,500円)。80% でメール通知、100% で Budgets アクションにより Bedrock 呼び出しを Deny する IAM ポリシーを実行ロールに自動付与 | 1 |

- Budgets はアカウント全体のコストが対象(アカウントの他の請求は月数十円なので問題なし)
- 使っていないときの維持費はほぼ0円(ECR のイメージ保存料などで月数円程度)

### その他のコスト対策(フェーズ2)
- プロンプトキャッシュを必ず有効にする
- 実装役に読ませるファイルを絞る(整理役が Issue に対象ファイルの目星を書く)

## 9. 秘密情報の扱い

| 秘密情報 | 使う場所 | 保存先 |
|---|---|---|
| Slack Bot Token / Signing Secret | n8n | n8n の認証情報ストア |
| GitHub トークン(Issue 作成用) | n8n | n8n の認証情報ストア |
| n8n 用 AWS アクセスキー | n8n | n8n の認証情報ストア |
| Langfuse 公開鍵・秘密鍵 | 整理役・実装役 | SSM Parameter Store(SecureString) |
| GitHub トークン(PR 作成用) | 実装役 | Parameter Store または AgentCore Identity(フェーズ2で決定) |

ルール:
- **秘密情報の値を Terraform のコードや state に入れない**
- Parameter Store のパラメータは Terraform で「入れ物」だけ作り、値はダミー + `lifecycle { ignore_changes = [value] }`。本物の値は `aws ssm put-parameter --overwrite` で投入する
- n8n 用 IAM ユーザーのアクセスキーは Terraform で作らず、CLI で発行する
- GitHub トークンは fine-grained PAT で、対象リポジトリだけに権限を絞る

## 10. インフラ(Terraform)

### 共通ルール
- リージョン: ap-northeast-1
- Terraform 1.11 以上(S3 ネイティブロックを使うため)、AWS プロバイダー v6 系
- `default_tags` で全リソースに `Project = "slack-issue-agent"` を付与
- リソース名のプレフィックスは `slack-issue-agent`
- コメントは日本語

### 運用
- state は S3 に置く(`infra/backend.tf`)
  - バケット: `nahaq-terraform-state-bucket`、key: `sla/terraform.tfstate`、ロックは S3 ネイティブロック(`use_lockfile`)
  - CI 用ロールが読み書きできるのは `sla/` プレフィックス配下のみ
- GitHub Actions(`.github/workflows/terraform.yml`)で、PR 時に `terraform plan`、main マージ時に自動 apply(マージ後に plan を再実行して apply するシンプル方式)
  - OIDC で plan 用ロール(`gha-sla-plan`)/ apply 用ロール(`gha-sla-apply`)を引き受ける
  - CI の Terraform バージョンはワークフローで固定(ローカルと揃える)
  - `terraform.tfvars` は Git 管理外のため、変数は GitHub の Variables / Secrets から `TF_VAR_*` で渡す(手順は README)
  - ジョブに GitHub Environments は使わない(ロールの信頼ポリシーの `sub` 条件と合わなくなるため)
- 環境は1つのみ(dev/prod の分割はしない)
- AWS 共通の土台(state バケット、GitHub OIDC プロバイダー、CI 用 IAM ロール)は別の非公開リポジトリ(aws-bootstrap)で管理済み。このリポジトリでは作らない
- CI 用 IAM ロールの権限も aws-bootstrap 側で管理する
  - apply 用ロールは `ReadOnlyAccess` に加え、`slack-issue-agent-*` という名前のリソースへの書き込みだけを許可している
  - このリポジトリでリソースの種類を増やしたり命名を変えたりした場合は、aws-bootstrap 側の権限も更新する(フェーズ2の ECR・AgentCore・DynamoDB も同様)

### フェーズ1で作るリソース(作成済み)
- **整理役 Lambda**: Python 3.13 / arm64 / メモリ 512MB / タイムアウト 60秒。`archive_file` で `agents/organizer/` を zip 化
  - 環境変数: `BEDROCK_MODEL_ID`、`LANGFUSE_HOST`、Langfuse 鍵の SSM パラメータ名2つ
- **CloudWatch ロググループ**: Terraform で先に作成(保持7日)。Lambda に自動生成させない
- **Lambda 実行ロール**(`force_detach_policies = true`。Budgets アクションが外部からポリシーを付けるため)
  - 自分のロググループへの書き込み
  - `bedrock:InvokeModel` / `InvokeModelWithResponseStream`。対象は `arn:aws:bedrock:*::foundation-model/anthropic.*` と `arn:aws:bedrock:*:<account>:inference-profile/*`(推論プロファイルはリージョンをまたぐためリージョンは `*`)
  - Langfuse 鍵の SSM パラメータ2つへの `ssm:GetParameter`
- **n8n 用 IAM ユーザー**: 整理役 Lambda への `lambda:InvokeFunction` のみ
- **SSM パラメータ**: `/slack-issue-agent/langfuse/public_key`、`/slack-issue-agent/langfuse/secret_key`
- **Budgets**: 予算、80% 通知、100% で Deny ポリシーを付与する Budgets アクション、その実行ロール
  - Budgets アクションの対象ロールは ARN ではなく**ロール名**で指定する

### 変数
- `bedrock_model_id`(デフォルトなし。`jp.anthropic.claude-sonnet-4-6`)
- `langfuse_host`(デフォルトなし。`https://jp.cloud.langfuse.com`)
- `alert_email`
- `monthly_budget_usd`(デフォルト 10)

### フェーズ2で追加するリソース
- ECR(`force_delete = true`、古いイメージを数世代で削除するライフサイクルポリシー)
- AgentCore Runtime、Gateway、Identity
- DynamoDB(オンデマンド、使用量カウンター)

イメージのビルドと push は Terraform の外(Makefile または GitHub Actions)で行い、Terraform はイメージタグを変数で受け取るだけにする。
初回のみ ECR リポジトリを先に作ってから push する必要がある。

## 11. リポジトリ構成

```
.
├── infra/                  # Terraform
├── agents/
│   ├── organizer/          # 整理役(Lambda)
│   │   ├── core.py         # Issue 案を作るロジック本体(Bedrock 呼び出し・プロンプト)
│   │   ├── lambda_app.py   # Lambda の入口(薄く保つ)
│   │   ├── prompts/
│   │   └── tests/
│   └── implementer/        # 実装役(フェーズ2、AgentCore Runtime 用コンテナ)
├── n8n/
│   ├── docker-compose.yml
│   └── workflows/          # ワークフローを JSON でエクスポートして Git 管理
├── .github/workflows/      # Terraform plan / apply
└── docs/
    ├── PROJECT.md          # このファイル
    └── architecture.drawio
```

- 整理役はロジックを `core.py` に閉じ込め、入口を薄くする(実行基盤を後から変えやすくするため)
- 整理役は1回の呼び出しで済むため、エージェントフレームワークは使わず Bedrock の Converse API を直接使う
- 実装役はエージェントフレームワーク(Strands Agents など)の利用を検討する

## 12. n8n

- Docker Compose で自宅PC(WSL2)上に構築
- データベースは標準の SQLite。データ用ボリュームを必ずマウントする
- `WEBHOOK_URL` に Cloudflare Tunnel の公開 URL を設定
- PC が停止している間は動かない(お試しのため許容)
- Slack Trigger は Webhook 方式を使う(Socket Mode は使わない)
- Slack は3秒以内に応答しないとイベントを再送するため、重い処理は非同期にする

## 13. 削除手順(プロジェクト廃止時)

1. `terraform destroy`(AWS リソース一式。Cloudflare をフェーズ以降で Terraform 管理にしていればそれも)
2. AWS の Tag Editor で `Project=slack-issue-agent` を検索し、残骸がないか確認(Terraform 管理外で作られやすいもの: CloudWatch ロググループ、ECR)
3. `docker compose down -v`(n8n)
4. Slack App を削除
5. GitHub のトークン / Webhook を削除
6. Langfuse のプロジェクトを削除
7. Cloudflare のトンネル(と DNS レコード)を削除

## 14. 未決事項

- **Cloudflare Tunnel の URL 固定**: 固定 URL には Cloudflare 管理の独自ドメインが必要(年1,500円前後)。ドメインなしの Quick Tunnel は起動ごとに URL が変わり、Slack・GitHub・コールバック先の再設定が必要になる。ドメインを取得したら、トンネルと DNS も Terraform(Cloudflare プロバイダー)で管理する
- **Bedrock のモデルアクセス**: モデル ID は `jp.anthropic.claude-sonnet-4-6` に決定。アカウントで Anthropic モデルの利用(ユースケース申請・モデルアクセス)が有効かは、整理役で初めて呼び出すときに確認する
- **AgentCore の東京リージョン提供状況**: フェーズ2着手時に Runtime・Gateway が東京で使えるか確認。可能なら Lambda と同じリージョンに揃える
- **実装役のモデル**: 国内処理(`jp.`)の方針を実装役にも適用するか。東京で使える `jp.` の Sonnet は 4.6 まで(2026-10 時点)
- **最初の対象リポジトリと Slack チャンネル**
- **実装役の GitHub トークンの保管先**(Parameter Store か AgentCore Identity か)
