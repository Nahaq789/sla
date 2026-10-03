# 月次コスト予算（アカウント全体）
resource "aws_budgets_budget" "monthly" {
  name         = "slack-issue-agent-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # 80% 到達でメール通知
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}

# 100% 到達で Bedrock Deny ポリシーを Lambda 実行ロールに自動アタッチ
resource "aws_budgets_budget_action" "deny_bedrock_on_exceed" {
  budget_name        = aws_budgets_budget.monthly.name
  action_type        = "APPLY_IAM_POLICY"
  approval_model     = "AUTOMATIC"
  notification_type  = "ACTUAL"
  execution_role_arn = aws_iam_role.budgets_action.arn

  action_threshold {
    action_threshold_type  = "PERCENTAGE"
    action_threshold_value = 100
  }

  definition {
    iam_action_definition {
      policy_arn = aws_iam_policy.deny_bedrock.arn
      roles      = [aws_iam_role.lambda_exec.arn]
    }
  }

  subscriber {
    address           = var.alert_email
    subscription_type = "EMAIL"
  }
}
