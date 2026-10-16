# state は aws-bootstrap リポジトリで作成した共通 state バケットに置く。
# GitHub Actions 用ロールに許可されているのは "sla/" プレフィックス配下のみのため、key はその下にする。
#
# backend ブロックには変数が使えないため、bucket / region は直接記入する。

terraform {
  backend "s3" {
    bucket       = "nahaq-terraform-state-bucket"
    key          = "sla/terraform.tfstate"
    region       = "ap-northeast-1"
    encrypt      = true
    use_lockfile = true
  }
}
