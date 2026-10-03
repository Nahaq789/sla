terraform {
  required_version = ">= 1.9"

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
