# Admin Login Hardening — AWS Deployment Guide

> Companion to [../ADMIN_LOGIN_HARDENING.md](../ADMIN_LOGIN_HARDENING.md).
> This document covers infrastructure-level setup for deploying the Phase 1.1
> admin auth hardening on AWS.

---

## 1. Recommended AWS Topology

```
                    ┌─────────────┐
                    │   Route 53   │
                    └─────┬───────┘
                          │
                 ┌────────▼────────┐
                 │  CloudFront     │  ← optional, recommended for
                 │  (distribution) │     static caching + geo-restrict
                 └────────┬────────┘
                          │
                 ┌────────▼────────┐
                 │   AWS WAF       │  ← WebACL attached here
                 │   (WebACL)      │     (or directly to ALB if no CF)
                 └────────┬────────┘
                          │
                 ┌────────▼────────┐
                 │   ALB           │  ← TLS termination (ACM cert)
                 │   (public)      │     X-Forwarded-For → client IP
                 └────────┬────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
     ┌────────▼────────┐    ┌────────▼────────┐
     │  ECS / EC2       │    │  ECS / EC2       │
     │  Django (API)    │    │  Next.js (web)   │
     └────────┬────────┘    └─────────────────┘
              │
    ┌─────────┴──────────┐
    │                    │
┌───▼───┐         ┌─────▼──────┐
│  RDS   │         │ ElastiCache │
│ Postgres│         │ Redis/Valkey│
└────────┘         └────────────┘
    │
┌───▼────────────┐
│ Secrets Manager │  ← MFA_ENCRYPTION_KEY
│ (+ KMS)        │     DJANGO_SECRET_KEY
└────────────────┘     DB credentials
```

### CloudFront + ALB vs ALB only

| Factor | ALB only | CloudFront + ALB |
|---|---|---|
| TLS termination | ALB (ACM) | CloudFront edge + ALB |
| WAF attachment | WAF → ALB | WAF → CloudFront |
| Geographic restriction | WAF geo-match rule | CloudFront geo-restrict (built-in) + WAF |
| Static asset caching | N/A | CloudFront cache behaviors |
| DDoS protection | AWS Shield Standard | AWS Shield Standard (enhanced at edge) |
| Latency | Single region | Edge cache reduces latency globally |
| Complexity | Lower | Slightly higher (origin config, cache behaviors) |

**Recommendation**: Start with **ALB only + WAF** for simplicity. Add CloudFront
later if geographic latency, static caching, or enhanced DDoS protection is needed.

---

## 2. AWS WAF Configuration

### 2.1 Create a WebACL

```
Region:       Same as ALB (or Global if attaching to CloudFront)
Resource:     Associate with ALB ARN (or CloudFront distribution)
Default action: Allow
```

### 2.2 Rules (in priority order)

#### Rule 1 — Admin Auth IP Rate Limit (rate-based)

```yaml
Name:         mirubro-admin-auth-rate-limit
Type:         Rate-based
Rate limit:   100 requests per 5-minute window
Aggregate on: Source IP
Scope-down statement:
  ByteMatchStatement:
    FieldToMatch: UriPath
    PositionalConstraint: STARTS_WITH
    SearchString: /api/v1/platform-admin/auth/
    TextTransformation: LOWERCASE
Action:       Block
```

**Why 100/5min**: This is deliberately coarse — it catches automated scanners
and volumetric attacks. The Django application-level limiter (5 attempts per
IP+email in 15 min) handles targeted brute-force.

#### Rule 2 — Admin IP Allowlist (optional, IP-set)

```yaml
# First, create an IP Set:
Name:         mirubro-admin-allowed-ips
Addresses:    [<office-ip>/32, <vpn-cidr>/24, ...]

# Then create two rules in order:
# Rule 2a: ALLOW matching IPs
Name:         mirubro-admin-ip-allow
Type:         Regular
Statement:
  AND:
    - ByteMatchStatement:
        FieldToMatch: UriPath
        PositionalConstraint: STARTS_WITH
        SearchString: /api/v1/platform-admin/
    - IPSetReferenceStatement:
        ARN: <ip-set-arn>
Action:       Allow

# Rule 2b: BLOCK everything else on admin paths
Name:         mirubro-admin-ip-block
Type:         Regular
Statement:
  ByteMatchStatement:
    FieldToMatch: UriPath
    PositionalConstraint: STARTS_WITH
    SearchString: /api/v1/platform-admin/
Action:       Block
```

> If using IP allowlist at WAF, you can leave `ADMIN_IP_ALLOWLIST` empty in Django
> (defense-in-depth: keep both if desired).

#### Rule 3 — Geo-Match Restriction (optional)

