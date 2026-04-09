terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state — adjust bucket/key for your account
  backend "s3" {
    bucket         = "mirubro-terraform-state"
    key            = "security/admin-hardening/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "mirubro-tf-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "mirubro"
      Component   = "admin-hardening"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}
