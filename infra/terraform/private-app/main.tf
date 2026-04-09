# ═══════════════════════════════════════════════════════════════════════════════
# Private Application Layer — MiRubro
# ═══════════════════════════════════════════════════════════════════════════════
#
# State: private/app-api/terraform.tfstate
#
# Contains:
#   secrets.tf          — Secrets Manager (django key, db password, mfa, mp)
#   logs.tf             — CloudWatch log groups (4 services)
#   task-definitions.tf — ECS task definitions (api, web, celery-worker, celery-beat)
#   services.tf         — ECS services with ALB integration
#   autoscaling.tf      — Auto scaling for api and web
#
# Depends on: core/base (VPC, subnets, SGs, ALB, ECS cluster, ECR, RDS, Redis)
#
# This layer changes frequently (every deploy updates task definitions).
# Core infrastructure in core/base is stable and rarely touched.
# ═══════════════════════════════════════════════════════════════════════════════

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "mirubro-terraform-state"
    key            = "private/app-api/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "mirubro-tf-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Component   = "private-app"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}

# ── Remote State: Core ───────────────────────────────────────────────────────

data "terraform_remote_state" "core" {
  backend = "s3"

  config = {
    bucket = "mirubro-terraform-state"
    key    = "core/base/terraform.tfstate"
    region = "us-east-1"
  }
}
