# Bedrock ARN の構築にアカウント ID が必要
data "aws_caller_identity" "current" {}

# ===== Lambda 実行ロール =====

resource "aws_iam_role" "lambda_exec" {
  name                  = "slack-issue-agent-organizer-exec"
  force_detach_policies = true

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

# 自分のロググループへの書き込み権限（CreateLogGroup は不要。Terraform で先に作成するため）
resource "aws_iam_policy" "lambda_logs" {
  name = "slack-issue-agent-organizer-logs"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "${aws_cloudwatch_log_group.organizer.arn}:*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_logs.arn
}

# Bedrock モデル呼び出し権限
# グローバル推論プロファイルはリージョンをまたぐため Resource をワイルドカードリージョンにする
resource "aws_iam_policy" "lambda_bedrock" {
  name = "slack-issue-agent-organizer-bedrock"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/anthropic.*",
          "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/*",
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_bedrock" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_bedrock.arn
}

# Langfuse 認証情報を Parameter Store から取得する権限
resource "aws_iam_policy" "lambda_ssm" {
  name = "slack-issue-agent-organizer-ssm"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "ssm:GetParameter"
        Resource = [
          aws_ssm_parameter.langfuse_public_key.arn,
          aws_ssm_parameter.langfuse_secret_key.arn,
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_ssm" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_ssm.arn
}

# ===== n8n 用 IAM ユーザー =====
# アクセスキーは state に平文で残るため Terraform では作成しない
# 発行手順は README を参照

resource "aws_iam_user" "n8n" {
  name          = "slack-issue-agent-n8n"
  force_destroy = true
}

resource "aws_iam_user_policy" "n8n_invoke" {
  name = "slack-issue-agent-n8n-invoke"
  user = aws_iam_user.n8n.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = aws_lambda_function.organizer.arn
      }
    ]
  })
}

# ===== Budgets アクション用ロール =====

resource "aws_iam_role" "budgets_action" {
  name = "slack-issue-agent-budgets-action"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "budgets.amazonaws.com" }
        Action    = "sts:AssumeRole"
        # Confused Deputy 攻撃を防ぐためアカウント ID を条件に指定
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

# Budgets が Lambda 実行ロールに Deny ポリシーをアタッチするための権限
resource "aws_iam_role_policy" "budgets_action" {
  name = "slack-issue-agent-budgets-action"
  role = aws_iam_role.budgets_action.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "iam:AttachRolePolicy"
        Resource = aws_iam_role.lambda_exec.arn
      }
    ]
  })
}

# 予算超過時に Lambda から Bedrock 呼び出しを遮断する Deny ポリシー
resource "aws_iam_policy" "deny_bedrock" {
  name = "slack-issue-agent-deny-bedrock"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Deny"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
        ]
        Resource = "*"
      }
    ]
  })
}
