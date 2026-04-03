# Mirubro Digital — Total Audit: Roles, Access, Users & Member Lifecycle

**Date:** 2026-04-01
**Auditor:** Staff Engineer / Product Security Auditor
**Scope:** End-to-end review of roles, users, memberships, access control, owner lifecycle, secondary accounts, invitations, onboarding, authentication, seat limits, tenant isolation, and all code behind `/app/settings/access` and `/api/v1/owner/access/`

---

# 1. Executive Summary

## How the Current Access System Works

Mirubro Digital implements a **multi-layered access control system** for its multi-tenant SaaS:

1. **Authentication** via JWT in httpOnly cookies (SimpleJWT), with `CookieJWTAuthentication` supporting both header and cookie-based auth.
2. **Tenant resolution** via `resolve_request_membership()` reading `X-Business-ID` header or `bid` cookie.
3. **RBAC enforcement** via `HasBusinessMembership` (billing gate) + `HasPermission` (role permission gate), evaluated per request.
4. **Permission matrix** defined in `SERVICE_ROLE_PERMISSIONS` per service (gestion/restaurante/menu_qr), customizable per-business via `RolePermissionOverride`.
5. **Billing enforcement** via `resolve_subscription()` (V2-first with legacy fallback) → `get_enforcement_decision()` → blocks access for suspended/canceled/past_due-expired businesses.
6. **Frontend enforcement** via `AppLayout` access gate, sidebar permission filtering, and role-based component visibility.

There is **no invitation system** — secondary users are created directly by the owner with credentials shared out-of-band. There is **no ownership transfer**. The system is **substantially production-ready** for the access control domain, with clear separation of concerns and strong tenant isolation.

## Production-Readiness Score: **72 / 100**

Points deducted for: no invitation flow (-8), no ownership transfer (-4), seat limits only on legacy subscription (-6), branch scope not enforced in queries (-4), no distinct first-time password flow for secondary users (-3), rollout flags hiding behavior (-3).

## Top 5 Risks

| # | Risk | Severity |
|---|------|----------|
| 1 | **Seat limits only check legacy `business.Subscription.max_seats`**, not `SubscriptionV2` | Critical |
| 2 | **No email-based invitation system** — owner must share credentials out-of-band (insecure, poor UX) | High |
| 3 | **Branch scope modeled but not enforced** in data querysets — branch-scoped users can access all branch data | High |
| 4 | **Rollout flags gate incomplete behavior** — if flags enabled before code is ready, breakage occurs | Medium |
| 5 | **3 coexisting subscription systems** create confusion about which is authoritative for seat limits vs billing | Medium |

## Top 5 Blockers Before Production

| # | Blocker | Why |
|---|---------|-----|
| 1 | Fix seat limit enforcement to check SubscriptionV2 (or at minimum, the resolved subscription) | Without this, paid seats can be exceeded for V2-only tenants |
| 2 | Implement invitation flow with email-based password setup | Sharing plaintext passwords is a security anti-pattern |
| 3 | Enforce branch_scope in querysets for branch-level users | Data isolation failure across branches |
| 4 | Test and document rollout flag combinations for production deployment | Flags default False — production must explicitly enable them |
| 5 | Remove or reconcile legacy subscription systems to avoid enforcement confusion | 3 systems create bugs at boundaries |

---

# 2. Architecture Map

## Frontend Routes/Pages/Components

```
/app/settings/access               → OwnerAccessPage (4 tabs)
  Tab: my-roles                    → AccessSummary for current user (all roles)
  Tab: business-roles              → RoleSummary list → /roles/[role]/ detail
  Tab: accounts                    → AccountsTable + modals (owner-only)
  Tab: employees                   → EmployeesTable + modals (owner-only)

/app/settings/access/roles/[role]  → RoleDetailPage (permissions + users)

Components: apps/web/src/components/app/owner-access/
  accounts-table.tsx               → User accounts table with row actions
  member-actions-modals.tsx        → ChangeRoleModal, ConfirmActionModal
  reset-password-modal.tsx         → Reset password, show temp password
  create-member-modal.tsx          → Create internal user form
  employee-form-modal.tsx          → Create/edit operative employee
  employees-table.tsx              → Employee list with row actions
  reset-pin-modal-employee.tsx     → Reset employee PIN
  shared-components.tsx            → PermissionList, RoleBadge, StatusBadge

API Clients:
  apps/web/src/lib/api/owner-access.ts   → 12 endpoints
  apps/web/src/lib/api/employees.ts      → 7 endpoints

Types:
  apps/web/src/types/owner-access.ts     → All request/response types
  apps/web/src/types/employees.ts        → Employee types + enums

Auth:
  apps/web/src/lib/auth/client.ts        → login, register, logout, forgot/reset password, verify email
  apps/web/src/lib/auth/index.ts         → getSession() server-side
  apps/web/src/lib/auth/types.ts         → Session type definition

Route Guards:
  apps/web/src/app/app/layout.tsx        → Main access gate (subscription + status)
  apps/web/src/app/app/onboarding/layout.tsx → Onboarding-only gate
  apps/web/src/middleware.ts             → x-pathname header injection only
  apps/web/src/components/navigation/sidebar.tsx → Permission-key based nav filtering
```

## Backend Endpoints/Views/Serializers/Services/Models

```
URL Config:
  services/api/src/config/urls.py              → Root URL registration
  services/api/src/apps/accounts/owner_urls.py → /api/v1/owner/access/* routes

Views:
  services/api/src/apps/accounts/owner_views.py    → 12 owner access endpoints (~1,100 lines)
  services/api/src/apps/accounts/employee_views.py → 7 employee endpoints (~400 lines)
  services/api/src/apps/accounts/views.py          → Auth views (Login, Register, Me, etc.) (~500 lines)
  services/api/src/apps/accounts/onboarding_views.py → OnboardingStatus, SetService

Serializers:
  services/api/src/apps/accounts/owner_serializers.py → 12 serializer classes

Services:
  services/api/src/apps/accounts/services.py → InternalUserService, OwnerGuardService, EmailService

Models:
  services/api/src/apps/accounts/models.py → AccountProfile, Membership, EmployeeProfile,
                                              AccessAuditLog, RolePermissionOverride

Permissions:
  services/api/src/apps/accounts/permissions.py → HasBusinessMembership, HasPermission,
                                                    EmployeeIsAuthenticated, IsOwnerRole,
                                                    HasEntitlement, RequiresEmailVerified

RBAC:
  services/api/src/apps/accounts/rbac.py          → SERVICE_ROLE_PERMISSIONS dict
  services/api/src/apps/accounts/rbac_registry.py → Capability registry (human-friendly names)

Auth:
  services/api/src/apps/accounts/authentication.py  → CookieJWTAuthentication, EmployeeTokenAuthentication
  services/api/src/apps/accounts/auth_backends.py    → UsernameOrEmailBackend
  services/api/src/apps/accounts/access.py           → resolve_request_membership()

Rollout:
  services/api/src/apps/accounts/rollout.py → 4 rollout flag definitions

Billing:
  services/api/src/apps/billing/runtime.py              → resolve_subscription() (V2-first)
  services/api/src/apps/billing/enforcement.py           → get_enforcement_decision()
  services/api/src/apps/billing/subscription_activator.py → activate_subscription_from_invoice()
  services/api/src/apps/billing/models.py                 → SubscriptionV2, MpCheckoutSession

Business:
  services/api/src/apps/business/models.py   → Business, Subscription (legacy)
  services/api/src/apps/business/context.py  → build_business_context()
```

