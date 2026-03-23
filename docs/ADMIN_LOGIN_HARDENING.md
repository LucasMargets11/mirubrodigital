# Admin Login Hardening — Phase 1.1

## Overview

This document describes the defense-in-depth architecture for the Mi Rubro
internal admin panel (`/admin`). It covers the application-level controls
implemented in Phase 1.1 and the recommended AWS infrastructure layers.

For the detailed AWS deployment guide, see
[security/admin-login-hardening-aws.md](security/admin-login-hardening-aws.md).

---

## Architecture Layers

```
┌──────────────────────────────────────────────────────────┐
│  Layer 0 — Edge / CDN  (CloudFront — optional)           │
│  • TLS termination                                       │
│  • Geographic restrictions via CloudFront geo-restrict   │
│  • AWS WAF WebACL attached here OR at ALB                │
├──────────────────────────────────────────────────────────┤
│  Layer 1 — AWS WAF  (attached to ALB or CloudFront)      │
│  • Rate-based rule: 100 req / 5 min per IP on auth/*     │
│  • IP-set rule: allowlist for /platform-admin/ (optional)│
│  • AWS Bot Control managed rule group (optional)         │
│  • Geo-match rule to block unexpected countries           │
│  • Logs to CloudWatch Logs / S3 for monitoring           │
├──────────────────────────────────────────────────────────┤
│  Layer 2 — Application Load Balancer (ALB)               │
│  • TLS termination (ACM certificate)                     │
│  • X-Forwarded-For with real client IP                   │
│  • Target group → ECS tasks / EC2 instances              │
├──────────────────────────────────────────────────────────┤
│  Layer 3 — Django Application                            │
│  • IP allowlist (ADMIN_IP_ALLOWLIST)                     │
│  • DRF ScopedRateThrottle (admin_auth: 30/min)           │
│  • Cache-based rate limiter (IP, email, IP+email)        │
│  • Anti-enumeration (generic errors + artificial delay)  │
│  • Two-step auth: password → MFA challenge → OTP verify  │
│  • TOTP MFA with Fernet-encrypted secrets at rest        │
│  • Recovery codes (SHA-256 hashed, single-use)           │
│  • OTP anti-replay (cache-based)                         │
│  • Comprehensive audit logging                           │
├──────────────────────────────────────────────────────────┤
│  Layer 4 — Session / Cookie                              │
│  • JWT cookies: httpOnly, Secure, SameSite=Lax           │
│  • Admin access token: 15 min, refresh: 4 hours          │
│  • HSTS 1 year + includeSubDomains + preload             │
│  • X-Frame-Options: DENY                                 │
│  • Content-Type nosniff                                  │
├──────────────────────────────────────────────────────────┤
│  Layer 5 — Data (RDS + ElastiCache + Secrets Manager)    │
│  • MFA secrets encrypted (Fernet/AES-128-CBC)            │
│  • MFA_ENCRYPTION_KEY in AWS Secrets Manager              │
│  • Recovery codes SHA-256 hashed                         │
│  • Rate-limit counters in ElastiCache Redis with TTL     │
│  • MFA challenge tokens in ElastiCache (5 min, 1-use)    │
└──────────────────────────────────────────────────────────┘
```

---

## AWS WAF Rules (Recommended)

Attach a WebACL to the ALB (or to CloudFront if using it).

### Rule 1: Admin Auth Rate Limit (rate-based)
- **Scope-down**: URI path starts with `/api/v1/platform-admin/auth/`
- **Rate limit**: 100 requests per 5-minute window per IP
- **Action**: Block
- **Why**: Blocks volumetric brute-force before it reaches Django.
  Application-level rate limiter handles per-email/per-account scenarios.

### Rule 2: Admin IP Allowlist (optional, IP-set)
- **Scope-down**: URI path starts with `/api/v1/platform-admin/`
- **IP Set**: Create an AWS WAF IP Set with admin team IPs/CIDRs
- **Action**: Allow matching IPs, Block the rest (priority order)
- **Why**: Restricts admin panel to known IPs at the edge.

### Rule 3: Geo-Match Restriction (optional)
- **Scope-down**: URI path starts with `/api/v1/platform-admin/auth/`
- **Country codes NOT IN**: `[AR, UY]` (adjust to team locations)
- **Action**: Block
- **Why**: Eliminates traffic from unexpected geographies.

### Rule 4: Bot Control (optional, managed rule group)
- **Rule group**: `AWSManagedRulesBotControlRuleSet`
- **Scope-down**: URI path starts with `/api/v1/platform-admin/`
- **Action**: Block for verified bots (targeted protection level)

