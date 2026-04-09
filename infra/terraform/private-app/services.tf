# ═══════════════════════════════════════════════════════════════════════════════
# ECS Services
# ═══════════════════════════════════════════════════════════════════════════════
#
# Four services: api, web, celery-worker, celery-beat.
# api and web are attached to ALB target groups from core/base.
# celery-worker and celery-beat have no load balancer (internal workers).

# ── API Service ──────────────────────────────────────────────────────────────

resource "aws_ecs_service" "api" {
  name            = "${var.project_name}-${var.environment}-api"
  cluster         = local.core.ecs_cluster_id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.core.private_subnet_ids
    security_groups  = [local.core.ecs_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = local.core.alb_target_group_api_arn
    container_name   = "api"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 90

  # Allow task definition to change without TF replacing the service
  lifecycle { ignore_changes = [task_definition] }

  depends_on = [aws_ecs_task_definition.api]

  tags = { Name = "${var.project_name}-${var.environment}-api-service" }
}

# ── Web Service ──────────────────────────────────────────────────────────────

resource "aws_ecs_service" "web" {
  name            = "${var.project_name}-${var.environment}-web"
  cluster         = local.core.ecs_cluster_id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = var.web_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.core.private_subnet_ids
    security_groups  = [local.core.ecs_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = local.core.alb_target_group_web_arn
    container_name   = "web"
    container_port   = 3000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 60

  lifecycle { ignore_changes = [task_definition] }

  depends_on = [aws_ecs_task_definition.web]

  tags = { Name = "${var.project_name}-${var.environment}-web-service" }
}

# ── Celery Worker Service ────────────────────────────────────────────────────

resource "aws_ecs_service" "celery_worker" {
  name            = "${var.project_name}-${var.environment}-celery-worker"
  cluster         = local.core.ecs_cluster_id
  task_definition = aws_ecs_task_definition.celery_worker.arn
  desired_count   = var.celery_worker_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.core.private_subnet_ids
    security_groups  = [local.core.ecs_security_group_id]
    assign_public_ip = false
  }

  # No load_balancer — workers are not exposed externally

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_minimum_healthy_percent = 0   # Workers can go to 0 during deploy
  deployment_maximum_percent         = 100 # No task overlap needed

  lifecycle { ignore_changes = [task_definition] }

  depends_on = [aws_ecs_task_definition.celery_worker]

  tags = { Name = "${var.project_name}-${var.environment}-celery-worker-service" }
}

# ── Celery Beat Service ──────────────────────────────────────────────────────

resource "aws_ecs_service" "celery_beat" {
  name            = "${var.project_name}-${var.environment}-celery-beat"
  cluster         = local.core.ecs_cluster_id
  task_definition = aws_ecs_task_definition.celery_beat.arn
  desired_count   = 1 # Always exactly 1 — beat must not run in parallel
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.core.private_subnet_ids
    security_groups  = [local.core.ecs_security_group_id]
    assign_public_ip = false
  }

  # No load_balancer — beat is not exposed externally

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_minimum_healthy_percent = 0   # Must stop old before starting new
  deployment_maximum_percent         = 100 # Prevent two beat instances

  lifecycle { ignore_changes = [task_definition] }

  depends_on = [aws_ecs_task_definition.celery_beat]

  tags = { Name = "${var.project_name}-${var.environment}-celery-beat-service" }
}
