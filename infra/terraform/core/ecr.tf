# ═══════════════════════════════════════════════════════════════════════════════
# ECR Repositories
# ═══════════════════════════════════════════════════════════════════════════════
#
# Four repos: api, web, celery-worker, celery-beat.
# celery-worker and celery-beat use the same Django image but are separate repos
# so that tagging and lifecycle policies can differ if needed.

resource "aws_ecr_repository" "repos" {
  for_each = toset(var.ecr_repo_names)

  name                 = each.value
  image_tag_mutability = "IMMUTABLE"
  force_delete         = var.environment != "production"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = { Name = each.value }
}

# ── Lifecycle policy: keep last 10 tagged images, expire untagged after 7 days

resource "aws_ecr_lifecycle_policy" "cleanup" {
  for_each = aws_ecr_repository.repos

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep last 20 tagged images"
        selection = {
          tagStatus   = "tagged"
          tagPrefixList = ["v"]
          countType   = "imageCountMoreThan"
          countNumber = 20
        }
        action = { type = "expire" }
      }
    ]
  })
}