---

# 3. Current Domain Model

| Entity | Purpose | Key Fields | Tenant Scoped? | Used By | Status |
|--------|---------|------------|----------------|---------|--------|
| **Django User** | Authentication identity | id, email, username, password, is_active, first_name, last_name | No (global) | All auth flows | Active |
| **AccountProfile** | User profile extension (1:1 with User) | account_status, email_verified, mfa_secret_encrypted, mfa_enabled, email_verification_token_hash, password_reset_token_hash | No (global) | Auth, verification, MFA | Active |
| **Business** | Tenant entity (HQ or branch) | name, parent (FK self), slug, service_type, status, country, currency, timezone, trial dates | N/A (is the tenant) | All tenant-scoped ops | Active |
| **Membership** | User ↔ Business join table (RBAC) | user (FK), business (FK), role (10 choices), status, branch_scope (FK), permissions (JSON), created_by_user | Yes | Access control, session | Active |
| **Subscription** (business app) | Legacy subscription (1:1 with Business) | business, plan, service, status, max_branches, max_seats | Yes | Seat limits (signal), legacy resolution | Legacy — still required for seat limits |
| **SubscriptionAddon** (business app) | Legacy plan add-ons | subscription (FK), code, quantity | Yes | Legacy add-on calculation | Legacy |
| **billing.Subscription** | Intermediate subscription (1:1) | business, plan_type, bundle, status, billing_period, selected_modules | Yes | Billing context (legacy) | Legacy |
| **billing.SubscriptionV2** | Canonical subscription (FK, allows history) | business (FK), service_type, plan_code, provider, status (state machine), trial/period dates, grace_until, cancel fields | Yes | Runtime resolution, enforcement | Active (canonical) |
| **RolePermissionOverride** | Per-business custom role permissions | business (FK), role, service, permission, enabled | Yes | Permission customization | Active |
| **EmployeeProfile** | Operative employee for POS/restaurant | business (FK), branch (FK), linked_user (FK), first_name, last_name, alias, employee_code, role_type, login_code_hash, must_change_pin, status | Yes | POS auth, employee mgmt | Active |
| **AccessAuditLog** | Audit trail (55+ action types) | action, actor (FK), target_user (FK), actor_type, business (FK), entity_type, entity_id, details, before_json, after_json, ip_address, user_agent | Yes | Compliance, debugging | Active |
| **MpCheckoutSession** (billing) | MercadoPago checkout tracking | tenant (FK Business), user (FK), plan (FK), status, mp fields | Yes | Checkout flow | Active |
| **BillingInvoiceEvent** (billing) | Payment event tracking | subscription (FK V2), provider_status, amount, paid_at | Yes | Activation trigger | Active |
| **Invitation** | Email-based user invitation | — | — | — | **NOT IMPLEMENTED** |

---

# 4. Real End-to-End Flows

## Flow 1: New Owner Signup

