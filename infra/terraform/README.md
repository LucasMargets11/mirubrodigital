# MiRubro — Terraform Infrastructure

Multi-state Terraform setup for MiRubro's AWS infrastructure. Each layer has
its own state file, variables, and outputs, connected via `terraform_remote_state`.

## Architecture

```
                       ┌─────────────────────────────────┐
                       │  public/cdn                     │
                       │  CloudFront · S3 · WAF(CF)      │
                       │  State: public/cdn/...          │
                       └──────────┬──────────────────────┘
                                  │ depends on
                       ┌──────────▼──────────────────────┐
                       │  public/dns-certs               │
                       │  Route 53 · ACM                 │
                       │  State: public/dns-certs/...    │
                       └──────────┬──────────────────────┘
                                  │ depends on
            ┌─────────────────────┴──────────────────────┐
            │                                            │
  ┌─────────▼───────────────────┐   ┌────────────────────▼───┐
  │  private/app-api            │   │  core/base             │
  │  ECS services · tasks ·    │   │  VPC · ECS cluster ·   │
  │  secrets · auto-scaling    │   │  ALB · RDS · Redis ·   │
  │  State: private/app-api/.. │   │  ECR · SGs · IAM       │
  └─────────────┬───────────────┘   │  State: core/base/...  │
                │ depends on        └────────────────────────┘
                └──────────────────────────┘
                                  │ stored in
                       ┌──────────▼──────────────────────┐
                       │  bootstrap                      │
                       │  S3 bucket + DynamoDB locks     │
                       │  (one-time script, not TF)      │
                       └─────────────────────────────────┘
```

## Directory structure

```
infra/terraform/
├── bootstrap/           One-time: S3 state bucket + DynamoDB locks
│   ├── bootstrap.sh
│   └── README.md
├── core/                State: core/base/terraform.tfstate
│   ├── main.tf          Terraform block, provider, backend config
│   ├── vpc.tf           VPC, subnets, IGW, NAT, route tables
│   ├── security-groups.tf  ALB, ECS, RDS, Redis security groups
│   ├── rds.tf           PostgreSQL 16, subnet group, parameter group
│   ├── elasticache.tf   Redis 7.1, replication group, subnet group
│   ├── ecr.tf           Container registries (4 repos), lifecycle policies
│   ├── ecs.tf           ECS cluster, IAM execution + task roles
│   ├── alb.tf           ALB, target groups (api/web), HTTP listener
│   ├── variables.tf
│   ├── outputs.tf       26 outputs consumed by other layers
│   └── terraform.tfvars.example
├── private-app/         State: private/app-api/terraform.tfstate
│   ├── main.tf          Terraform block, provider, remote state ref
│   ├── secrets.tf       Secrets Manager (5 secrets)
│   ├── logs.tf          CloudWatch log groups (4 services)
│   ├── task-definitions.tf  ECS task definitions (api, web, celery-worker, celery-beat)
│   ├── services.tf      ECS services with ALB integration
│   ├── autoscaling.tf   Auto scaling for api and web
│   ├── variables.tf
│   ├── outputs.tf       21 outputs for CI/CD and monitoring
│   └── terraform.tfvars.example
├── public-dns/          State: public/dns-certs/terraform.tfstate
│   ├── main.tf          Terraform block, provider, remote state ref
│   ├── route53.tf       Hosted zone + api.mirubro.com A alias → ALB
│   ├── acm.tf           ACM certificate (apex + www + api) + DNS validation
│   ├── variables.tf
│   ├── outputs.tf       5 outputs (zone_id, NS, cert ARN, cert status, api FQDN)
│   └── terraform.tfvars.example
├── public-cdn/          State: public/cdn/terraform.tfstate
│   ├── main.tf          CloudFront, S3 assets, WAF CLOUDFRONT
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
└── _legacy/             Original admin-hardening TF (reference only)
```

## State keys

All states use the same S3 backend bucket (`mirubro-terraform-state`) and
DynamoDB lock table (`mirubro-tf-locks`).

| Layer | State key | Resources |
|---|---|---|
| Core | `core/base/terraform.tfstate` | VPC, subnets, NAT, IGW, SGs, RDS PostgreSQL 16, ElastiCache Redis 7.1, ECR (4 repos), ECS cluster, IAM roles, ALB, target groups |
| App | `private/app-api/terraform.tfstate` | Secrets Manager (5), CloudWatch log groups (4), ECS task defs (4), ECS services (4), auto-scaling (api/web) |
| DNS | `public/dns-certs/terraform.tfstate` | Route 53 hosted zone, ACM certificate (3 SANs), DNS validation records, api.mirubro.com A alias |
| CDN | `public/cdn/terraform.tfstate` | CloudFront, S3 assets, WAF CLOUDFRONT |

---

## Deployment order

> **Order rationale**: deploy services before DNS so the app can be validated
> via the ALB's temporary DNS name (`*.elb.amazonaws.com`) over HTTP. This way
> nameserver migration in Hostinger — the most visible and hardest-to-rollback
> step — only happens after the full stack is confirmed healthy. ACM validation
> can also take minutes; decoupling it from the app deploy avoids blocking the
> rollout on DNS propagation.

