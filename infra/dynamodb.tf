# 整理役の会話履歴。1 スレッド (Slack の thread_ts) = 1 アイテム
# 聞き返しや [修正] で整理役を再度呼んだときに、それまでの会話を読み出すために使う
resource "aws_dynamodb_table" "conversations" {
  name         = "slack-issue-agent-conversations"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "thread_ts"

  attribute {
    name = "thread_ts"
    type = "S"
  }

  # 古い会話は expires_at (UNIX 秒) を過ぎたら自動で削除する。期間は Lambda 側で決める (30 日)
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
