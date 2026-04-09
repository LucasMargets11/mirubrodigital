#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# MiRubro — Terraform Backend Bootstrap
# ═══════════════════════════════════════════════════════════════════════════════
#
# Creates the S3 bucket and DynamoDB table that all Terraform states use as
# backend.  Run this ONCE before the first `terraform init` in any layer.
#
# Prerequisites:
#   - AWS CLI v2 installed and configured (aws configure)
#   - IAM permissions: s3:CreateBucket, s3:PutBucketVersioning,
#     s3:PutBucketEncryption, s3:PutPublicAccessBlock, dynamodb:CreateTable
#
# Usage:
#   chmod +x bootstrap.sh
#   ./bootstrap.sh                    # uses defaults
#   AWS_REGION=us-east-1 ./bootstrap.sh
#
# This script is idempotent — safe to run again if resources already exist.
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

BUCKET_NAME="mirubro-terraform-state"
DYNAMO_TABLE="mirubro-tf-locks"
REGION="${AWS_REGION:-us-east-1}"

echo "══════════════════════════════════════════════════════"
echo " MiRubro — Terraform Backend Bootstrap"
echo "══════════════════════════════════════════════════════"
echo ""
echo " Region:         ${REGION}"
echo " S3 Bucket:      ${BUCKET_NAME}"
echo " DynamoDB Table: ${DYNAMO_TABLE}"
echo ""

# ── 1. S3 Bucket ─────────────────────────────────────────────────────────────

echo "→ Creating S3 bucket: ${BUCKET_NAME} ..."

if aws s3api head-bucket --bucket "${BUCKET_NAME}" 2>/dev/null; then
  echo "  Bucket already exists — skipping creation."
else
  # us-east-1 does NOT accept LocationConstraint
  if [ "${REGION}" = "us-east-1" ]; then
    aws s3api create-bucket \
      --bucket "${BUCKET_NAME}" \
      --region "${REGION}"
  else
    aws s3api create-bucket \
      --bucket "${BUCKET_NAME}" \
      --region "${REGION}" \
      --create-bucket-configuration LocationConstraint="${REGION}"
  fi
  echo "  Bucket created."
fi

# Enable versioning (protects against accidental state deletion)
echo "→ Enabling versioning ..."
aws s3api put-bucket-versioning \
  --bucket "${BUCKET_NAME}" \
  --versioning-configuration Status=Enabled

# Enable server-side encryption (AES-256 default)
echo "→ Enabling default encryption ..."
aws s3api put-bucket-encryption \
  --bucket "${BUCKET_NAME}" \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms"
      },
      "BucketKeyEnabled": true
    }]
  }'

# Block ALL public access
echo "→ Blocking public access ..."
aws s3api put-public-access-block \
  --bucket "${BUCKET_NAME}" \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# ── 2. DynamoDB Lock Table ───────────────────────────────────────────────────

echo "→ Creating DynamoDB table: ${DYNAMO_TABLE} ..."

if aws dynamodb describe-table --table-name "${DYNAMO_TABLE}" --region "${REGION}" 2>/dev/null; then
  echo "  Table already exists — skipping creation."
else
  aws dynamodb create-table \
    --table-name "${DYNAMO_TABLE}" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "${REGION}" \
    --tags Key=Project,Value=mirubro Key=ManagedBy,Value=bootstrap

  echo "  Waiting for table to become active ..."
  aws dynamodb wait table-exists --table-name "${DYNAMO_TABLE}" --region "${REGION}"
  echo "  Table ready."
fi

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "══════════════════════════════════════════════════════"
echo " ✅ Bootstrap complete."
echo ""
echo " State keys configured in this project:"
echo "   • core/base/terraform.tfstate"
echo "   • public/dns-certs/terraform.tfstate"
echo "   • public/cdn/terraform.tfstate"
echo "   • private/app-api/terraform.tfstate"
echo ""
echo " Next step: cd into a layer directory and run:"
echo "   terraform init"
echo "══════════════════════════════════════════════════════"
