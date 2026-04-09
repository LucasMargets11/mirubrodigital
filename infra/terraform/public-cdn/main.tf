# ═══════════════════════════════════════════════════════════════════════════════
# Public CDN & Distribution — MiRubro
# ═══════════════════════════════════════════════════════════════════════════════
#
# State: public/cdn/terraform.tfstate
#
# Contains: S3 assets bucket, CloudFront distribution, WAF (CLOUDFRONT scope),
#           CloudFront Functions, Response Headers Policy.
#
# Depends on:
#   - core/base       (ALB DNS name for origin)
#   - public/dns-certs (ACM cert ARN, Route 53 zone ID)
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
    key            = "public/cdn/terraform.tfstate"
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
      Component   = "public-cdn"
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

# ── Remote State: DNS & Certs ────────────────────────────────────────────────

data "terraform_remote_state" "dns" {
  backend = "s3"

  config = {
    bucket = "mirubro-terraform-state"
    key    = "public/dns-certs/terraform.tfstate"
    region = "us-east-1"
  }
}

# ── Locals ───────────────────────────────────────────────────────────────────

locals {
  core = data.terraform_remote_state.core.outputs
  dns  = data.terraform_remote_state.dns.outputs

  prefix    = "${var.project_name}-${var.environment}"
  fqdn_www  = "${var.canonical_subdomain}.${var.domain_name}" # www.mirubro.com
  fqdn_apex = var.domain_name                                  # mirubro.com
}
