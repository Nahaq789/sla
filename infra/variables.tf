variable "bedrock_model_id" {
  description = "Bedrock グローバル推論プロファイル ID（例: us.anthropic.claude-3-5-sonnet-20241022-v2:0）"
  type        = string
}

variable "langfuse_host" {
  description = "Langfuse Cloud のホスト URL（サインアップ時に選択したリージョンに合わせる。例: https://us.cloud.langfuse.com）"
  type        = string
}

variable "alert_email" {
  description = "予算アラートの通知先メールアドレス"
  type        = string
}

variable "monthly_budget_usd" {
  description = "月次予算の上限額（USD）。約 1,500 円相当のデフォルト値を設定"
  type        = number
  default     = 10
}
