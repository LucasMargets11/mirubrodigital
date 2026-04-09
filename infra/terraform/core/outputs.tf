# ═══════════════════════════════════════════════════════════════════════════════
# Core Infrastructure — Outputs
# ═══════════════════════════════════════════════════════════════════════════════
#
# Consumed by other layers via terraform_remote_state:
#   data.terraform_remote_state.core.outputs.<output_name>

# ── VPC / Networking ─────────────────────────────────────────────────────────

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs (ALB, NAT)"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs (ECS, RDS, ElastiCache)"
  value       = aws_subnet.private[*].id
}

# ── Security Groups ──────────────────────────────────────────────────────────

output "alb_security_group_id" {
  description = "ALB security group ID"
  value       = aws_security_group.alb.id
}

output "ecs_security_group_id" {
  description = "ECS tasks security group ID"
  value       = aws_security_group.ecs.id
}

output "rds_security_group_id" {
  description = "RDS security group ID"
  value       = aws_security_group.rds.id
}

output "redis_security_group_id" {
  description = "Redis security group ID"
  value       = aws_security_group.redis.id
}

# ── ALB ──────────────────────────────────────────────────────────────────────

output "alb_arn" {
  description = "ALB ARN"
  value       = aws_lb.main.arn
}

output "alb_dns_name" {
  description = "ALB DNS name (used as CloudFront origin or direct access)"
  value       = aws_lb.main.dns_name
}

output "alb_zone_id" {
  description = "ALB hosted zone ID (for Route 53 alias records)"
  value       = aws_lb.main.zone_id
}

output "alb_http_listener_arn" {
  description = "HTTP listener ARN (for adding rules in private-app)"
  value       = aws_lb_listener.http.arn
}

output "alb_target_group_api_arn" {
  description = "API target group ARN (for ECS service in private-app)"
  value       = aws_lb_target_group.api.arn
}

output "alb_target_group_web_arn" {
  description = "Web target group ARN (for ECS service in private-app)"
  value       = aws_lb_target_group.web.arn
}

# ── ECS ──────────────────────────────────────────────────────────────────────

output "ecs_cluster_id" {
  description = "ECS cluster ID"
  value       = aws_ecs_cluster.main.id
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "ecs_task_execution_role_arn" {
  description = "ECS task execution role ARN (for pulling images, reading secrets)"
  value       = aws_iam_role.ecs_task_execution.arn
}

output "ecs_task_role_arn" {
  description = "ECS task role ARN (app-level permissions)"
  value       = aws_iam_role.ecs_task.arn
}

# ── ECR ──────────────────────────────────────────────────────────────────────

output "ecr_repository_urls" {
  description = "Map of ECR repository name → URL"
  value       = { for name, repo in aws_ecr_repository.repos : name => repo.repository_url }
}

# ── RDS ──────────────────────────────────────────────────────────────────────

output "rds_endpoint" {
  description = "RDS primary endpoint (host:port)"
  value       = aws_db_instance.main.endpoint
}

output "rds_address" {
  description = "RDS hostname (without port)"
  value       = aws_db_instance.main.address
}

output "rds_port" {
  description = "RDS port"
  value       = aws_db_instance.main.port
}

output "rds_db_name" {
  description = "Database name"
  value       = aws_db_instance.main.db_name
}

# ── ElastiCache ──────────────────────────────────────────────────────────────

output "elasticache_primary_endpoint" {
  description = "ElastiCache primary endpoint address"
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "elasticache_redis_url" {
  description = "Full Redis connection URL (rediss:// for TLS)"
  value       = "rediss://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/1"
}
# }

# output "celery_broker_url" {
#   description = "Celery broker URL (ElastiCache, db 0)"
#   value       = "rediss://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0"
# }

# ── Secrets ──────────────────────────────────────────────────────────────────

# output "mfa_key_secret_arn" {
#   description = "ARN of the MFA encryption key secret"
#   value       = aws_secretsmanager_secret.mfa_key.arn
# }

# output "django_secret_key_arn" {
#   description = "ARN of the Django SECRET_KEY secret"
#   value       = aws_secretsmanager_secret.django_secret_key.arn
# }

# output "db_credentials_secret_arn" {
#   description = "ARN of the DB credentials secret"
#   value       = aws_secretsmanager_secret.db_credentials.arn
# }

# output "secrets_read_policy_arn" {
#   description = "IAM policy ARN for reading secrets (attach to ECS task execution role)"
#   value       = aws_iam_policy.secrets_read.arn
# }

# ── WAF (REGIONAL — attached to ALB) ────────────────────────────────────────

# output "waf_web_acl_arn" {
#   description = "WAF WebACL ARN (REGIONAL scope, attached to ALB)"
#   value       = aws_wafv2_web_acl.admin.arn
# }