> **Note on WAF vs App rate limiting**: AWS WAF rate-based rules operate
> on IP only. Per-email and per-IP+email rate limiting is handled at the
> application layer (Django cache-based limiter), which is the only layer
> that can inspect request body content.

---

## Reverse Proxy (Optional — Nginx)

If running Nginx between ALB and Django (e.g., as a sidecar container),
add supplementary rate limiting:

```nginx
limit_req_zone $binary_remote_addr zone=admin_auth_ip:10m rate=10r/m;
limit_conn_zone $binary_remote_addr zone=admin_conn:5m;

location /api/v1/platform-admin/auth/ {
    limit_req zone=admin_auth_ip burst=5 nodelay;
    limit_conn admin_conn 3;
    limit_req_status 429;
    limit_conn_status 429;

    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

> **When Nginx is NOT used** (ALB → Django directly), the rate limiting
> stack is: AWS WAF (IP) → DRF ScopedRateThrottle → application cache limiter.
> This is sufficient for most deployments.

---

## Environment Variables Reference

### Cache (ElastiCache)

| Variable | Default | Description |
|---|---|---|
| `CACHE_REDIS_URL` | `redis://redis:6379/1` | Redis/Valkey URL for Django cache. For ElastiCache with TLS: `rediss://my-cluster.xxxxx.cache.amazonaws.com:6379/0` |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Redis URL for Celery broker (can be same ElastiCache or separate) |

### Rate Limiting

| Variable | Default | Description |
|---|---|---|
| `ADMIN_LOGIN_IP_EMAIL_MAX_ATTEMPTS` | `5` | Max attempts per IP+email combo |
| `ADMIN_LOGIN_IP_EMAIL_WINDOW_SECONDS` | `900` | Window for IP+email counter (15 min) |
| `ADMIN_LOGIN_IP_EMAIL_COOLDOWN_SECONDS` | `900` | Cooldown after IP+email limit hit |
| `ADMIN_LOGIN_EMAIL_MAX_ATTEMPTS` | `10` | Max attempts per email (all IPs) |
| `ADMIN_LOGIN_EMAIL_WINDOW_SECONDS` | `1800` | Window for email counter (30 min) |
| `ADMIN_LOGIN_EMAIL_COOLDOWN_SECONDS` | `1800` | Cooldown after email limit hit |
| `ADMIN_LOGIN_IP_MAX_ATTEMPTS` | `20` | Max attempts per IP (all emails) |
| `ADMIN_LOGIN_IP_WINDOW_SECONDS` | `600` | Window for IP counter (10 min) |
| `ADMIN_LOGIN_IP_COOLDOWN_SECONDS` | `600` | Cooldown after IP limit hit |
| `ADMIN_LOGIN_FAILURE_DELAY_SECONDS` | `0.5` | Artificial delay on failed attempts |

### MFA

| Variable | Default | Description |
|---|---|---|
| `MFA_ENCRYPTION_KEY` | *(required)* | Fernet key. **Store in AWS Secrets Manager** and inject via ECS secrets or startup script. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `MFA_OTP_MAX_ATTEMPTS` | `5` | Max OTP verification attempts per challenge |
| `MFA_OTP_LOCKOUT_SECONDS` | `900` | Lockout after max OTP attempts (15 min) |
| `MFA_CHALLENGE_TTL_SECONDS` | `300` | Challenge token lifetime (5 min) |
| `MFA_BOOTSTRAP_ENABLED` | `True` | Allow login without MFA for initial enrollment |

### IP Allowlist (application-level)

| Variable | Default | Description |
|---|---|---|
| `ADMIN_IP_ALLOWLIST` | *(empty)* | Comma-separated IPs/CIDRs. Empty = all allowed. Recommended: also enforce at AWS WAF IP Set. |

### Proxy / IP Extraction

| Variable | Default | Description |
|---|---|---|
| `TRUSTED_PROXY_DEPTH` | `1` | Number of trusted proxies. ALB only = `1`, CloudFront + ALB = `2`. Django counts this many positions from the **right** of `X-Forwarded-For` to find the real client IP (e.g. `xff[-1]` for ALB, `xff[-2]` for CF+ALB). |

### Admin Session

| Variable | Default | Description |
|---|---|---|
| `ADMIN_ACCESS_TOKEN_MINUTES` | `15` | Access token lifetime for admin sessions |
| `ADMIN_REFRESH_TOKEN_HOURS` | `4` | Refresh token lifetime for admin sessions |

### Security Headers (auto-enabled when `DEBUG=False`)

