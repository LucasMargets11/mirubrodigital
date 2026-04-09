# ═══════════════════════════════════════════════════════════════════════════════
# ElastiCache Redis
# ═══════════════════════════════════════════════════════════════════════════════

# ── Subnet Group ─────────────────────────────────────────────────────────────

resource "aws_elasticache_subnet_group" "main" {
  name        = "${var.project_name}-${var.environment}-redis"
  description = "Private subnets for ElastiCache"
  subnet_ids  = aws_subnet.private[*].id

  tags = { Name = "${var.project_name}-${var.environment}-redis-subnet-group" }
}

# ── Replication Group (single node for staging) ─────────────────────────────

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${var.project_name}-${var.environment}"
  description          = "Redis — MiRubro ${var.environment} (Celery broker + cache)"

  engine               = "redis"
  engine_version       = "7.1"
  node_type            = var.elasticache_node_type
  num_cache_clusters   = var.environment == "production" ? 2 : 1
  port                 = 6379
  parameter_group_name = "default.redis7"

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auto_minor_version_upgrade = true

  snapshot_retention_limit = var.environment == "production" ? 3 : 0
  maintenance_window       = "Tue:04:00-Tue:05:00"

  tags = { Name = "${var.project_name}-${var.environment}-redis" }
}