```yaml
Name:         mirubro-admin-geo-block
Type:         Regular
Statement:
  AND:
    - ByteMatchStatement:
        FieldToMatch: UriPath
        PositionalConstraint: STARTS_WITH
        SearchString: /api/v1/platform-admin/auth/
    - NOT:
        GeoMatchStatement:
          CountryCodes: [AR, UY]  # adjust to team locations
Action:       Block
```

#### Rule 4 — Bot Control (optional, managed rule group)

```yaml
Name:         mirubro-admin-bot-control
Type:         Managed rule group
Rule group:   AWSManagedRulesBotControlRuleSet
Inspection level: TARGETED (lower cost) or COMMON
Scope-down:
  ByteMatchStatement:
    FieldToMatch: UriPath
    PositionalConstraint: STARTS_WITH
    SearchString: /api/v1/platform-admin/
Override action: None (use rule group defaults)
```

> Cost note: Bot Control is charged per request inspected. Scope it down to
> `/platform-admin/` only to minimize costs.

### 2.3 WAF Logging

WAF supports three logging destinations. Choose based on retention needs:

| Destination | Use case | Notes |
|---|---|---|
| **CloudWatch Logs** | Real-time alerting, short-term investigation | Log group must start with `aws-waf-logs-`. Set retention ≥ 90 days. |
| **S3 bucket** | Long-term archival, compliance | Bucket name must start with `aws-waf-logs-`. Use lifecycle rules for Glacier transition. |
| **Kinesis Data Firehose** | Streaming to SIEM (Splunk, Datadog, etc.) | Delivery stream name must start with `aws-waf-logs-`. |

**Recommended setup:**

```
1. Primary:   CloudWatch Logs → aws-waf-logs-mirubro-admin
               Filter: BLOCK and COUNT actions only
               Retention: 90 days

2. Archival:  S3 → aws-waf-logs-mirubro-admin-archive
               Lifecycle: Standard 30d → IA 90d → Glacier 365d
```

Metric filters on CloudWatch Logs can trigger alarms for spikes in blocked
requests against `/api/v1/platform-admin/auth/*`.

---

## 3. ALB Configuration

### 3.1 Listeners

```
HTTPS:443  → Target Group (Django API on port 8000)
             Certificate: ACM certificate for api.mirubro.com
             Security Policy: ELBSecurityPolicy-TLS13-1-2-2021-06
```

### 3.2 X-Forwarded-For

Each trusted proxy **appends** the connecting client's IP to `X-Forwarded-For`.
A malicious client can prepend arbitrary values, so Django counts from the
**right** (not the left) by `TRUSTED_PROXY_DEPTH` positions.

**ALB only (`TRUSTED_PROXY_DEPTH=1`)**
```
X-Forwarded-For: <spoofed>, <real-client-ip>
                                    ▲
                                 xff[-1]   ← ALB appended
```

**CloudFront + ALB (`TRUSTED_PROXY_DEPTH=2`)**
```
X-Forwarded-For: <spoofed>, <real-client-ip>, <cloudfront-edge-ip>
                                 ▲                     ▲
                              xff[-2]               xff[-1]
                          CF appended            ALB appended
```

Set in Django:
```
TRUSTED_PROXY_DEPTH=1   # ALB only   → xff[-1]
TRUSTED_PROXY_DEPTH=2   # CloudFront + ALB → xff[-2]
```

> **Never trust `xff[0]`** (the leftmost entry). It is fully client-controlled
> and can be set to any value by the requester.

### 3.3 SECURE_PROXY_SSL_HEADER

ALB sets `X-Forwarded-Proto: https` on HTTPS listeners. Django uses:
```python
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
```
This is auto-enabled when `DEBUG=False` (see settings.py).

---

## 4. Amazon ElastiCache (Redis / Valkey)

### 4.1 Cluster Setup

```
Engine:           Redis 7.x or Valkey 7.2+
Node type:        cache.t4g.micro (start small, scale as needed)
Cluster mode:     Disabled (single-node is sufficient for admin auth)
Encryption:
  - At-rest:      Enabled (uses default AWS KMS key)
  - In-transit:   Enabled (TLS required)
Auth:             AUTH token enabled (Redis password)
VPC:              Same VPC as ECS tasks
Security group:   Allow inbound 6379 from ECS security group only
```

### 4.2 Django Configuration

```bash
# Environment variable in ECS task definition
CACHE_REDIS_URL=rediss://:AUTH_TOKEN@my-cluster.xxxxx.use1.cache.amazonaws.com:6379/0
```

