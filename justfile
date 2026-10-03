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
plan:
    terraform -chdir={{infra_dir}} plan

# インフラ作成・更新（確認あり）
apply:
    terraform -chdir={{infra_dir}} apply

# インフラ削除（確認あり）
destroy:
    terraform -chdir={{infra_dir}} destroy

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

# 整理役 Lambda の動作確認（例: just invoke myorg/myrepo）
invoke repo="myorg/myrepo":
    aws lambda invoke \
        --function-name slack-issue-agent-organizer \
        --payload "{\"message\": \"テスト依頼\", \"thread_ts\": \"1234567890.123456\", \"repo\": \"{{repo}}\"}" \
        --cli-binary-format raw-in-base64-out \
        --region ap-northeast-1 \
        /tmp/sla-response.json \
    && cat /tmp/sla-response.json
