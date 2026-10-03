# Langfuse 公開鍵
# 初期値はダミー。apply 後に aws ssm put-parameter で本物の値を投入する（README 参照）
resource "aws_ssm_parameter" "langfuse_public_key" {
  name  = "/slack-issue-agent/langfuse/public_key"
  type  = "SecureString"
  value = "placeholder"

  lifecycle {
    ignore_changes = [value]
  }
}

# Langfuse 秘密鍵
resource "aws_ssm_parameter" "langfuse_secret_key" {
  name  = "/slack-issue-agent/langfuse/secret_key"
  type  = "SecureString"
  value = "placeholder"

  lifecycle {
    ignore_changes = [value]
  }
}