Notes:
- Use `rediss://` (double-s) for TLS connections to ElastiCache.
- The AUTH token can also be stored in Secrets Manager and injected at container startup.
- Database number (`/0`) is fine — ElastiCache single-node supports multiple databases.
  Unlike local Docker setup, there's no need to avoid db1 or any specific database.

### 4.3 What lives in ElastiCache

| Key pattern | TTL | Purpose |
|---|---|---|
| `mirubro:admin_rl:ip:<ip>` | 10 min | IP-level login attempt counter |
| `mirubro:admin_rl:em:<hash>` | 30 min | Email-level login attempt counter |
| `mirubro:admin_rl:ie:<ip>:<hash>` | 15 min | IP+email login attempt counter |
| `mirubro:admin_rl:*:cd` | varies | Cooldown markers |
| `mirubro:mfa_challenge:<token>` | 5 min | MFA challenge tokens (single-use) |
| `mirubro:mfa_used:<user>:<otp>` | ~90 sec | OTP anti-replay markers |
| `mirubro:mfa_attempts:<user>` | 15 min | OTP attempt counter |

All keys are prefixed with `mirubro:` (Django `KEY_PREFIX`). Total key count
for admin auth is very low (< 100 even under attack).

### 4.4 Failover Considerations

If ElastiCache is temporarily unavailable:
- Rate limiting degrades gracefully — `django.core.cache` operations return
  `None`/raise `ValueError` which the rate limiter handles by allowing the
  request (fail-open). AWS WAF provides the perimeter defense in this case.
- MFA challenge tokens cannot be created/verified — admin login fails with
  a server error. This is acceptable (fail-closed for MFA).

---

## 5. AWS Secrets Manager

### 5.1 Secrets to Store

| Secret name | Value | Rotation |
|---|---|---|
| `mirubro/prod/mfa-encryption-key` | Fernet key (44-char base64) | Manual (rotate requires re-encrypting all TOTP secrets) |
| `mirubro/prod/django-secret-key` | Django SECRET_KEY | Yearly |
| `mirubro/prod/db-credentials` | RDS username + password | Auto-rotate via Secrets Manager |
| `mirubro/prod/elasticache-auth` | Redis AUTH token | Manual or via rotation Lambda |

### 5.2 Generating the MFA Encryption Key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store the output in Secrets Manager:
```bash
aws secretsmanager create-secret \
  --name mirubro/prod/mfa-encryption-key \
  --secret-string "$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  --kms-key-id alias/mirubro-secrets \
  --description "Fernet key for admin MFA TOTP secret encryption"
```

### 5.3 Injecting Secrets into ECS

**Option A: ECS native secrets (recommended)**

In the ECS task definition:
```json
{
  "containerDefinitions": [{
    "secrets": [
      {
        "name": "MFA_ENCRYPTION_KEY",
        "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789:secret:mirubro/prod/mfa-encryption-key"
      },
      {
        "name": "DJANGO_SECRET_KEY",
        "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789:secret:mirubro/prod/django-secret-key"
      }
    ]
  }]
}
```

The ECS agent resolves the secret and injects it as an environment variable.
The task execution role needs `secretsmanager:GetSecretValue` permission.

**Option B: Startup script**

In the container entrypoint:
```bash
export MFA_ENCRYPTION_KEY=$(aws secretsmanager get-secret-value \
  --secret-id mirubro/prod/mfa-encryption-key \
  --query SecretString --output text)
exec python manage.py runserver 0.0.0.0:8000
```

**Option A is preferred** — no SDK calls at startup, no IAM instance credentials needed
in the container, and secrets are never written to disk.

### 5.4 KMS Integration

- Create a Customer Managed Key (CMK): `alias/mirubro-secrets`
- Use it as the encryption key for all Secrets Manager secrets
- Grant `kms:Decrypt` to the ECS task execution role
- Enables CloudTrail logging of every secret access

```bash
aws kms create-key --description "Mi Rubro secrets encryption"
aws kms create-alias --alias-name alias/mirubro-secrets --target-key-id <key-id>
```

### 5.5 MFA Key Rotation Procedure

Rotating `MFA_ENCRYPTION_KEY` requires re-encrypting all stored TOTP secrets:

1. Generate new Fernet key
2. Deploy with **both** keys temporarily (old + new)
3. Run management command to re-encrypt all `AccountProfile.mfa_secret_encrypted`
4. Remove old key
5. Update Secrets Manager with new key only

> This is a rare operation. In most cases, the initial key is never rotated
> unless a compromise is suspected.

---

## 6. Monitoring & Alerting

### 6.1 CloudWatch Alarms

