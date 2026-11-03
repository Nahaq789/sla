# 実装役の実行ロール。AgentCore Runtime がコンテナを動かすときに使う
# 今は骨組みなので Bedrock は呼ばない。Bedrock の権限は実装役の中身を入れるときに足す
resource "aws_iam_role" "implementer_exec" {
  name                  = "slack-issue-agent-implementer-exec"
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
            "aws:SourceArn" = "arn:aws:bedrock-agentcore:ap-northeast-1:${data.aws_caller_identity.current.account_id}:*"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "implementer_exec" {
  name = "slack-issue-agent-implementer-exec"
  role = aws_iam_role.implementer_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EcrPull"
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
        ]
        Resource = aws_ecr_repository.implementer.arn
      },
      {
        Sid      = "EcrToken"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:DescribeLogStreams",
          "logs:PutLogEvents",
        ]
        Resource = [
          "arn:aws:logs:ap-northeast-1:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*",
          "arn:aws:logs:ap-northeast-1:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*",
        ]
      },
      {
        Sid      = "LogGroupsList"
        Effect   = "Allow"
        Action   = "logs:DescribeLogGroups"
        Resource = "arn:aws:logs:ap-northeast-1:${data.aws_caller_identity.current.account_id}:log-group:*"
      },
      {
        Sid    = "Traces"
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
          "xray:GetSamplingRules",
          "xray:GetSamplingTargets",
        ]
        Resource = "*"
      },
      {
        Sid      = "Metrics"
        Effect   = "Allow"
        Action   = "cloudwatch:PutMetricData"
        Resource = "*"
        Condition = {
          StringEquals = { "cloudwatch:namespace" = "bedrock-agentcore" }
        }
      },
    ]
  })
}

# 実装役。名前にハイフンは使えない
resource "aws_bedrockagentcore_agent_runtime" "implementer" {
  agent_runtime_name = "slack_issue_agent_implementer"
  description        = "実装役: GitHub Issue からコードを直して Draft PR を作る"
  role_arn           = aws_iam_role.implementer_exec.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.implementer.repository_url}:${var.implementer_image_tag}"
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = "HTTP"
  }

  # 暴走に備えて、1 セッションは 2 時間で止める。待機中のセッションは 15 分で止める
  lifecycle_configuration {
    idle_runtime_session_timeout = 900
    max_lifetime                 = 7200
  }

  # 実行ロールの権限が付く前に作ると、イメージを取得できず作成に失敗する
  depends_on = [aws_iam_role_policy.implementer_exec]
}
