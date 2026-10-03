# agents/organizer/ ディレクトリを zip 化してデプロイ用アーカイブを生成
data "archive_file" "organizer" {
  type        = "zip"
  source_dir  = "${path.module}/../agents/organizer"
  output_path = "${path.module}/../build/organizer.zip"
}

# ログは Terraform で先に作成し、Lambda による自動生成を防いで保持期間を確実に適用する
resource "aws_cloudwatch_log_group" "organizer" {
  name              = "/aws/lambda/slack-issue-agent-organizer"
  retention_in_days = 7
}

resource "aws_lambda_function" "organizer" {
  function_name    = "slack-issue-agent-organizer"
  filename         = data.archive_file.organizer.output_path
  source_code_hash = data.archive_file.organizer.output_base64sha256
  role             = aws_iam_role.lambda_exec.arn
  handler          = "lambda_app.lambda_handler"
  runtime          = "python3.13"
  architectures    = ["arm64"]
  memory_size      = 512
  timeout          = 60

  environment {
    variables = {
      BEDROCK_MODEL_ID = var.bedrock_model_id
      LANGFUSE_HOST    = var.langfuse_host
      # 値ではなく SSM パラメータ名を渡し、Lambda 実行時に取得させる
      LANGFUSE_PUBLIC_KEY_PARAM = aws_ssm_parameter.langfuse_public_key.name
      LANGFUSE_SECRET_KEY_PARAM = aws_ssm_parameter.langfuse_secret_key.name
    }
  }

  # 事前作成したロググループを明示的に指定
  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.organizer.name
  }

  depends_on = [aws_cloudwatch_log_group.organizer]
}
