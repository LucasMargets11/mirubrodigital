# ═══════════════════════════════════════════════════════════════════════════════
# Public DNS & Certificates — MiRubro
# ═══════════════════════════════════════════════════════════════════════════════
#
# State: public/dns-certs/terraform.tfstate
# Region: us-east-1 (all layers share region; cert valid for ALB + CloudFront)
#
# Contains:
#   route53.tf — Hosted zone for mirubro.com + api.mirubro.com A alias → ALB
#   acm.tf     — ACM certificate (mirubro.com + www + api) + DNS validation
#
# Depends on: core/base (alb_dns_name, alb_zone_id)
# Consumed by: public/cdn (acm_certificate_arn, zone_id)
#              core/alb.tf HTTPS listener (acm_certificate_arn)
#
# NOTE: Apply requires two phases — see acm.tf header for the full flow.
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
    key            = "public/dns-certs/terraform.tfstate"
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
      Component   = "public-dns"
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
