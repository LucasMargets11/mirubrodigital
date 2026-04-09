# ═══════════════════════════════════════════════════════════════════════════════
# Private Application Layer — Outputs
# ═══════════════════════════════════════════════════════════════════════════════
#
# For CI/CD pipelines, monitoring dashboards, and operational scripts.

# ── ECS Services ─────────────────────────────────────────────────────────────

output "api_service_name" {
  description = "ECS service name for Django API"
  value       = aws_ecs_service.api.name
}

output "web_service_name" {
  description = "ECS service name for Next.js Web"
  value       = aws_ecs_service.web.name
}

output "celery_worker_service_name" {
  description = "ECS service name for Celery worker"
  value       = aws_ecs_service.celery_worker.name
}

output "celery_beat_service_name" {
  description = "ECS service name for Celery beat"
  value       = aws_ecs_service.celery_beat.name
}

# ── ECS Task Definition ARNs (for CI/CD deploy scripts) ─────────────────────

output "api_task_definition_arn" {
  description = "API task definition ARN (latest revision)"
  value       = aws_ecs_task_definition.api.arn
}

output "web_task_definition_arn" {
  description = "Web task definition ARN (latest revision)"
  value       = aws_ecs_task_definition.web.arn
}

output "celery_worker_task_definition_arn" {
  description = "Celery worker task definition ARN"
  value       = aws_ecs_task_definition.celery_worker.arn
}

output "celery_beat_task_definition_arn" {
  description = "Celery beat task definition ARN"
  value       = aws_ecs_task_definition.celery_beat.arn
}

# ── CloudWatch Log Groups ───────────────────────────────────────────────────

output "api_log_group" {
  description = "CloudWatch log group for API"
  value       = aws_cloudwatch_log_group.api.name
}

output "web_log_group" {
  description = "CloudWatch log group for Web"
  value       = aws_cloudwatch_log_group.web.name
}

output "celery_worker_log_group" {
  description = "CloudWatch log group for Celery worker"
  value       = aws_cloudwatch_log_group.celery_worker.name
}

output "celery_beat_log_group" {
  description = "CloudWatch log group for Celery beat"
  value       = aws_cloudwatch_log_group.celery_beat.name
}

# ── Secrets Manager ARNs ────────────────────────────────────────────────────

output "django_secret_key_arn" {
  description = "Secrets Manager ARN for DJANGO_SECRET_KEY"
  value       = aws_secretsmanager_secret.django_secret_key.arn
}

output "db_password_arn" {
  description = "Secrets Manager ARN for DB password"
  value       = aws_secretsmanager_secret.db_password.arn
}

output "mfa_encryption_key_arn" {
  description = "Secrets Manager ARN for MFA encryption key"
  value       = aws_secretsmanager_secret.mfa_encryption_key.arn
}

output "mp_access_token_arn" {
  description = "Secrets Manager ARN for MercadoPago access token"
  value       = aws_secretsmanager_secret.mp_access_token.arn
}

output "mp_webhook_secret_arn" {
  description = "Secrets Manager ARN for MercadoPago webhook secret"
  value       = aws_secretsmanager_secret.mp_webhook_secret.arn
}
