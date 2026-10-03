output "lambda_function_name" {
  description = "整理役 Lambda 関数名"
  value       = aws_lambda_function.organizer.function_name
}

output "lambda_function_arn" {
  description = "整理役 Lambda 関数 ARN"
  value       = aws_lambda_function.organizer.arn
}

output "n8n_iam_user_name" {
  description = "n8n 用 IAM ユーザー名"
  value       = aws_iam_user.n8n.name
}

output "langfuse_public_key_param" {
  description = "Langfuse 公開鍵の SSM パラメータ名"
  value       = aws_ssm_parameter.langfuse_public_key.name
}

output "langfuse_secret_key_param" {
  description = "Langfuse 秘密鍵の SSM パラメータ名"
  value       = aws_ssm_parameter.langfuse_secret_key.name
}