| Step | Code Path | Details |
|------|-----------|---------|
| **Entrypoint** | Frontend: `/(auth)/registrarse` → `POST /api/v1/auth/register/` | Public registration page |
| **RegisterView** | [views.py:242](services/api/src/apps/accounts/views.py#L242) | Creates `User(username=email, email=email)` + auto-creates `AccountProfile(email_verified=False)` via signal |
| **Verification email** | [EmailService.send_verification_email()](services/api/src/apps/accounts/services.py) | Sends link with plaintext token; SHA-256 hash stored |
| **Email verify** | `POST /api/v1/auth/verify-email/` → [VerifyEmailView](services/api/src/apps/accounts/views.py#L352) | Token validated, `email_verified=True`, `account_status=ACTIVE` |
| **First login** | `POST /api/v1/auth/login/` → [LoginView](services/api/src/apps/accounts/views.py#L215) | Calls `_ensure_membership()` → creates `Business(status='onboarding')` + `Membership(role='owner')` |
| **Login response** | JWT cookies set + `{onboarding: true}` | Frontend routes to `/app/onboarding` |
| **Records created** | User → AccountProfile → Business(onboarding) → Membership(owner) | No subscription created at this point |
| **Audit** | EMAIL_VERIFIED logged | Other creation events not logged (gap) |
| **Access state** | `access_allowed=false`, `reason_code=no_subscription` | User can only see onboarding funnel |

## Flow 2: Owner Pays and Starts Using Mi Rubro

| Step | Code Path | Details |
|------|-----------|---------|
| **Entrypoint** | Frontend: `/app/onboarding` → step router → `/servicio` → `/plan` → `/checkout` | 3-step onboarding funnel |
| **Service selection** | `POST /api/v1/auth/onboarding/set-service/` → [SetServiceView](services/api/src/apps/accounts/onboarding_views.py) | Sets `Business.service_type` |
| **Plan selection** | Frontend selects plan, proceeds to checkout | MercadoPago checkout session created |
| **Checkout** | `POST /api/v1/billing/commercial/checkout/` | Creates `MpCheckoutSession` + MP preapproval plan, returns redirect URL |
| **User pays** | Redirected to MercadoPago, provides payment | External flow |
| **Webhook: preapproval** | MP webhook → creates `SubscriptionV2(status=CHECKOUT_PENDING)` | Links MP subscription to tenant |
| **Webhook: authorized_payment** | MP webhook → [activate_subscription_from_invoice()](services/api/src/apps/billing/subscription_activator.py) | **ONLY activation path** — atomic, idempotent, SELECT FOR UPDATE |
| **Activation** | SubscriptionV2.status='active', is_active=True → Business.status='active' → MpCheckoutSession.status='activated' | All within single transaction |
| **Membership** | `_ensure_owner_membership()` called inside activator | Ensures owner Membership exists (idempotent) |
| **Access state** | `access_allowed=true`, `reason_code=access_granted` | User can now access all plan features |
| **Race conditions** | Handled via `SELECT FOR UPDATE` on SubscriptionV2 row | Concurrent webhooks safely serialized |

## Flow 3: Business/Account Provisioning

| Aspect | Details |
|--------|---------|
| **Who creates Business** | `_ensure_membership()` in views.py, called at first login |
| **When** | Lazy creation — only when user has no existing Membership |
| **Status** | Created with `status='onboarding'` |
| **Subscription** | NOT created at this point — billing required |
| **Idempotent?** | Yes — checks for existing Membership first |
| **Retry/abandon** | Safe — onboarding step router resumes from correct step |
| **HQ/Branch** | Always creates HQ (no parent) |

## Flow 4: Secondary Account Creation

| Aspect | Details |
|--------|---------|
| **UI action** | Owner clicks "+ Crear usuario" in Accounts tab |
| **Frontend** | `CreateMemberModal` → `ownerAccessApi.createMember()` |
| **Backend** | `POST /api/v1/owner/access/accounts/create/` → [create_member()](services/api/src/apps/accounts/owner_views.py) → `InternalUserService.create_internal_user()` |
| **Created** | Django User + AccountProfile(email_verified=True) + Membership(status=ACTIVE) |
| **Password** | Set by owner during creation — shown in modal, must be shared out-of-band |
| **Email** | Optional — if provided, checked for uniqueness but no invite email sent |
| **Seat limit** | Checked atomically with SELECT FOR UPDATE (but only against legacy max_seats) |
| **Audit** | USER_CREATED logged |
| **Who can create** | Owner only (backend enforced) |
| **Can admin create?** | **No** — only owner role |
| **Multi-business?** | A User can have Membership in multiple businesses (unique constraint: user+business) |
| **Branch scope** | Not set during creation — all new users get full tree access |

## Flow 5: Invitation Acceptance

| Aspect | Details |
|--------|---------|
| **Status** | **NOT IMPLEMENTED** |
| **Evidence** | No `Invitation` model, no invite endpoint, no invite email flow, no invite acceptance page |
| **Current workaround** | Owner creates user with credentials and shares them directly |
| **Impact** | Poor UX, insecure credential sharing, no self-service password setup for new users |

## Flow 6: Password Setup and Authentication

| Aspect | Details |
|--------|---------|
| **Owner self-service** | Register → email verification → login with password set at registration |
| **Secondary user password** | Set by owner during `createMember()` → must be shared out-of-band |
| **Distinct set-password flow?** | **No** — no first-time password setup link for invited users (invitations don't exist) |
| **Password reset (self-service)** | `POST /auth/forgot-password/` → email with token → `POST /auth/reset-password/` |
| **Password reset (owner)** | `POST /owner/access/accounts/{id}/reset-password/` → generates temp password or explicit |
| **Email verification required?** | Gated by `EMAIL_VERIFICATION_ENFORCEMENT` rollout flag. If enabled, commercial endpoints require `email_verified=True` |
| **Loopholes** | Internal users created via `createMember()` get `email_verified=True` automatically — bypasses verification requirement (by design, since owner is vouching) |
| **Login/refresh/logout/restore** | Coherent — JWT in cookies, 15-min access + 7-day refresh, rotation on refresh, server-side session restore via `/auth/me/` |

## Flow 7: Access Management Screen (`/app/settings/access`)

| Tab | Data Source | API Call | Actions | Backend Enforcement |
|-----|-------------|----------|---------|---------------------|
| **My Roles** | AccessSummary for current user | `GET /owner/access/summary/` | View-only | Any authenticated member |
| **Business Roles** | All roles with user counts | `GET /owner/access/roles/` | View roles, navigate to detail | Owner-only (backend) |
| **Accounts** | All user accounts in business | `GET /owner/access/accounts/` | Change role, reset password, suspend/reactivate, remove | Owner-only (backend) |
| **Employees** | All operative employees | `GET /owner/access/employees/` | Create, edit, reset PIN, suspend/reactivate | Owner/Admin (backend) |

**Mismatches found**: See Section 7 for details.

## Flow 8: Member Lifecycle Management

| Action | Implemented? | Frontend | Backend | Enforcement |
|--------|-------------|----------|---------|-------------|
| Add member | Yes | CreateMemberModal | `POST /accounts/create/` | Owner-only, seat limit (legacy) |
| Edit role | Yes | ChangeRoleModal | `PATCH /accounts/{id}/role/` | Owner-only, last-owner guard |
| Resend invite | **No** | — | — | Invitations not implemented |
| Remove member | Yes | ConfirmActionModal | `DELETE /accounts/{id}/` | Owner-only, last-owner guard |
| Deactivate/suspend | Yes | ConfirmActionModal (toggle) | `POST /accounts/{id}/suspend/` | Owner-only, last-owner guard |
| Transfer ownership | **No** | — | — | Not implemented |
| Recover access | Partial | Self-service password reset | `POST /auth/forgot-password/` | Works for users with email |
| Reinvite after expiration | **No** | — | — | Invitations not implemented |

## Flow 9: Subscription / Seat / State Enforcement

| Aspect | Details |
|--------|---------|
| **Seat limits enforced server-side?** | **Partially** — `check_seat_limit` pre_save signal checks `legacy business.Subscription.max_seats` only. `InternalUserService.create_internal_user()` also checks atomically (SELECT FOR UPDATE) but same legacy source. SubscriptionV2 does NOT have max_seats field. |
| **What happens in past_due?** | If within `grace_until` → access allowed with renewal prompt. If grace expired → access blocked (`reason_code=grace_period_expired`). Business.status mirrored to `past_due`. |
| **What happens in suspended?** | Access fully blocked (`reason_code=suspended`). Frontend redirects to `/app/cuenta/estado?status=suspended`. |
| **What happens in canceled?** | Access fully blocked (`reason_code=canceled`). Frontend redirects to `/app/cuenta/estado?status=canceled`. |
| **Can owner invite members while past_due/suspended?** | **No** — `HasBusinessMembership` blocks ALL requests for non-access-allowed businesses. But `/owner/access/` endpoints do not have `billing_enforcement_bypass`, so they are blocked correctly. |
| **Can existing staff still log in during past_due?** | They can login (LoginView has no billing check) but MeView returns `access_allowed=false`, and AppLayout redirects to state page. Effectively blocked from using the app. |
| **Inconsistencies** | Seat limits use legacy Subscription; billing enforcement uses V2-first resolver. A V2-only tenant has billing enforcement but NO seat limits. |

## Flow 10: Multi-Tenant Safety

| Check | Status | Evidence |
|-------|--------|----------|
| **Queryset filtering** | ✅ All viewsets filter by `business` in `get_queryset()` | Verified across catalog, sales, inventory, invoices, orders, customers, cash, treasury |
| **get_object filtering** | ✅ `get_object_or_404` includes `business=` filter | Consistent pattern |
| **Serializer validation** | ✅ Cross-tenant FK references rejected | Treasury tests verify rejecting cross-business expense |
| **ID manipulation** | ✅ Cannot access another business's data by changing IDs | Queryset is always scoped first |
| **Role checks tenant-specific** | ✅ Membership is per (user, business) | Permission resolution uses membership's role + business's service |
| **Branch scope leaks** | ⚠️ `branch_scope` field exists but not enforced in querysets | Branch-scoped users can currently access all branches in HQ family |
| **Employee token isolation** | ✅ `business_id` embedded in JWT, validated on decode | Cannot cross-access businesses |

---

# 5. Access Control Matrix

Based on code analysis of `SERVICE_ROLE_PERMISSIONS` in [rbac.py](services/api/src/apps/accounts/rbac.py) and owner_views.py permission checks.

| Action | owner | admin | manager | cashier | staff | viewer | kitchen | salon | analyst | contador |
|--------|-------|-------|---------|---------|-------|--------|---------|-------|---------|----------|
| Invite member | N/A¹ | N/A¹ | N/A¹ | N/A¹ | N/A¹ | N/A¹ | N/A¹ | N/A¹ | N/A¹ | N/A¹ |
| Create internal user | ✅ backend | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Change role | ✅ backend | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Remove member | ✅ backend | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Transfer ownership | N/A² | N/A² | N/A² | N/A² | N/A² | N/A² | N/A² | N/A² | N/A² | N/A² |
| View billing | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Access settings/access | ✅ | ✅ (UI)³ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Access admin pages | ✅ platform | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Access POS | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| Access reports | ✅ backend | ✅ backend | ✅ backend | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ backend | ✅ backend |
| Access invoicing | ✅ backend | ✅ backend | ✅ backend | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ backend |
| Manage branches | ✅ backend | ✅ backend | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Manage employees | ✅ backend | ✅ backend | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Reset password (other user) | ✅ backend | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Suspend member | ✅ backend | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Edit role permissions | ✅ backend | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| View audit logs | ✅ backend | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

¹ Invitations not implemented  
² Ownership transfer not implemented  
³ Admin can click "Roles & Accesos" in sidebar (`permissionKey: manage_users` granted to admin), but backend checks `role == 'owner'` for most tabs. The `access_summary` endpoint is open to all; role/account/employee listing requires owner. **Mismatch: admin sees the page but only the "My Roles" tab works.** The frontend does check `isOwner` (matching owner OR admin) but the backend owner_views require strict owner role for accounts/roles/employees.

---

# 6. Findings

## Critical Findings

### C1: Seat Limits Not Enforced for SubscriptionV2 Tenants
- **Severity:** Critical
- **Why it matters:** If a business has only a `SubscriptionV2` (no legacy `business.Subscription`), the `check_seat_limit` signal and `InternalUserService` will find `sub = None` and skip the seat check entirely. This means unlimited users can be created.
- **Evidence:**
  - [models.py:253](services/api/src/apps/accounts/models.py#L253): `sub = getattr(hq, 'subscription', None)` — this accesses `business.Subscription` (legacy OneToOne), NOT SubscriptionV2
  - [services.py](services/api/src/apps/accounts/services.py): `InternalUserService.create_internal_user()` also checks `hq.subscription.max_seats`
  - `SubscriptionV2` does not have a `max_seats` field
- **Reproduction:** Create a business with only a V2 subscription → create unlimited members
- **Impact:** Revenue loss (seats not enforced), potential abuse
- **Fix:** Resolve seat limits through the runtime subscription resolver, or add `max_seats` to plan configuration accessed via V2 plan_code
- **Release blocker:** Yes

### C2: No Invitation System — Credentials Shared in Plaintext
- **Severity:** High (approaching Critical for production)
- **Why it matters:** The owner creates a secondary user with username + password, then must share those credentials via external channels (WhatsApp, text, verbal). This is an unacceptable security practice for a SaaS product handling financial data.
- **Evidence:**
  - [create-member-modal.tsx](apps/web/src/components/app/owner-access/create-member-modal.tsx): Shows temp credentials to owner for manual sharing
  - No `Invitation` model anywhere in codebase
  - No invite endpoint in owner_urls.py
  - No invite email template
- **Reproduction:** Create a member → credentials shown once → no email sent
- **Impact:** Credential interception, poor onboarding UX, no password ownership by the invited user
- **Fix:** Implement email-based invitation with token-based password setup link
- **Release blocker:** Yes (for commercial launch)

## High Findings

### H1: Branch Scope Not Enforced in Data Queries
- **Severity:** High
- **Why it matters:** `Membership.branch_scope` is a FK field that should restrict a user to a specific branch's data, but NO queryset filtering uses it. A cashier assigned to Branch A can see all data from Branch B.
- **Evidence:**
  - [models.py:187](services/api/src/apps/accounts/models.py#L187): `branch_scope = models.ForeignKey('business.Business', ...)` — field exists
  - No occurrences of `branch_scope` in any ViewSet `get_queryset()` across all apps
  - `resolve_request_membership()` in [access.py](services/api/src/apps/accounts/access.py) resolves branch but does not filter data by it
- **Impact:** Cross-branch data leak within same business family
- **Fix:** Add branch filtering middleware or ViewSet mixin that applies `branch_scope` to querysets
- **Release blocker:** Yes if multi-branch is a production feature

### H2: Admin Role Frontend/Backend Mismatch on Access Page
- **Severity:** High
- **Why it matters:** Frontend checks `role === 'owner' || role === 'admin'` to show management tabs, but backend requires strict `role === 'owner'` for all owner endpoints. An admin sees tabs they cannot use.
- **Evidence:**
  - [page.tsx](apps/web/src/app/app/settings/access/page.tsx): `const canManage = summary.role === 'owner' || summary.role === 'admin'`
  - [owner_views.py](services/api/src/apps/accounts/owner_views.py): All endpoints check `membership.role == 'owner'`
- **Reproduction:** Log in as admin → navigate to /app/settings/access → see Accounts/Roles/Employees tabs → all API calls fail with 403
- **Impact:** Confusing UX, broken admin experience
- **Fix:** Either restrict frontend to owner-only, or expand backend to support admin for read operations
- **Release blocker:** No (UX issue, not security)

### H3: Legacy Subscription System Still Required for Seat Limits
- **Severity:** High
- **Why it matters:** Even though SubscriptionV2 is canonical for billing enforcement, the legacy `business.Subscription` is still the only source of `max_seats`. If the legacy subscription is not backfilled or maintained, seat limits silently disappear.
- **Evidence:**
  - [models.py:253](services/api/src/apps/accounts/models.py#L253): Seat check reads `hq.subscription.max_seats`
  - [runtime.py](services/api/src/apps/billing/runtime.py): V2 is authoritative for billing — creates divergence
- **Impact:** Seat enforcement depends on maintaining TWO subscription systems simultaneously
- **Fix:** Add seat limit configuration to V2 resolution chain (e.g., plan tier → seat limit lookup)
- **Release blocker:** Coupled with C1

## Medium Findings

### M1: No Ownership Transfer Mechanism
- **Severity:** Medium
- **Why it matters:** If the business owner becomes unavailable, there is no self-service or even admin tool to transfer ownership. The last-owner guard prevents the sole owner from being demoted.
- **Evidence:**
  - `OwnerGuardService.assert_not_last_owner()` in [services.py](services/api/src/apps/accounts/services.py) blocks sole-owner changes
  - No `transfer_ownership` endpoint in owner_urls.py
  - No admin endpoint for ownership transfer
- **Impact:** Business lockout if owner loses access
- **Fix:** Implement ownership transfer (owner-initiated) and admin-facilitated recovery
- **Release blocker:** No (operational workaround: direct DB update)

### M2: Rollout Flags Default to False — Production Configuration Required
- **Severity:** Medium
- **Why it matters:** All 4 rollout flags default to `False`. If deployed to production without explicit configuration:
  - `SUBSCRIPTION_STATUS_ENFORCEMENT` off → suspended accounts can still access data
  - `EMAIL_VERIFICATION_ENFORCEMENT` off → unverified emails can start subscriptions
  - `NEW_ONBOARDING` off → new users miss the onboarding funnel
  - `OWNER_USER_MANAGEMENT_V2` off → V2 management features hidden
- **Evidence:** [rollout.py](services/api/src/apps/accounts/rollout.py): `flags.get(flag_name, False)`
- **Impact:** Security features disabled unless explicitly turned on
- **Fix:** Document required flags for production. Consider making V2 features the default.
- **Release blocker:** Yes (configuration, not code)

### M3: Internal Users Skip Email Verification by Design
- **Severity:** Medium
- **Why it matters:** Users created via `createMember()` get `email_verified=True` automatically. While this is intentional (owner vouches for them), it means the email address is never verified to actually belong to that person.
- **Evidence:** [services.py](services/api/src/apps/accounts/services.py): `InternalUserService.create_internal_user()` sets `profile.email_verified = True`
- **Impact:** Email field may be incorrect; password reset emails would go to wrong address
- **Fix:** Acceptable if invitations are implemented (invited user verifies their own email)
- **Release blocker:** No

### M4: No Rate Limiting on Owner Access Endpoints
- **Severity:** Medium
- **Why it matters:** The `reset-password` and `create-member` endpoints lack rate limiting. An attacker with a compromised owner session could create many users or reset passwords rapidly.
- **Evidence:** No throttle classes on owner_views.py endpoints
- **Impact:** Abuse potential with compromised credentials
- **Fix:** Add DRF throttle classes to sensitive endpoints
- **Release blocker:** No

### M5: Password Complexity Not Enforced
- **Severity:** Medium
- **Why it matters:** Only minimum 8 characters required. No complexity rules (upper, lower, digit, special). MFA is available but not mandatory.
- **Evidence:** [owner_serializers.py](services/api/src/apps/accounts/owner_serializers.py): `min_length=8, max_length=128`
- **Impact:** Weak passwords susceptible to brute-force (mitigated by JWT cookie architecture — no direct API brute force since session is cookie-bound)
- **Fix:** Use Django's built-in password validators
- **Release blocker:** No

## Low Findings

### L1: Audit Log does not Track Business/Membership Creation During Registration
- **Severity:** Low
- **Why it matters:** `_ensure_membership()` creates Business + Membership but does not write to `AccessAuditLog`.
- **Evidence:** [views.py:94](services/api/src/apps/accounts/views.py#L94): Only `logger.info()`, no audit log
- **Fix:** Add MEMBERSHIP_CREATED audit log entry
- **Release blocker:** No

### L2: VerifyEmailView Has Dead Code (Unreachable First Query)
- **Severity:** Low
- **Why it matters:** There's a stale `.first()` query before the actual hash-based lookup.
- **Evidence:** [views.py:370](services/api/src/apps/accounts/views.py#L370): `profile = AccountProfile.objects...filter(email_verification_token_hash__isnull=False).first()` — result immediately overwritten
- **Fix:** Remove the dead query
- **Release blocker:** No

### L3: ForgotPasswordView Logs Wrong Audit Action
- **Severity:** Low
- **Why it matters:** Uses `PASSWORD_RESET_CONFIRMED` for a "request" action, not "confirmed".
- **Evidence:** [views.py:455](services/api/src/apps/accounts/views.py#L455): `action='PASSWORD_RESET_CONFIRMED'` with `details={'source': 'self_service'}`
- **Fix:** Use a distinct action like `PASSWORD_RESET_REQUESTED`
- **Release blocker:** No

### L4: Employee Code Generation Not Collision-Safe Under Concurrency
- **Severity:** Low
- **Why it matters:** Employee code generation (EMP-NNNN) uses sequential counting which could collide under concurrent creation requests.
- **Fix:** Use unique constraint retry or UUID-based codes
- **Release blocker:** No

---

# 7. Gaps Between UI and Backend

## Actions Shown in UI But Not Supported in Backend

| UI Element | Issue |
|------------|-------|
| Admin sees "Business Roles", "Accounts", "Employees" tabs | Backend enforces owner-only; admin gets 403 on all API calls. Frontend shows these tabs because `canManage` includes admin role. |
| "Resend invite" concept | UI does not show it, but the absence of invitations means there's no way to re-send credentials if lost. Owner must reset password manually. |

## Backend Capabilities Not Exposed in UI

| Capability | Backend | Frontend |
|------------|---------|----------|
| `POST /accounts/{id}/disable/` | Exists (legacy toggle disable) | Not shown — replaced by suspend in V2 |
| `GET /audit-logs/` | Returns full audit trail | **Not shown in access page UI** — no audit log tab visible |
| `PUT /roles/{role}/permissions/` with granular customization | Full per-permission override | UI supports it via role detail page (toggle switches) |
| `PATCH /employees/{id}/` | Update all employee fields | UI shows edit modal for name/alias/role only |

## Wording That Could Mislead

| UI Text | Issue |
|---------|-------|
| "Resetear" (password) | Could be confused with "remove" — consider "Resetear contraseña" |
| "Suspender" toggle | Suspends membership (blocks app access) but the button says "Suspender" without clarifying it blocks login |
| Employee "Credencial" column shows PIN/QR/NFC | But only PIN is implemented — QR_CODE and NFC_TAG are model choices but no implementation |

## Missing States

| State | Issue |
|-------|-------|
| No "invitation pending" indicator | Because invitations don't exist, but when implemented, the accounts table should show pending invites |
| No visual indicator for "email not verified" | `email_verified` is not shown in the accounts table — owner can't see if a user's email is verified |
| No indication of branch scope | Accounts table does not show which branch a user is scoped to |

---

# 8. Legacy and Duplication Risks

## Subscription Systems (3 Coexisting)

| System | Location | Purpose | Status | Risk |
|--------|----------|---------|--------|------|
| `business.Subscription` | [business/models.py](services/api/src/apps/business/models.py) | Legacy plan + max_seats + max_branches | **STILL REQUIRED** for seat limits | If removed, seat limits break |
| `billing.Subscription` | [billing/models.py](services/api/src/apps/billing/models.py) (OneToOne) | Intermediate billing (bundles + modules) | Legacy | Dead weight — not used by runtime resolver |
| `billing.SubscriptionV2` | [billing/models.py](services/api/src/apps/billing/models.py) (FK) | Canonical state machine + provider integration | **ACTIVE** (canonical for billing) | Missing seat/branch limit fields |

**Canonical:** `SubscriptionV2` for billing status/enforcement. But `business.Subscription` for seat limits.
**Risk:** Divergence between the two leads to inconsistent enforcement.

## Onboarding Versions

| Version | Gated By | Status |
|---------|----------|--------|
| Legacy (direct billing hub) | `NEW_ONBOARDING=false` | Still active when flag off |
| V2 (7-step funnel) | `NEW_ONBOARDING=true` | Production-intended flow |

**Risk:** If `NEW_ONBOARDING` not enabled, users go through legacy flow that may create inconsistent state.

## Owner Management Versions

| Version | Gated By | Endpoints |
|---------|----------|-----------|
| V1 | Always active | `disable_account` (toggle is_active) |
| V2 | `OWNER_USER_MANAGEMENT_V2=true` | `change_role`, `suspend_member`, `remove_member` |

**Risk:** V1 `disable_account` disables the Django User globally (not per-business). V2 `suspend_member` suspends the Membership (per-business). Both exist at different URLs. The frontend uses V2 actions exclusively.

## Dead/Legacy Code to Consider Removing

| Code | File | Reason |
|------|------|--------|
| `billing.Subscription` (OneToOne) | billing/models.py | Not used by runtime resolver — only V2 and legacy business.Subscription |
| `disable_account` endpoint | owner_views.py | Replaced by `suspend_member` in V2 |
| `AccountProfile.account_status` field with `PENDING_EMAIL_VERIFICATION` | models.py | Could be derived from `email_verified` flag |
| `Business.default_service` | business/models.py | Replaced by `service_type` |

---

# 9. Production Hardening Checklist

## Security

- [ ] Fix seat limit enforcement to use SubscriptionV2 plan configuration (C1)
- [ ] Implement email-based invitation flow with password setup link (C2)
- [ ] Add rate limiting to owner access endpoints (M4)
- [ ] Add Django password validators (M5)
- [ ] Remove dead code in VerifyEmailView (L2)
- [ ] Verify CORS configuration restricts origins in production
- [ ] Ensure all rollout flags are explicitly set in production environment

## Tenant Isolation

- [ ] Enforce `branch_scope` in querysets for multi-branch deployments (H1)
- [ ] Add cross-tenant access tests for owner access endpoints
- [ ] Add tests for employee token cross-business attempts
- [ ] Verify serializer FK queryset restrictions across all apps

## Owner UX

- [ ] Fix admin role mismatch on access page — either restrict or expand (H2)
- [ ] Show audit log tab in access page UI
- [ ] Show email verification status in accounts table
- [ ] Show branch scope in accounts table
- [ ] Add "invitation pending" state when invitations are implemented
- [ ] Improve wording: "Resetear contraseña", "Suspender acceso"

## Data Consistency

- [ ] Add `max_seats` and `max_branches` to V2 plan configuration or lookup
- [ ] Reconcile 3 subscription systems — remove `billing.Subscription` (OneToOne)
- [ ] Ensure `business.Subscription` backfill always runs for V2-first tenants
- [ ] Add audit log for business/membership creation during registration (L1)
- [ ] Fix ForgotPasswordView audit action label (L3)

## Billing/Access Consistency

- [ ] Enable `SUBSCRIPTION_STATUS_ENFORCEMENT` in production
- [ ] Enable `EMAIL_VERIFICATION_ENFORCEMENT` in production
- [ ] Enable `NEW_ONBOARDING` in production
- [ ] Enable `OWNER_USER_MANAGEMENT_V2` in production
- [ ] Document grace period duration and retry behavior
- [ ] Test all business states (onboarding → active → past_due → suspended → canceled) end-to-end

## Observability/Auditability

- [ ] Expose audit log in access management UI
- [ ] Add structured logging for all owner access operations
- [ ] Monitor V2 vs legacy subscription mismatch logs (already logging but need alerting)
- [ ] Add metrics for member creation, role changes, suspensions

## Test Coverage

- [ ] Backend: Cross-tenant access tests for owner endpoints
- [ ] Backend: Seat limit tests with V2-only tenants (will fail — confirming C1)
- [ ] Backend: All business state transition tests
- [ ] Backend: Concurrent webhook activation tests
- [ ] Frontend: Access page E2E tests
- [ ] Frontend: Admin role sees but can't use management tabs (H2)
- [ ] Frontend: Subscription state pages render correctly

---

# 10. Recommended Target Behavior

## Owner Creation
**Current:** Register → verify email → login → lazy Business(onboarding) + Membership(owner) → onboarding funnel → checkout → webhook activates.
**Recommended:** Keep current flow. Add audit log for business creation. Ensure all flags enabled in production.

## Tenant Provisioning
**Current:** Lazy at first login. Business starts as `onboarding`.
**Recommended:** Keep lazy provisioning. Add idempotent retry support for abandoned onboarding (already handled by step router).

## Invite Flow
**Current:** NOT IMPLEMENTED. Owner creates user with credentials shared verbally.
**Recommended target:**
1. Owner enters email + role in invite form
2. Backend creates `Invitation(email, role, business, token_hash, expires_at, status=pending)`
3. Email sent with invite link to `/aceptar-invitacion?token=...`
4. If user exists → link to existing account, create Membership
5. If user doesn't exist → register with email + choose password, create Membership
6. Invitation status: pending → accepted (or expired after 7 days)
7. Owner can resend or cancel invitation

## Secondary Account Setup
**Current:** Owner sets password for user.
**Recommended:** Keep direct creation as a fallback (for kiosk/POS scenarios where users don't have email). But make invitation the primary flow for users with email.

## Password Setup
**Current:** Owner sets password or self-service reset.
**Recommended:** Add first-time password setup link for invited users. The invite email contains a token that allows the user to set their own password.

## Role Changes
**Current:** Owner-only via PATCH. Backend-enforced with last-owner guard.
**Recommended:** Keep current implementation. Consider allowing admin to change non-owner roles.

## Suspension Behavior
**Current:** Membership status toggled. User blocked from business access.
**Recommended:** Keep current implementation. Add clear messaging about what "suspended" means.

## Member Limits
**Current:** Legacy max_seats only.
**Recommended:** Create a plan configuration lookup: `plan_code → {max_seats, max_branches}` accessible from V2 runtime. Drop dependency on legacy Subscription for limits.

---

# 11. Implementation Plan

## Phase 0: Immediate Blockers (pre-launch)

| # | Objective | Files | Risk | Sequence |
|---|-----------|-------|------|----------|
| 0.1 | Fix seat limits for V2 tenants — add plan-tier → max_seats lookup | accounts/models.py, accounts/services.py, billing/runtime.py | Medium (data migration) | First |
| 0.2 | Enable all 4 rollout flags in production config | settings.py, .env.production | Low (config only) | Parallel with 0.1 |
| 0.3 | Fix admin/owner mismatch on access page frontend | apps/web/.../access/page.tsx | Low | Parallel |
| 0.4 | Remove dead code in VerifyEmailView | accounts/views.py | None | Parallel |
| 0.5 | Fix ForgotPasswordView audit action | accounts/views.py | None | Parallel |

## Phase 1: Stabilization

| # | Objective | Files | Risk | Sequence |
|---|-----------|-------|------|----------|
| 1.1 | Implement invitation model + API | accounts/models.py, new invite_views.py, invite_serializers.py | Medium | First |
| 1.2 | Build invitation acceptance flow (backend) | accounts/views.py, accounts/services.py | Medium | After 1.1 |
| 1.3 | Build invitation UI (frontend) | owner-access/ components, api client | Medium | After 1.2 |
| 1.4 | Implement first-time password setup page | frontend auth pages | Low | After 1.2 |
| 1.5 | Add rate limiting to sensitive endpoints | accounts/owner_views.py | Low | Parallel |
| 1.6 | Add password validation rules | accounts/services.py, owner_serializers.py | Low | Parallel |

## Phase 2: Cleanup / Consolidation

| # | Objective | Files | Risk | Sequence |
|---|-----------|-------|------|----------|
| 2.1 | Remove `billing.Subscription` (OneToOne) | billing/models.py, migrations | Medium (data migration) | First |
| 2.2 | Migrate seat/branch limits to V2 plan config | billing/models.py, accounts/models.py | Medium | After 2.1 |
| 2.3 | Remove `disable_account` endpoint (V1) | owner_views.py, owner_urls.py | Low | After V2 fully active |
| 2.4 | Enforce branch_scope in querysets | All viewset files (mixin) | Medium (testing) | After 2.2 |
| 2.5 | Remove `OWNER_USER_MANAGEMENT_V2` flag (make V2 permanent) | rollout.py, all checks | Low | After 2.3 |

## Phase 3: UX Polish

| # | Objective | Files | Risk | Sequence |
|---|-----------|-------|------|----------|
| 3.1 | Add audit log tab to access page | access/page.tsx, new component | Low | Any time |
| 3.2 | Add email verification indicator in accounts table | accounts-table.tsx | Low | Any time |
| 3.3 | Add branch scope indicator in accounts table | accounts-table.tsx | Low | After 2.4 |
| 3.4 | Implement ownership transfer | new endpoint + modal | Medium | After 2.4 |
| 3.5 | Improve wording/labels across access page | components/*.tsx | None | Any time |
| 3.6 | Add invitation status/progress indicators | accounts-table.tsx | Low | After 1.3 |

---

# 12. Test Plan

## Backend Unit/Integration Tests

### Missing Tests (High Priority)

| Test | What It Validates | Priority |
|------|-------------------|----------|
| `test_create_member_v2_only_tenant_exceeds_seats` | Seat limit enforcement with V2-only subscription (currently no limit enforced) | Critical |
| `test_create_member_no_subscription_rejects` | Cannot create users when business has no subscription at all | High |
| `test_admin_role_cannot_access_owner_endpoints` | Admin 403 on accounts/roles/employees endpoints | High |
| `test_cross_business_member_creation_blocked` | Cannot create a member in another business's context | High |
| `test_business_state_transitions_mirror_subscription` | Business.status follows SubscriptionV2.status changes | High |
| `test_past_due_owner_cannot_create_members` | Billing enforcement blocks member creation during past_due | Medium |
| `test_suspended_user_blocked_from_all_endpoints` | Suspended membership cannot access any endpoint | Medium |
| `test_concurrent_seat_limit_check` | Race condition testing with parallel member creation | Medium |

### Missing Tests (Medium Priority)

| Test | What It Validates |
|------|-------------------|
| `test_registration_audit_log_created` | _ensure_membership() creates audit log |
| `test_email_verification_token_expiry` | Token expires after 48 hours |
| `test_password_reset_token_single_use` | Token cannot be reused |
| `test_rollout_flag_subscription_enforcement` | Suspended accounts blocked when flag enabled |
| `test_rollout_flag_email_verification` | Commercial endpoints require verified email when flag enabled |

## Frontend Tests

### Missing Tests

| Test | What It Validates |
|------|-------------------|
| `test_access_page_admin_role_only_sees_my_roles` | Admin cannot see management tabs or gets appropriate error |
| `test_access_page_loading_error_empty_states` | All states render correctly |
| `test_create_member_modal_validation` | Form validation (username regex, password length) |
| `test_role_detail_owner_role_readonly` | Owner role permissions cannot be modified |
| `test_subscription_blocked_redirect` | past_due/suspended/canceled routes correctly |

## End-to-End Scenarios

| Scenario | Coverage |
|----------|----------|
| Full signup → verify → onboard → pay → activate → manage members | Complete happy path |
| Signup → abandon at checkout → resume | Onboarding step router resilience |
| Owner creates member → member logs in → member accesses correct data | Cross-role verification |
| Payment fails → past_due → grace period → access blocked | Billing state lifecycle |
| Owner suspends member → member tries to login → blocked | Suspension enforcement |

## Permission Boundary Tests

| Test | What It Validates |
|------|-------------------|
| `test_each_role_permission_matrix` | Verify all 10 roles × all permissions match rbac.py |
| `test_custom_permission_override` | RolePermissionOverride correctly grants/denies |
| `test_service_role_restrictions` | menu_qr only allows allowed roles |

## Tenant Isolation Tests

| Test | What It Validates |
|------|-------------------|
| `test_switch_business_forbidden_nonmember` | Cannot switch to business user doesn't belong to |
| `test_header_business_id_manipulation` | X-Business-ID with wrong business returns 403 |
| `test_employee_token_cross_business` | Employee token for business A rejected on business B endpoints |

## Suspended/Past_due/Canceled Access Tests

| Test | What It Validates |
|------|-------------------|
| `test_past_due_in_grace_allows_access` | Access allowed during grace period |
| `test_past_due_expired_grace_blocks` | Access blocked after grace expires |
| `test_suspended_blocks_all_access` | No endpoints accessible |
| `test_canceled_blocks_all_access` | No endpoints accessible |
| `test_login_possible_but_app_blocked` | User can login but gets blocked by enforcement |

---

# 13. Final Verdict

## Is the Current System Safe Enough for Production?

**Conditionally yes**, with the critical items addressed.

The tenant isolation is **strong** — properly enforced at queryset, permission, and serializer levels. The authentication system is **secure** — httpOnly cookies, constant-time token comparison, SHA-256 hashing, and JWT rotation. The RBAC system is **well-designed** — layered enforcement with backend authority.

However, **three critical issues must be fixed before commercial launch:**

1. **Seat limits for V2 tenants** (C1) — Currently no enforcement for the canonical subscription system. Direct revenue impact.
2. **Invitation flow** (C2) — Sharing plaintext credentials is unacceptable for a financial SaaS. At minimum, implement email-based invite with password setup link.
3. **Rollout flags must be enabled** (M2) — Production deployment must explicitly enable all 4 flags, especially `SUBSCRIPTION_STATUS_ENFORCEMENT` and `EMAIL_VERIFICATION_ENFORCEMENT`.

## What Must Be Fixed Before Launch

| Item | Effort | Why |
|------|--------|-----|
| Seat limits for V2 (C1) | 2-3 days | Revenue protection |
| Rollout flags enabled (M2) | 1 hour | Security enforcement |
| Admin/owner mismatch (H2) | 2 hours | Prevent broken admin UX |
| Dead code cleanup (L2, L3) | 1 hour | Code hygiene |

## What Can Wait

| Item | Why It Can Wait |
|------|-----------------|
| Invitation system (C2) | Owner can create users directly — suboptimal but functional. Needed before scaling. |
| Branch scope enforcement (H1) | Multi-branch is not widely used yet |
| Ownership transfer (M1) | Admin/DB workaround available |
| `billing.Subscription` cleanup (2.1) | Works as-is during migration period |
| Audit log UI (3.1) | Data is logged, just not exposed |

---

# Explicit Answers to Audit Questions

**Q1: After an owner pays, what exact code path turns them into an active owner of a business?**
MercadoPago `subscription_authorized_payment` webhook → `activate_subscription_from_invoice()` in [subscription_activator.py](services/api/src/apps/billing/subscription_activator.py) → atomically sets `SubscriptionV2.status=ACTIVE, is_active=True` → `Business.status=active` → `_ensure_owner_membership()` creates/confirms Membership. Activation is **webhook-driven only**, never on redirect.

**Q2: Who creates the business record and when?**
`_ensure_membership()` in [views.py:94](services/api/src/apps/accounts/views.py#L94), called at first login (LoginView) or first MeView call. Creates `Business(status='onboarding')` with no subscription.

**Q3: Who creates the membership record and when?**
Same as Q2 — `_ensure_membership()` creates `Membership(role='owner')` alongside the Business. For secondary users, `InternalUserService.create_internal_user()` creates it.

**Q4: Can an owner manually create a user account, or only invite by email?**
**Only direct creation** — `POST /owner/access/accounts/create/` with username, password, role. No invitation by email exists.

**Q5: Can invited users define their password through a first-access link?**
**No** — invitations are not implemented. Password is set by the owner at creation time.

**Q6: What happens if the invited email already belongs to an existing user?**
**N/A** — no invitation system. For `createMember()`, if the email exists, the backend returns a validation error (email uniqueness check).

**Q7: Are seat/member limits enforced on the backend?**
**Partially** — enforced only via `business.Subscription.max_seats` (legacy). Not enforced for V2-only tenants.

**Q8: Is /app/settings/access fully backed by secure API enforcement?**
**Yes for owner role** — all endpoints enforce role=owner on backend. **Mismatch for admin role** — frontend shows tabs admin can't use.

**Q9: Are role permissions tenant-specific or accidentally global?**
**Tenant-specific** — Membership is per (user, business). `RolePermissionOverride` is per (business, role, service). `permissions_for_service()` resolves per-business overrides.

**Q10: What happens to access when subscription state becomes past_due, suspended, or canceled?**
Access is blocked globally via `HasBusinessMembership` → `get_enforcement_decision()`. Only `past_due` within grace period allows access with renewal prompt. Users can log in but AppLayout redirects to state page.

**Q11: Is ownership transfer implemented or only planned?**
**NOT IMPLEMENTED** — no code exists. Last-owner guard prevents manual workarounds via API.

**Q12: Is there dead code from previous versions?**
**Yes**: `disable_account` V1 endpoint, `billing.Subscription` OneToOne model, `Business.default_service` field, stale VerifyEmailView query, wrong audit action label. None is dangerous but adds confusion.

**Q13: Are feature flags hiding incomplete behavior?**
**Yes** — all 4 rollout flags default to `False`. If enabled without preparation:
- `SUBSCRIPTION_STATUS_ENFORCEMENT`: Will block suspended-status accounts (requires migration 0013 complete)
- `EMAIL_VERIFICATION_ENFORCEMENT`: Will block unverified emails from commercial endpoints
- All flags gate production-intended behavior. Must be enabled for launch.

**Q14: Are there security issues that could let one business see/modify another business's users?**
**No evidence of cross-tenant leaks** — queryset filtering, serializer validation, and tenant-scoped tokens prevent cross-business access. Branch-scope enforcement within the same business family is the only gap.

---

# CTO Summary

Mirubro's access control system is architecturally sound with proper multi-layered enforcement: JWT auth → membership resolution → billing enforcement → RBAC permission check → tenant-scoped querysets. The code quality is high, with atomic operations, SELECT FOR UPDATE for race conditions, audit logging, and last-owner protection. Three items block production: (1) seat limits not enforced for the canonical V2 subscription system, (2) no invitation flow forcing insecure credential sharing, and (3) four rollout flags defaulting to off that must be explicitly enabled. The coexistence of three subscription systems is manageable but should be consolidated in a near-term sprint. Branch scope enforcement must be added before multi-branch goes live. Overall production-readiness: 72/100 — fixable to 90+ within a focused 2-week sprint.

# Product/Operations Summary

The system that controls who can access Mi Rubro and what they can do is well-built and secure. Each business's data is properly isolated — no business can see another's information. The owner can create user accounts, assign roles, change permissions, suspend or remove team members, and reset passwords. However, there is no email invitation system yet — the owner must create accounts with passwords and share them manually, which is inconvenient and insecure. Before launching commercially, we need to (1) ensure seat limits work correctly for all billing plans, (2) turn on security features that are currently disabled by default, and (3) ideally add email invitations so new team members can set their own passwords securely. The current system works for small teams managed directly by the owner, but scaling to larger businesses will require the invitation flow and additional admin-level permissions.
