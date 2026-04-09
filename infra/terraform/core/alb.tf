# ═══════════════════════════════════════════════════════════════════════════════
# Application Load Balancer
# ═══════════════════════════════════════════════════════════════════════════════
#
# The ALB lives in public subnets and forwards traffic to ECS tasks in private
# subnets. Target groups are created here (stable infra) and referenced by
# ECS services in private-app/ via remote state outputs.
#
# HTTPS listener requires an ACM certificate, which is created in public-dns/.
# Until then, only the HTTP listener is active (for health checks and testing).
# Once ACM is ready, uncomment the HTTPS listener block.

# ── ALB ──────────────────────────────────────────────────────────────────────

resource "aws_lb" "main" {
  name               = "${var.project_name}-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  enable_deletion_protection = var.environment == "production"
  drop_invalid_header_fields = true

  tags = { Name = "${var.project_name}-${var.environment}-alb" }
}

# ── Target Group: API (Django, port 8000) ────────────────────────────────────

resource "aws_lb_target_group" "api" {
  name        = "${var.project_name}-${var.environment}-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip" # Required for Fargate

  health_check {
    path                = "/api/v1/health/"
    protocol            = "HTTP"
    port                = "traffic-port"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = { Name = "${var.project_name}-${var.environment}-api-tg" }
}

# ── Target Group: Web (Next.js, port 3000) ───────────────────────────────────

resource "aws_lb_target_group" "web" {
  name        = "${var.project_name}-${var.environment}-web"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/api/health"
    protocol            = "HTTP"
    port                = "traffic-port"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = { Name = "${var.project_name}-${var.environment}-web-tg" }
}

# ── Listener: HTTP (port 80) ────────────────────────────────────────────────
# In production, this will redirect to HTTPS. For now, it routes to web TG
# so the ALB can be tested before ACM certificates are provisioned.

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }

  tags = { Name = "${var.project_name}-${var.environment}-http-listener" }
}

# ── Listener: HTTPS (port 443) ──────────────────────────────────────────────
# UNCOMMENT after public-dns/ creates the ACM certificate and you have its ARN.
# Then replace the HTTP default action with a redirect to HTTPS.
#
# resource "aws_lb_listener" "https" {
#   load_balancer_arn = aws_lb.main.arn
#   port              = 443
#   protocol          = "HTTPS"
#   ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
#   certificate_arn   = data.terraform_remote_state.dns.outputs.acm_certificate_arn
#
#   default_action {
#     type             = "forward"
#     target_group_arn = aws_lb_target_group.web.arn
#   }
# }
#
# resource "aws_lb_listener_rule" "api_routing" {
#   listener_arn = aws_lb_listener.https.arn
#   priority     = 100
#
#   action {
#     type             = "forward"
#     target_group_arn = aws_lb_target_group.api.arn
#   }
#
#   condition {
#     path_pattern { values = ["/api/*", "/admin/*"] }
#   }
# }
