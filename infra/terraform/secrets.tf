# ═══════════════════════════════════════════════════════════════════════════════
# AWS Secrets Manager + KMS — MFA Encryption Key & Sensitive Settings
# ═══════════════════════════════════════════════════════════════════════════════

# ── KMS key for encrypting the secrets ───────────────────────────────────────

resource "aws_kms_key" "secrets" {
  description             = "KMS key for ${var.project_name} Secrets Manager"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${var.project_name}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}

# ── MFA Encryption Key secret ───────────────────────────────────────────────

resource "aws_secretsmanager_secret" "mfa_key" {
  name        = "${var.project_name}/${var.environment}/mfa-encryption-key"
  description = "Fernet key for TOTP MFA secret encryption"
  kms_key_id  = aws_kms_key.secrets.arn

  recovery_window_in_days = 30
}

resource "aws_secretsmanager_secret_version" "mfa_key" {
  secret_id     = aws_secretsmanager_secret.mfa_key.id
  secret_string = var.mfa_encryption_key
}

# ── Django SECRET_KEY ────────────────────────────────────────────────────────

resource "aws_secretsmanager_secret" "django_secret_key" {
  name        = "${var.project_name}/${var.environment}/django-secret-key"
  description = "Django SECRET_KEY"
  kms_key_id  = aws_kms_key.secrets.arn

  recovery_window_in_days = 30
}

# ── Database credentials ─────────────────────────────────────────────────────

resource "aws_secretsmanager_secret" "db_credentials" {
  name        = "${var.project_name}/${var.environment}/db-credentials"
  description = "PostgreSQL connection credentials"
  kms_key_id  = aws_kms_key.secrets.arn

  recovery_window_in_days = 30
}

# ── IAM policy for ECS task execution role to read secrets ───────────────────

data "aws_iam_policy_document" "secrets_read" {
  statement {
    sid    = "ReadSecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
    ]
    resources = [
      aws_secretsmanager_secret.mfa_key.arn,
      aws_secretsmanager_secret.django_secret_key.arn,
      aws_secretsmanager_secret.db_credentials.arn,
    ]
  }

  statement {
    sid    = "DecryptWithKMS"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
    ]
    resources = [
      aws_kms_key.secrets.arn,
    ]
  }
}

resource "aws_iam_policy" "secrets_read" {
  name   = "${var.project_name}-${var.environment}-secrets-read"
  policy = data.aws_iam_policy_document.secrets_read.json
}

# Attach to ECS task execution role (if provided)
resource "aws_iam_role_policy_attachment" "ecs_secrets" {
  count      = var.ecs_task_execution_role_arn != "" ? 1 : 0
  role       = split("/", var.ecs_task_execution_role_arn)[1]
  policy_arn = aws_iam_policy.secrets_read.arn
}
