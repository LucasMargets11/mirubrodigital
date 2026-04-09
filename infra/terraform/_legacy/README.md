# Admin Hardening — Terraform Infrastructure

Provisions the AWS resources required by Phase 1.1 admin login hardening:

| Resource | File | Purpose |
|---|---|---|
| **AWS WAF** | `waf.tf` | WebACL with admin rate limiting, managed rules, CloudWatch logging |
| **ElastiCache** | `elasticache.tf` | Redis 7.x cluster for rate-limit counters, MFA tokens, Celery broker |
| **Secrets Manager + KMS** | `secrets.tf` | MFA_ENCRYPTION_KEY, Django SECRET_KEY, DB creds — KMS-encrypted |

## Prerequisites

- Terraform >= 1.5
- AWS CLI configured with appropriate credentials
- Existing ALB, VPC, subnets, and ECS task execution role

## Usage

```bash
cd infra/terraform

# 1. Copy and fill variables
cp production.tfvars.example production.tfvars
# Edit production.tfvars with real values

# 2. Initialize
terraform init

# 3. Plan
terraform plan -var-file=production.tfvars

# 4. Apply
terraform apply -var-file=production.tfvars
```

## Outputs → Django env vars

After `terraform apply`, wire outputs into your ECS task definition:

| Terraform output | Django env var | Notes |
|---|---|---|
| `elasticache_endpoint` | `CACHE_REDIS_URL` | `rediss://...` (TLS) |
| `celery_broker_url` | `CELERY_BROKER_URL` | Same cluster, db 0 |
| `mfa_key_secret_arn` | `MFA_ENCRYPTION_KEY` | Use ECS `valueFrom` to inject |
| `django_secret_key_arn` | `SECRET_KEY` | Use ECS `valueFrom` to inject |
| `db_credentials_secret_arn` | `DATABASE_URL` | Parse JSON in entrypoint or use `valueFrom` |

## Post-deploy checklist

```
1. terraform apply -var-file=production.tfvars
2. Verify WAF attached:  aws wafv2 get-web-acl-for-resource --resource-arn <ALB_ARN>
3. Verify ElastiCache:   redis-cli -h <endpoint> --tls ping
4. Verify secrets:       aws secretsmanager get-secret-value --secret-id mirubro/production/mfa-encryption-key
5. Deploy API with new env vars
6. Run migrations:       python manage.py migrate
7. First admin enrolls MFA via bootstrap
8. Check enrollment:     python manage.py check_mfa_bootstrap
9. Set MFA_BOOTSTRAP_ENABLED=false when all admins enrolled
```
