terraform {
  # S3 ネイティブロック (use_lockfile) を使うため 1.11 以上
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = "ap-northeast-1"

  # 全リソースに共通タグを付与
  default_tags {
    tags = {
      Project = "slack-issue-agent"
    }
  }
}
