# ═══════════════════════════════════════════════════════════════════════════════
# Secrets Manager — Application Secrets
# ═══════════════════════════════════════════════════════════════════════════════
#
# Secrets are injected into ECS task definitions via `valueFrom`.
# The task execution role in core/base already has permission to read
# secrets matching: arn:aws:secretsmanager:<region>:*:secret:<project>/<env>/*

locals {
  secrets_prefix = "${var.project_name}/${var.environment}"
}

# ── Django SECRET_KEY ────────────────────────────────────────────────────────

resource "aws_secretsmanager_secret" "django_secret_key" {
  name                    = "${local.secrets_prefix}/django-secret-key"
  description             = "Django SECRET_KEY"
  recovery_window_in_days = var.environment == "production" ? 30 : 0

  tags = { Name = "${var.project_name}-${var.environment}-django-secret-key" }
}

resource "aws_secretsmanager_secret_version" "django_secret_key" {
  secret_id     = aws_secretsmanager_secret.django_secret_key.id
  secret_string = var.django_secret_key
}

# ── Database Password ────────────────────────────────────────────────────────

resource "aws_secretsmanager_secret" "db_password" {
  name                    = "${local.secrets_prefix}/db-password"
  description             = "PostgreSQL master password"
  recovery_window_in_days = var.environment == "production" ? 30 : 0

  tags = { Name = "${var.project_name}-${var.environment}-db-password" }
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = var.db_password
}

# ── MFA Encryption Key ──────────────────────────────────────────────────────

resource "aws_secretsmanager_secret" "mfa_encryption_key" {
  name                    = "${local.secrets_prefix}/mfa-encryption-key"
  description             = "Fernet key for MFA TOTP encryption"
  recovery_window_in_days = var.environment == "production" ? 30 : 0

  tags = { Name = "${var.project_name}-${var.environment}-mfa-encryption-key" }
}

resource "aws_secretsmanager_secret_version" "mfa_encryption_key" {
  secret_id     = aws_secretsmanager_secret.mfa_encryption_key.id
  secret_string = var.mfa_encryption_key
}

# ── MercadoPago Access Token ─────────────────────────────────────────────────

resource "aws_secretsmanager_secret" "mp_access_token" {
  name                    = "${local.secrets_prefix}/mp-access-token"
  description             = "MercadoPago production access token"
  recovery_window_in_days = var.environment == "production" ? 30 : 0

  tags = { Name = "${var.project_name}-${var.environment}-mp-access-token" }
}

resource "aws_secretsmanager_secret_version" "mp_access_token" {
  secret_id     = aws_secretsmanager_secret.mp_access_token.id
  secret_string = var.mp_access_token
}

# ── MercadoPago Webhook Secret ───────────────────────────────────────────────

resource "aws_secretsmanager_secret" "mp_webhook_secret" {
  name                    = "${local.secrets_prefix}/mp-webhook-secret"
  description             = "MercadoPago webhook signature secret"
  recovery_window_in_days = var.environment == "production" ? 30 : 0

  tags = { Name = "${var.project_name}-${var.environment}-mp-webhook-secret" }
}

resource "aws_secretsmanager_secret_version" "mp_webhook_secret" {
  secret_id     = aws_secretsmanager_secret.mp_webhook_secret.id
  secret_string = var.mp_webhook_secret
}
