# 実装役のコンテナイメージ。ビルドと push は Terraform の外で行う（just implementer-push）
resource "aws_ecr_repository" "implementer" {
  name = "slack-issue-agent-implementer"
  # タグはコミットの SHA なので、同じタグが別の中身を指さないように上書きを禁止する
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# 古いイメージは新しい 5 世代を残して削除する
resource "aws_ecr_lifecycle_policy" "implementer" {
  repository = aws_ecr_repository.implementer.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the latest 5 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
