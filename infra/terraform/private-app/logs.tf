# ═══════════════════════════════════════════════════════════════════════════════
# CloudWatch Log Groups
# ═══════════════════════════════════════════════════════════════════════════════

locals {
  log_prefix = "/${var.project_name}/${var.environment}"
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "${local.log_prefix}/ecs/api"
  retention_in_days = var.log_retention_days

  tags = { Name = "${var.project_name}-${var.environment}-api-logs" }
}

resource "aws_cloudwatch_log_group" "web" {
  name              = "${local.log_prefix}/ecs/web"
  retention_in_days = var.log_retention_days

  tags = { Name = "${var.project_name}-${var.environment}-web-logs" }
}

resource "aws_cloudwatch_log_group" "celery_worker" {
  name              = "${local.log_prefix}/ecs/celery-worker"
  retention_in_days = var.log_retention_days

  tags = { Name = "${var.project_name}-${var.environment}-celery-worker-logs" }
}

resource "aws_cloudwatch_log_group" "celery_beat" {
  name              = "${local.log_prefix}/ecs/celery-beat"
  retention_in_days = var.log_retention_days

  tags = { Name = "${var.project_name}-${var.environment}-celery-beat-logs" }
}
