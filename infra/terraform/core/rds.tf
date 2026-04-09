# ═══════════════════════════════════════════════════════════════════════════════
# RDS PostgreSQL
# ═══════════════════════════════════════════════════════════════════════════════

# ── Subnet Group ─────────────────────────────────────────────────────────────

resource "aws_db_subnet_group" "main" {
  name        = "${var.project_name}-${var.environment}-db"
  description = "Private subnets for RDS"
  subnet_ids  = aws_subnet.private[*].id

  tags = { Name = "${var.project_name}-${var.environment}-db-subnet-group" }
}

# ── Parameter Group ──────────────────────────────────────────────────────────

resource "aws_db_parameter_group" "postgres16" {
  name_prefix = "${var.project_name}-${var.environment}-pg16-"
  family      = "postgres16"
  description = "PostgreSQL 16 — MiRubro ${var.environment}"

  parameter {
    name  = "log_min_duration_statement"
    value = "1000" # Log queries slower than 1s
  }

  parameter {
    name  = "log_connections"
    value = "1"
  }

  parameter {
    name  = "log_disconnections"
    value = "1"
  }

  lifecycle { create_before_destroy = true }

  tags = { Name = "${var.project_name}-${var.environment}-pg16-params" }
}

# ── RDS Instance ─────────────────────────────────────────────────────────────

resource "aws_db_instance" "main" {
  identifier = "${var.project_name}-${var.environment}"

  engine         = "postgres"
  engine_version = "16"
  instance_class = var.rds_instance_class

  allocated_storage     = var.rds_allocated_storage
  max_allocated_storage = var.rds_allocated_storage * 2 # Auto-scaling ceiling
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  multi_az               = var.rds_multi_az
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.postgres16.name

  backup_retention_period = 7
  backup_window           = "03:00-04:00"       # UTC
  maintenance_window      = "Mon:04:00-Mon:05:00"

  skip_final_snapshot       = var.environment != "production"
  final_snapshot_identifier = var.environment == "production" ? "${var.project_name}-final-snapshot" : null
  deletion_protection       = var.environment == "production"
  copy_tags_to_snapshot     = true

  performance_insights_enabled = false # Enable in production

  tags = { Name = "${var.project_name}-${var.environment}-postgres" }
}