### Step 0: Bootstrap (once, ever)

```bash
cd infra/terraform/bootstrap
chmod +x bootstrap.sh
./bootstrap.sh
```

Creates the S3 bucket and DynamoDB table. Idempotent — safe to re-run.

### Step 1: Core infrastructure

```bash
cd infra/terraform/core
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — set db_password to a strong value
terraform init
terraform plan
terraform apply
```

**Before applying**: review the plan for expected resource count (~25 resources: VPC, 4 subnets, IGW, NAT, EIP, 2 route tables, 4 SGs, RDS, ElastiCache, 4 ECR repos, ECS cluster, 2 IAM roles, ALB, 2 target groups, HTTP listener).

### Step 2: Application services

```bash
cd infra/terraform/private-app
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars (container images, all 5 secrets)
terraform init
terraform plan
terraform apply
```

**Prerequisite**: Push Docker images to ECR repos created in Step 1, then set `api_image` and `web_image` in tfvars. Set all 5 secrets (`django_secret_key`, `db_password`, `mfa_encryption_key`, `mp_access_token`, `mp_webhook_secret`).

### Step 2.5: Validate via ALB (manual)

Before touching DNS, confirm the stack works through the ALB's temporary name:

```bash
# Get the ALB DNS from core outputs
cd infra/terraform/core
ALB_DNS=$(terraform output -raw alb_dns_name)

# Health checks
curl -f http://$ALB_DNS/api/v1/health/   # → Django API
curl -f http://$ALB_DNS/api/health        # → Next.js Web

# Smoke test
curl -s http://$ALB_DNS/ | head -20       # → Web home page
```

**Do not proceed to Step 3 until both health checks return 200.**

### Step 3: DNS & certificates

```bash
cd infra/terraform/public-dns
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
# → Update nameservers in Hostinger to the output NS records
# → Wait for ACM certificate DNS validation to complete
#   (aws acm describe-certificate --certificate-arn <ARN> --query 'Certificate.Status')
```

**After nameservers propagate** (~15 min to 48 h): uncomment the HTTPS listener in `core/alb.tf`, pass the ACM cert ARN, and re-apply core.

### Step 4: CDN & distribution (last)

```bash
cd infra/terraform/public-cdn
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

---

## Pre-apply checklist (core/base)

Before running `terraform apply` on core:

1. **Bootstrap completed** — S3 bucket and DynamoDB table exist
2. **AWS credentials configured** — `aws sts get-caller-identity` succeeds
3. **`terraform.tfvars` created** — copied from example, `db_password` set
4. **`terraform init` succeeds** — backend accessible, providers downloaded
5. **`terraform plan` reviewed** — ~25 resources, no surprises
6. **No manual AWS resources** — start from a clean account/VPC

## What core/base does NOT contain

These responsibilities belong to other layers:

| Thing | Layer | Why |
|---|---|---|
| ECS task definitions | `private-app` | Changes every deploy (image tag) |
| ECS services | `private-app` | Coupled to task definitions |
| Secrets Manager values | `private-app` | App-specific secrets |
| CloudWatch log groups | `private-app` | Scoped to services |
| Auto-scaling policies | `private-app` | Scoped to services |
| Route 53 zone | `public-dns` | DNS is a separate concern |
| ACM certificates | `public-dns` | Requires DNS validation |
| HTTPS listener | `core` (commented) | Uncomment after ACM cert exists |
| CloudFront distribution | `public-cdn` | Last layer, depends on DNS + core |

## Cross-state dependencies

Layers consume outputs from `core/base` via `terraform_remote_state`:

| Consumer | Outputs consumed from core |
|---|---|
| **private-app** | `ecs_cluster_id`, `ecs_task_execution_role_arn`, `ecs_task_role_arn`, `ecs_security_group_id`, `private_subnet_ids`, `alb_target_group_api_arn`, `alb_target_group_web_arn`, `ecr_repository_urls`, `rds_endpoint`, `elasticache_redis_url` |
| **public-dns** | `alb_dns_name`, `alb_zone_id` |
| **public-cdn** | `alb_dns_name` (via dns layer), `zone_id`, `acm_certificate_arn` (from dns layer) |

## Legacy files

The `_legacy/` directory contains the original Terraform files for
admin-hardening (WAF, ElastiCache, Secrets). These resources are now
implemented in `core/` and `private-app/`. Legacy files are kept for
reference only and will be removed after migration is verified.

## Security notes

- **Never commit `terraform.tfvars`** — it contains secrets (DB passwords, encryption keys)
- All `.tfvars` files are in `.gitignore`
- State is encrypted at rest (S3 SSE-KMS)
- State locking via DynamoDB prevents concurrent applies
- Security groups follow least-privilege: Internet → ALB → ECS → (RDS | Redis)
- RDS and Redis have no outbound egress (they don't initiate connections)
- RDS storage is encrypted (AES-256)
- ElastiCache has transit encryption (TLS) and at-rest encryption
- ECR images are scanned on push
- Secrets are stored in AWS Secrets Manager, injected into ECS tasks via `valueFrom`
