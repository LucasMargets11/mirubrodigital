# ═══════════════════════════════════════════════════════════════════════════════
# Security Groups
# ═══════════════════════════════════════════════════════════════════════════════
#
# Principle: least-privilege. Each SG only allows traffic it needs.
# Ingress chains: Internet → ALB → ECS → (RDS | Redis)

# ── ALB Security Group ──────────────────────────────────────────────────────

resource "aws_security_group" "alb" {
  name_prefix = "${var.project_name}-${var.environment}-alb-"
  description = "ALB — accepts HTTP(S) from the internet"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${var.project_name}-${var.environment}-alb-sg" }

  lifecycle { create_before_destroy = true }
}

resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTP from internet (redirects to HTTPS)"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTPS from internet"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "alb_to_ecs" {
  security_group_id            = aws_security_group.alb.id
  description                  = "To ECS tasks"
  ip_protocol                  = "tcp"
  from_port                    = 0
  to_port                      = 65535
  referenced_security_group_id = aws_security_group.ecs.id
}

# ── ECS Security Group ──────────────────────────────────────────────────────

resource "aws_security_group" "ecs" {
  name_prefix = "${var.project_name}-${var.environment}-ecs-"
  description = "ECS tasks — accepts traffic from ALB only"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${var.project_name}-${var.environment}-ecs-sg" }

  lifecycle { create_before_destroy = true }
}

resource "aws_vpc_security_group_ingress_rule" "ecs_from_alb" {
  security_group_id            = aws_security_group.ecs.id
  description                  = "From ALB"
  ip_protocol                  = "tcp"
  from_port                    = 0
  to_port                      = 65535
  referenced_security_group_id = aws_security_group.alb.id
}

resource "aws_vpc_security_group_egress_rule" "ecs_all_outbound" {
  security_group_id = aws_security_group.ecs.id
  description       = "All outbound (ECR pulls, external APIs, etc.)"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# ── RDS Security Group ──────────────────────────────────────────────────────

resource "aws_security_group" "rds" {
  name_prefix = "${var.project_name}-${var.environment}-rds-"
  description = "RDS PostgreSQL — accepts connections from ECS only"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${var.project_name}-${var.environment}-rds-sg" }

  lifecycle { create_before_destroy = true }
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_ecs" {
  security_group_id            = aws_security_group.rds.id
  description                  = "PostgreSQL from ECS"
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.ecs.id
}

resource "aws_vpc_security_group_egress_rule" "rds_no_outbound" {
  security_group_id = aws_security_group.rds.id
  description       = "No outbound (DB does not initiate connections)"
  ip_protocol       = "-1"
  cidr_ipv4         = "127.0.0.1/32"
}

# ── Redis Security Group ────────────────────────────────────────────────────

resource "aws_security_group" "redis" {
  name_prefix = "${var.project_name}-${var.environment}-redis-"
  description = "ElastiCache Redis — accepts connections from ECS only"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${var.project_name}-${var.environment}-redis-sg" }

  lifecycle { create_before_destroy = true }
}

resource "aws_vpc_security_group_ingress_rule" "redis_from_ecs" {
  security_group_id            = aws_security_group.redis.id
  description                  = "Redis from ECS"
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
  referenced_security_group_id = aws_security_group.ecs.id
}

resource "aws_vpc_security_group_egress_rule" "redis_no_outbound" {
  security_group_id = aws_security_group.redis.id
  description       = "No outbound"
  ip_protocol       = "-1"
  cidr_ipv4         = "127.0.0.1/32"
}