| Alarm | Metric | Threshold | Action |
|---|---|---|---|
| Admin login rate spike | WAF `BlockedRequests` on admin auth rule | > 50 in 5 min | SNS → Slack/email |
| ElastiCache CPU | `EngineCPUUtilization` | > 80% for 5 min | SNS alert |
| ElastiCache evictions | `Evictions` | > 0 | SNS alert (may indicate memory pressure) |
| Django 5xx on admin auth | ALB `HTTPCode_Target_5XX_Count` | > 5 in 5 min | SNS alert |

### 6.2 Application-Level Audit

All admin auth events are written to `AccessAuditLog` in PostgreSQL.
Query for suspicious patterns:

```sql
-- Failed logins in the last hour
SELECT ip_address, COUNT(*) as attempts, MAX(created_at) as last_attempt
FROM accounts_accessauditlog
WHERE action IN ('ADMIN_LOGIN_FAILED', 'ADMIN_LOGIN_THROTTLED', 'ADMIN_LOGIN_COOLDOWN')
  AND created_at > NOW() - INTERVAL '1 hour'
GROUP BY ip_address
ORDER BY attempts DESC;

-- MFA failures
SELECT actor_id, ip_address, COUNT(*) as failures
FROM accounts_accessauditlog
WHERE action = 'ADMIN_MFA_FAILED'
  AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY actor_id, ip_address
ORDER BY failures DESC;
```

### 6.3 WAF Logs

WAF logs go to CloudWatch Logs group `aws-waf-logs-mirubro-admin`.
Create a CloudWatch Insights query for blocked admin requests:

```
fields @timestamp, httpRequest.clientIp, httpRequest.uri, action
| filter action = "BLOCK"
| filter httpRequest.uri like /platform-admin/
| stats count(*) as blocked by httpRequest.clientIp
| sort blocked desc
| limit 20
```

---

## 7. Security Group Configuration

```
ECS Security Group (api):
  Inbound:   TCP 8000 from ALB security group
  Outbound:  TCP 5432 to RDS security group
             TCP 6379 to ElastiCache security group
             TCP 443  to 0.0.0.0/0 (Secrets Manager, external APIs)

ALB Security Group:
  Inbound:   TCP 443 from 0.0.0.0/0 (or CloudFront prefix list)
  Outbound:  TCP 8000 to ECS security group

ElastiCache Security Group:
  Inbound:   TCP 6379 from ECS security group
  Outbound:  None required

RDS Security Group:
  Inbound:   TCP 5432 from ECS security group
  Outbound:  None required
```

---

## 8. AWS Deployment Checklist

### Pre-deployment

- [ ] Create KMS CMK `alias/mirubro-secrets`
- [ ] Store `MFA_ENCRYPTION_KEY` in Secrets Manager (encrypted with CMK)
- [ ] Store `DJANGO_SECRET_KEY` in Secrets Manager
- [ ] Provision ElastiCache Redis cluster (TLS + AUTH enabled)
- [ ] Store ElastiCache AUTH token in Secrets Manager
- [ ] Create ECS task execution role with `secretsmanager:GetSecretValue` + `kms:Decrypt`

### Infrastructure

- [ ] Create ALB with HTTPS listener (ACM certificate)
- [ ] Create AWS WAF WebACL with rules 1-4 (see section 2)
- [ ] Attach WebACL to ALB (or CloudFront)
- [ ] Enable WAF logging to CloudWatch Logs
- [ ] Configure security groups (section 7)

### Application

- [ ] Set environment variables in ECS task definition:
  - `CACHE_REDIS_URL` → ElastiCache endpoint (rediss://)
  - `CELERY_BROKER_URL` → ElastiCache endpoint (rediss://)
  - `TRUSTED_PROXY_DEPTH` → `1` (ALB) or `2` (CloudFront+ALB)
  - `DEBUG` → `False`
  - `MFA_BOOTSTRAP_ENABLED` → `true` (for initial setup)
- [ ] Configure secrets in ECS task definition:
  - `MFA_ENCRYPTION_KEY` → Secrets Manager ARN
  - `DJANGO_SECRET_KEY` → Secrets Manager ARN
- [ ] Run `python manage.py migrate accounts 0018`
- [ ] Verify admin login page loads at `/admin/login`
- [ ] Superadmin completes MFA enrollment
- [ ] Set `MFA_BOOTSTRAP_ENABLED` → `false`

### Post-deployment

- [ ] Create CloudWatch alarms (section 6.1)
- [ ] Verify WAF is logging blocked requests
- [ ] Run end-to-end test: login → MFA → dashboard → logout
- [ ] Verify rate limiting: 6+ rapid login attempts should be blocked
- [ ] Verify audit logs: check `AccessAuditLog` table for events
- [ ] Schedule periodic review of WAF blocked requests (weekly)
