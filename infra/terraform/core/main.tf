# ═══════════════════════════════════════════════════════════════════════════════
# Core Infrastructure — MiRubro
# ═══════════════════════════════════════════════════════════════════════════════
#
# State: core/base/terraform.tfstate
#
# Contains: VPC, subnets, NAT, IGW, security groups, RDS, ElastiCache,
#           KMS, ECR repositories, ECS cluster, ALB, WAF REGIONAL.
#
# Does NOT contain: ECS services/tasks, Secrets Manager values, auto-scaling.
# Those belong in private-app/ layer (private/app-api/terraform.tfstate).
#
# This is the foundation. All other layers depend on outputs from this state.
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
    key            = "core/base/terraform.tfstate"
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
      Component   = "core"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}
