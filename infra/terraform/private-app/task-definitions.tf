# ═══════════════════════════════════════════════════════════════════════════════
# ECS Task Definitions
# ═══════════════════════════════════════════════════════════════════════════════
#
# Four tasks: api, web, celery-worker, celery-beat.
# All use Fargate launch type. Images come from ECR repos created in core/base.
# Secrets are injected from Secrets Manager via `secrets` (not `environment`).

locals {
  # Shorthand for remote state outputs
  core = data.terraform_remote_state.core.outputs

  # Common secrets block for Django containers (api, celery-worker, celery-beat)
  django_secrets = [
    { name = "DJANGO_SECRET_KEY",  valueFrom = aws_secretsmanager_secret.django_secret_key.arn },
    { name = "POSTGRES_PASSWORD",  valueFrom = aws_secretsmanager_secret.db_password.arn },
    { name = "MFA_ENCRYPTION_KEY", valueFrom = aws_secretsmanager_secret.mfa_encryption_key.arn },
    { name = "MP_ACCESS_TOKEN",    valueFrom = aws_secretsmanager_secret.mp_access_token.arn },
    { name = "MP_WEBHOOK_SECRET",  valueFrom = aws_secretsmanager_secret.mp_webhook_secret.arn },
  ]

  # Common env vars for Django containers
  django_environment = [
    { name = "DJANGO_DEBUG",         value = "False" },
    { name = "DJANGO_ALLOWED_HOSTS", value = var.django_allowed_hosts },
    { name = "POSTGRES_HOST",        value = local.core.rds_address },
    { name = "POSTGRES_PORT",        value = tostring(local.core.rds_port) },
    { name = "POSTGRES_DB",          value = local.core.rds_db_name },
    { name = "POSTGRES_USER",        value = var.db_username },
    { name = "REDIS_URL",            value = local.core.elasticache_redis_url },
    { name = "CACHE_REDIS_URL",      value = local.core.elasticache_redis_url },
    { name = "CORS_ALLOWED_ORIGINS", value = var.cors_allowed_origins },
    { name = "COOKIE_SECURE",        value = "True" },
  ]
}

# ── API Task Definition ──────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project_name}-${var.environment}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = local.core.ecs_task_execution_role_arn
  task_role_arn            = local.core.ecs_task_role_arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = var.api_image
      essential = true

      portMappings = [{
        containerPort = 8000
        protocol      = "tcp"
      }]

      environment = local.django_environment
      secrets     = local.django_secrets

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/api/v1/health/ || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = { Name = "${var.project_name}-${var.environment}-api-task" }
}

# ── Web Task Definition ──────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "web" {
  family                   = "${var.project_name}-${var.environment}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.web_cpu
  memory                   = var.web_memory
  execution_role_arn       = local.core.ecs_task_execution_role_arn
  task_role_arn            = local.core.ecs_task_role_arn

  container_definitions = jsonencode([
    {
      name      = "web"
      image     = var.web_image
      essential = true

      portMappings = [{
        containerPort = 3000
        protocol      = "tcp"
      }]

      environment = [
        { name = "NEXT_PUBLIC_API_URL",  value = "https://api.${var.domain_name}" },
        { name = "NEXT_PUBLIC_BASE_URL", value = "https://www.${var.domain_name}" },
        { name = "API_URL_INTERNAL",     value = "http://localhost:8000" },
        { name = "NODE_ENV",             value = "production" },
        { name = "PORT",                 value = "3000" },
        { name = "HOSTNAME",             value = "0.0.0.0" },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.web.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "web"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:3000/api/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
    }
  ])

  tags = { Name = "${var.project_name}-${var.environment}-web-task" }
}

# ── Celery Worker Task Definition ────────────────────────────────────────────

resource "aws_ecs_task_definition" "celery_worker" {
  family                   = "${var.project_name}-${var.environment}-celery-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.celery_worker_cpu
  memory                   = var.celery_worker_memory
  execution_role_arn       = local.core.ecs_task_execution_role_arn
  task_role_arn            = local.core.ecs_task_role_arn

  container_definitions = jsonencode([
    {
      name      = "celery-worker"
      image     = var.api_image # Same Django image, different entrypoint
      essential = true

      command = ["celery", "-A", "config.celery", "worker", "--loglevel=info", "--concurrency=2"]

      environment = local.django_environment
      secrets     = local.django_secrets

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.celery_worker.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "celery-worker"
        }
      }
    }
  ])

  tags = { Name = "${var.project_name}-${var.environment}-celery-worker-task" }
}

# ── Celery Beat Task Definition ──────────────────────────────────────────────

resource "aws_ecs_task_definition" "celery_beat" {
  family                   = "${var.project_name}-${var.environment}-celery-beat"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.celery_beat_cpu
  memory                   = var.celery_beat_memory
  execution_role_arn       = local.core.ecs_task_execution_role_arn
  task_role_arn            = local.core.ecs_task_role_arn

  container_definitions = jsonencode([
    {
      name      = "celery-beat"
      image     = var.api_image # Same Django image, different entrypoint
      essential = true

      command = ["celery", "-A", "config.celery", "beat", "--loglevel=info"]

      environment = local.django_environment
      secrets     = local.django_secrets

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.celery_beat.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "celery-beat"
        }
      }
    }
  ])

  tags = { Name = "${var.project_name}-${var.environment}-celery-beat-task" }
}
