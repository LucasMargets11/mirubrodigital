# Bootstrap — Terraform Backend Resources

One-time script to create the S3 bucket and DynamoDB table used by all
Terraform state files in this project.

## Prerequisites

- AWS CLI v2 configured with credentials that can create S3 buckets and
  DynamoDB tables.
- Bash shell (WSL, Git Bash, or Linux/macOS).

## Usage

```bash
cd infra/terraform/bootstrap
chmod +x bootstrap.sh
./bootstrap.sh
```

The script is idempotent — re-running it when resources already exist is safe.

## What it creates

| Resource | Name | Purpose |
|---|---|---|
| S3 Bucket | `mirubro-terraform-state` | Stores all `.tfstate` files (versioned, encrypted, public access blocked) |
| DynamoDB Table | `mirubro-tf-locks` | Prevents concurrent `terraform apply` (PAY_PER_REQUEST) |

## State keys

After bootstrap, each layer initialises its own state key:

| Layer | State key | Directory |
|---|---|---|
| Core infrastructure | `core/base/terraform.tfstate` | `../core/` |
| DNS & certificates | `public/dns-certs/terraform.tfstate` | `../public-dns/` |
| CDN & distribution | `public/cdn/terraform.tfstate` | `../public-cdn/` |
| Application services | `private/app-api/terraform.tfstate` | `../private-app/` |