| Setting | Value |
|---|---|
| `SESSION_COOKIE_SECURE` | `True` |
| `SESSION_COOKIE_HTTPONLY` | `True` |
| `CSRF_COOKIE_SECURE` | `True` |
| `CSRF_COOKIE_HTTPONLY` | `True` |
| `SECURE_SSL_REDIRECT` | `True` |
| `SECURE_HSTS_SECONDS` | `31536000` |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True` |
| `SECURE_HSTS_PRELOAD` | `True` |
| `SECURE_PROXY_SSL_HEADER` | `('HTTP_X_FORWARDED_PROTO', 'https')` |
| `X_FRAME_OPTIONS` | `DENY` |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` |

---

## New API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/platform-admin/auth/login/` | None | Step 1: email + password |
| POST | `/api/v1/platform-admin/auth/mfa-verify/` | None | Step 2: MFA challenge + OTP |
| POST | `/api/v1/platform-admin/auth/mfa-recovery/` | None | Step 2 alt: MFA + recovery code |
| POST | `/api/v1/platform-admin/auth/mfa-enroll/` | JWT | Start TOTP enrollment |
| POST | `/api/v1/platform-admin/auth/mfa-confirm/` | JWT | Confirm enrollment with OTP |
| POST | `/api/v1/platform-admin/auth/mfa-disable/` | JWT | Disable MFA (superadmin, requires password) |
| POST | `/api/v1/platform-admin/auth/logout/` | JWT | Clear admin session cookies |

---

## New Frontend Routes

| Path | Purpose |
|---|---|
| `/admin/login` | Admin login page (credentials + MFA) |
| `/admin/mfa-setup` | Initial TOTP enrollment |

---

## Audit Events Added

| Action | When |
|---|---|
| `ADMIN_LOGIN_SUCCESS` | Successful admin authentication |
| `ADMIN_LOGIN_FAILED` | Invalid credentials, inactive user, or non-staff |
| `ADMIN_LOGIN_THROTTLED` | IP-level rate limit triggered |
| `ADMIN_LOGIN_COOLDOWN` | IP+email or email cooldown triggered |
| `ADMIN_LOGIN_BLOCKED_IP` | IP not in allowlist |
| `ADMIN_MFA_REQUIRED` | MFA challenge issued |
| `ADMIN_MFA_SUCCESS` | OTP verified |
| `ADMIN_MFA_FAILED` | Wrong OTP |
| `ADMIN_MFA_RECOVERY_USED` | Recovery code consumed |
| `ADMIN_MFA_ENABLED` | MFA enrollment completed |
| `ADMIN_MFA_DISABLED` | MFA removed from user |
| `ADMIN_MFA_RESET` | MFA reset |
| `ADMIN_SUSPICIOUS_AUTH` | Suspicious pattern detected |

---

## AWS WAF vs Application — Responsibility Split

| Concern | AWS WAF | Application (Django) |
|---|---|---|
| IP volumetric rate limit | Rate-based rule (100/5min) | DRF throttle (30/min) |
| Per-email rate limit | N/A (no body inspection) | Cache-based limiter |
| Per-IP+email rate limit | N/A | Cache-based limiter |
| IP allowlist | IP-set rule (edge) | `ADMIN_IP_ALLOWLIST` (app) |
| Geo restriction | Geo-match rule | N/A |
| Bot detection | Bot Control rule group | N/A |
| Anti-enumeration | N/A | Generic errors + delay |
| MFA enforcement | N/A | TOTP + recovery codes |
| Audit logging | WAF logs → CloudWatch | AccessAuditLog model |

---

## Migration

Run after deploying the code:

```bash
python manage.py migrate accounts 0018
```

This migration:
- Adds 4 MFA fields to `AccountProfile`
- Makes `AccessAuditLog.business` nullable (was NOT NULL CASCADE)
- Extends `AccessAuditLog.action` choices with 13 new admin auth events

---

## Deployment Checklist

1. [ ] Store `MFA_ENCRYPTION_KEY` in AWS Secrets Manager
2. [ ] Configure `CACHE_REDIS_URL` pointing to ElastiCache
3. [ ] Set `TRUSTED_PROXY_DEPTH` (1 for ALB, 2 for CloudFront+ALB)
4. [ ] Run `python manage.py migrate`
5. [ ] Create AWS WAF WebACL with rules (see AWS deployment doc)
6. [ ] Attach WebACL to ALB (or CloudFront distribution)
7. [ ] Set `ADMIN_IP_ALLOWLIST` and/or WAF IP-set
8. [ ] Verify `DEBUG=False` in production for security headers
9. [ ] Test admin login flow end-to-end
10. [ ] Superadmin completes MFA enrollment via bootstrap login
11. [ ] Set `MFA_BOOTSTRAP_ENABLED=False` after all admins enrolled
12. [ ] Enable WAF logging to CloudWatch Logs
