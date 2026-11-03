# GitHub トークンの置き場所。AgentCore Identity が Secrets Manager に保管する
# Terraform にはダミー値だけを渡す。本物は just github-token で登録するので、state にもリポジトリにも残らない
resource "aws_bedrockagentcore_api_key_credential_provider" "github" {
  name    = "slack-issue-agent-github"
  api_key = "placeholder-set-with-just-github-token"

  lifecycle {
    ignore_changes = [api_key]
  }
}

# Gateway が使うロール。トークンを読めるのはこのロールだけにする (実装役の実行ロールには渡さない)
resource "aws_iam_role" "github_gateway" {
  name                  = "slack-issue-agent-github-gateway"
  force_detach_policies = true

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "bedrock-agentcore.amazonaws.com" }
        Action    = "sts:AssumeRole"
        # Confused Deputy 攻撃を防ぐためアカウント ID と呼び出し元を条件に指定
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
          ArnLike = {
            "aws:SourceArn" = "arn:aws:bedrock-agentcore:ap-northeast-1:${data.aws_caller_identity.current.account_id}:gateway/slack-issue-agent-github-*"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "github_gateway" {
  name = "slack-issue-agent-github-gateway"
  role = aws_iam_role.github_gateway.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "WorkloadAccessToken"
        Effect = "Allow"
        Action = "bedrock-agentcore:GetWorkloadAccessToken"
        Resource = [
          "arn:aws:bedrock-agentcore:ap-northeast-1:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default",
          "arn:aws:bedrock-agentcore:ap-northeast-1:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default/workload-identity/slack-issue-agent-github-*",
        ]
      },
      {
        Sid      = "GitHubApiKey"
        Effect   = "Allow"
        Action   = "bedrock-agentcore:GetResourceApiKey"
        Resource = aws_bedrockagentcore_api_key_credential_provider.github.credential_provider_arn
      },
      {
        Sid      = "GitHubApiKeySecret"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = aws_bedrockagentcore_api_key_credential_provider.github.api_key_secret_arn[0].secret_arn
      },
    ]
  })
}

# 実装役から GitHub を呼ぶ窓口。呼び出しは IAM 署名で確認する
resource "aws_bedrockagentcore_gateway" "github" {
  name            = "slack-issue-agent-github"
  description     = "実装役が GitHub API を呼ぶための Gateway"
  role_arn        = aws_iam_role.github_gateway.arn
  authorizer_type = "AWS_IAM"
  protocol_type   = "MCP"

  depends_on = [aws_iam_role_policy.github_gateway]
}

# 許可する API の一覧は github_tools_openapi.json に書く
resource "aws_bedrockagentcore_gateway_target" "github" {
  name               = "github"
  description        = "実装役に許可する GitHub API"
  gateway_identifier = aws_bedrockagentcore_gateway.github.gateway_id

  credential_provider_configuration {
    api_key {
      provider_arn              = aws_bedrockagentcore_api_key_credential_provider.github.credential_provider_arn
      credential_location       = "HEADER"
      credential_parameter_name = "Authorization"
      credential_prefix         = "Bearer"
    }
  }

  target_configuration {
    mcp {
      open_api_schema {
        inline_payload {
          payload = file("${path.module}/github_tools_openapi.json")
        }
      }
    }
  }
}
