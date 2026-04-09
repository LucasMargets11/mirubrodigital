# ═══════════════════════════════════════════════════════════════════════════════
# ECS Cluster + IAM Roles
# ═══════════════════════════════════════════════════════════════════════════════
#
# This layer creates only the CLUSTER and shared IAM roles.
# Task definitions, services, and auto-scaling are in private-app/.

# ── Cluster ──────────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-${var.environment}"

  setting {
    name  = "containerInsights"
    value = var.environment == "production" ? "enabled" : "disabled"
  }

  tags = { Name = "${var.project_name}-${var.environment}-ecs-cluster" }
}

# ── Task Execution Role (shared by all tasks) ───────────────────────────────
# Allows ECS agent to pull images from ECR, push logs to CloudWatch,
# and read secrets from Secrets Manager / SSM.

resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project_name}-${var.environment}-ecs-task-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${var.project_name}-${var.environment}-ecs-task-execution" }
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_base" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow reading secrets from Secrets Manager (for container env injection)
resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  name = "${var.project_name}-${var.environment}-ecs-secrets"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue"
      ]
      Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:${var.project_name}/${var.environment}/*"
    }]
  })
}

# ── Task Role (app-level permissions, shared baseline) ──────────────────────
# This role is assumed by the running containers. Add app-specific permissions
# (S3 access, SES, etc.) via additional policies in private-app/ if needed.

resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-${var.environment}-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${var.project_name}-${var.environment}-ecs-task" }
}
