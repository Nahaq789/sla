# slack-issue-agent デプロイ管理
# 使い方: just <レシピ名>

infra_dir := "infra"

# レシピ一覧を表示（デフォルト）
default:
    @just --list

# ===== Terraform =====

# Terraform 初期化（初回 or プロバイダー変更後に実行）
init:
    terraform -chdir={{infra_dir}} init

# フォーマットチェック
fmt-check:
    terraform -chdir={{infra_dir}} fmt -check -diff

# フォーマット自動修正
fmt:
    terraform -chdir={{infra_dir}} fmt

# 構文バリデーション
validate:
    terraform -chdir={{infra_dir}} validate

# 差分確認（AWS への変更はしない）
plan: build
    terraform -chdir={{infra_dir}} plan

# インフラ作成・更新（確認あり）
apply: build
    terraform -chdir={{infra_dir}} apply

# インフラ削除（確認あり）
destroy: build
    terraform -chdir={{infra_dir}} destroy

# ===== 整理役 Lambda =====

# デプロイ用の build/organizer/ を作る（plan / apply の前に自動で実行される）
build:
    ./scripts/build_organizer.sh

# 整理役の単体テスト
test:
    uv run --project agents/organizer pytest agents/organizer

# ===== n8n =====

# n8n だけをローカルで起動（トンネルなし。初回のオーナーアカウント作成に使う）
n8n-local:
    docker compose -f n8n/docker-compose.yml up -d n8n
    @echo "エディタ: http://localhost:5678"

# Quick Tunnel と n8n を起動（公開 URL が変わったら表示される）
n8n-up:
    ./scripts/n8n_up.sh

# n8n とトンネルを停止（データは残る）
n8n-down:
    docker compose -f n8n/docker-compose.yml down

# ワークフローを n8n/workflows/ に書き出す（ピン留めしたテストデータは取り除く）
n8n-export:
    ./scripts/n8n_export.sh

# ログを表示（例: just n8n-logs tunnel）
n8n-logs service="n8n":
    docker compose -f n8n/docker-compose.yml logs -f --tail 100 {{service}}

# ===== SSM =====

# Langfuse 公開鍵を SSM に投入（例: just ssm-public pk-lf-xxxx）
ssm-public key:
    aws ssm put-parameter \
        --name "/slack-issue-agent/langfuse/public_key" \
        --value "{{key}}" \
        --type SecureString \
        --overwrite \
        --region ap-northeast-1

# Langfuse 秘密鍵を SSM に投入（例: just ssm-secret sk-lf-xxxx）
ssm-secret key:
    aws ssm put-parameter \
        --name "/slack-issue-agent/langfuse/secret_key" \
        --value "{{key}}" \
        --type SecureString \
        --overwrite \
        --region ap-northeast-1

# ===== IAM =====

# n8n 用アクセスキーを発行（SecretAccessKey はこの時しか取得できない）
create-n8n-key:
    aws iam create-access-key \
        --user-name slack-issue-agent-n8n \
        --region ap-northeast-1

# ===== Lambda =====

# 整理役 Lambda の動作確認（例: just invoke Nahaq789/casino-simulator "残高表示を3桁区切りにしたい"）
# thread_ts は毎回新しい値にする（同じ値だと前回の会話の続きとして扱われる）
invoke repo="Nahaq789/casino-simulator" message="テスト依頼":
    aws lambda invoke \
        --function-name slack-issue-agent-organizer \
        --payload "{\"message\": \"{{message}}\", \"thread_ts\": \"$(date +%s.%6N)\", \"repo\": \"{{repo}}\"}" \
        --cli-binary-format raw-in-base64-out \
        --region ap-northeast-1 \
        /tmp/sla-response.json \
    && cat /tmp/sla-response.json
