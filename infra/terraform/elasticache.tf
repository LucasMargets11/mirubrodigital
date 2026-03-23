# ═══════════════════════════════════════════════════════════════════════════════
# Amazon ElastiCache (Redis 7.x / Valkey) — Admin Rate Limiting & MFA Tokens
# ═══════════════════════════════════════════════════════════════════════════════
#
# Single-node for staging, multi-AZ replication group for production.
# In-transit encryption enabled (TLS) → Django uses rediss:// scheme.

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project_name}-cache-subnets"
  subnet_ids = var.elasticache_subnet_ids
}

resource "aws_security_group" "elasticache" {
  name_prefix = "${var.project_name}-cache-"
  vpc_id      = var.vpc_id
  description = "ElastiCache access from ECS tasks"

  ingress {
    description     = "Redis from app"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [var.app_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${var.project_name}-cache"
  description          = "Redis for admin auth rate-limiting, MFA tokens, Celery broker"

  engine         = "redis"
  engine_version = "7.1"
  node_type      = var.elasticache_node_type
  port           = 6379

  # Single shard, 1 replica for production HA
  num_cache_clusters = var.environment == "production" ? 2 : 1

  # TLS
  transit_encryption_enabled = true
  at_rest_encryption_enabled = true

  # Network
  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.elasticache.id]

  # Maintenance / snapshots
  maintenance_window       = "sun:03:00-sun:04:00"
  snapshot_retention_limit = var.environment == "production" ? 7 : 0
  snapshot_window          = "02:00-03:00"

  automatic_failover_enabled = var.environment == "production"
  multi_az_enabled           = var.environment == "production"

  apply_immediately = true
}
