# Mirubro Digital — Implementation Plan: Access & Roles Remediation

**Date:** 2026-04-01
**Source of truth:** `IMPL_SPEC_ACCESS_REMEDIATION.md` (v2)
**Status:** READY FOR CODING
**Delivery:** 4 PRs (3 required + 1 optional)

---

## 1. Final Frozen Decisions

These are fixed. No alternatives. No debate.

| Decision | Value |
|----------|-------|
| Account modes | `owner_managed`, `personal` — two values only |
| New fields on `AccountProfile` | `account_mode` (CharField, choices, default `owner_managed`), `must_change_password` (BooleanField, default `False`) |
| Derived helpers (not stored) | `can_change_password()` → `account_mode == 'personal'`, `can_self_reset()` → `account_mode == 'personal' AND user.email != ''` |
| Seat limit source | Canonical: `SubscriptionV2` via `resolve_subscription()` + `get_seat_limit()`. Fallback: legacy `business.Subscription`. Never V2-only. |
| OWNER_MANAGED password rules | Cannot change own password. Cannot self-reset. Never forced to change. Owner reset is final. |
| PERSONAL password rules | Can change own password. Can self-reset if email set. May be forced to change on first login (default: yes). Owner reset sets `must_change_password=True`. |
| Access management visibility | Owner-only. `canManage = summary.role === 'owner'` — no admin access. |
| Invitation flow | None. Owner creates directly. No self-registration for secondary users. No acceptance step. |
| Default for existing users | `account_mode='owner_managed'`, `must_change_password=False` — safe restrictive default via migration. |
| Recommended mode by role | admin/manager/analyst/contador → PERSONAL. cashier/staff/viewer/kitchen/salon → OWNER_MANAGED. UI pre-selects, owner overrides. |
| New endpoints | `POST /api/v1/auth/change-password/`, `POST /api/v1/auth/force-change-password/` |
| Gated endpoints | `ForgotPasswordView` → silently ignores non-PERSONAL. `ResetPasswordView` → rejects non-PERSONAL tokens. |
| Forced change page route | `/cambiar-contrasena` — in `(auth)` layout, outside `/app/`. |
| Layout guard | `must_change_password === true` → redirect to `/cambiar-contrasena` before any subscription check. |

---

## 2. PR Roadmap Overview

| PR | Name | Objective | Scope | Risk | Dependencies |
|----|------|-----------|-------|------|-------------|
| **PR-1** | Backend Foundation | All backend changes: fields, migration, endpoints, gates, seat limits, session, tests | 13 backend files, 1 new file, 2 new test files | Medium — touches auth views, seat limits, session payload | None |
| **PR-2** | Frontend Integration | All frontend changes: modal, table, types, layout guard, forced change page | 8 frontend files, 1 new page | Low — purely additive UI, reads new backend fields | PR-1 merged + deployed |
| **PR-3** | Hardening & Cleanup | Audit action fix, dead code removal, membership status sync | 3 backend files | Very low — isolated fixes | PR-1 merged |
| **PR-4** | Branch Scope (optional) | Queryset-level branch filtering across apps | Multiple apps, research-first | High — wide surface area, needs test coverage | PR-1 + PR-2 merged |

---

## 3. PR-1 — Backend Foundation

### 3.1 Ordered Task List

| Order | Task ID | Task | Files | Effort |
|-------|---------|------|-------|--------|
| 1 | B-1 | Create `billing/plans.py` with `PLAN_SEAT_LIMITS` + `get_seat_limit()` | `services/api/src/apps/billing/plans.py` (NEW) | S |
| 2 | B-2 | Add `account_mode` + `must_change_password` fields to `AccountProfile` | `services/api/src/apps/accounts/models.py` L17–58 | S |
| 3 | B-3 | Add `can_change_password()` + `can_self_reset()` helpers | `services/api/src/apps/accounts/models.py` (after fields) | S |
| 4 | B-4 | Generate and verify migration | `services/api/src/apps/accounts/migrations/0024_*.py` (auto) | S |
| 5 | B-5 | V2-aware seat check in `InternalUserService.create_internal_user()` | `services/api/src/apps/accounts/services.py` L247–262 | M |
| 6 | B-6 | V2-aware seat check in `check_seat_limit` signal | `services/api/src/apps/accounts/models.py` (pre_save signal) | M |
| 7 | B-7 | Accept `account_mode` + `force_password_change` in `InternalUserService` | `services/api/src/apps/accounts/services.py` L197–210 | S |
| 8 | B-8 | Add fields to `CreateMemberSerializer` | `services/api/src/apps/accounts/owner_serializers.py` | S |
| 9 | B-9 | Pass new fields through `create_member` view | `services/api/src/apps/accounts/owner_views.py` L530–545 | S |
| 10 | B-10 | Add `account_mode` to `UserAccountSerializer` + `accounts_list` response | `services/api/src/apps/accounts/owner_serializers.py` L42–53, `owner_views.py` L456–480 | S |
| 11 | B-11 | Add seat info to `accounts_list` response | `services/api/src/apps/accounts/owner_views.py` L430–480 | S |
| 12 | B-12 | Mode-aware `reset_password`: set `must_change_password` for PERSONAL only | `services/api/src/apps/accounts/owner_views.py` L640–660 | S |
| 13 | B-13 | Update `_session_payload()` with `account_mode` + `must_change_password` | `services/api/src/apps/accounts/views.py` L132–145 | S |
| 14 | B-14 | Create `ForceChangePasswordView` | `services/api/src/apps/accounts/views.py` (new class) | M |
| 15 | B-15 | Create `ChangePasswordView` | `services/api/src/apps/accounts/views.py` (new class) | M |
| 16 | B-16 | Gate `ForgotPasswordView` on `can_self_reset()` | `services/api/src/apps/accounts/views.py` L457–465 | S |
| 17 | B-17 | Gate `ResetPasswordView` on `account_mode == 'personal'` | `services/api/src/apps/accounts/views.py` L530–545 | S |
| 18 | B-18 | Register new URL routes | `services/api/src/apps/accounts/urls.py` | S |
| 19 | B-19 | Write seat limit tests | `services/api/src/apps/accounts/tests/test_seat_limits_v2.py` (NEW) | M |
| 20 | B-20 | Write account mode tests | `services/api/src/apps/accounts/tests/test_account_modes.py` (NEW) | M |

### 3.2 File-by-File Changes

#### `services/api/src/apps/billing/plans.py` (NEW)

```python
PLAN_SEAT_LIMITS: dict[str, int] = {
    'start': 2, 'starter': 2, 'plus': 5, 'pro': 10,
    'business': 20, 'enterprise': 100,
    'menu_qr': 2, 'menu_qr_lite': 2, 'menu_qr_visual': 3,
    'menu_qr_marca': 5, 'menu_qr_premium': 10, 'menu_qr_pro': 10,
}
DEFAULT_SEAT_LIMIT = 2

def get_seat_limit(plan_tier: str) -> int:
    return PLAN_SEAT_LIMITS.get(plan_tier, DEFAULT_SEAT_LIMIT)
```

#### `services/api/src/apps/accounts/models.py`

**B-2: Add fields after `email_verified` (currently line 51):**

```python
class AccountMode(models.TextChoices):
    OWNER_MANAGED = 'owner_managed', 'Administrada por el dueño'
    PERSONAL      = 'personal',      'Personal'

account_mode = models.CharField(
    max_length=16,
    choices=AccountMode.choices,
    default=AccountMode.OWNER_MANAGED,
)
must_change_password = models.BooleanField(default=False)
```

Place `AccountMode` as an inner class of `AccountProfile`, alongside `AccountStatus` and `InternalRole`.

**B-3: Add helpers after the existing token methods:**

```python
def can_change_password(self) -> bool:
    return self.account_mode == self.AccountMode.PERSONAL

def can_self_reset(self) -> bool:
    return (
        self.account_mode == self.AccountMode.PERSONAL
        and bool(self.user.email)
    )
```

**B-6: Update `check_seat_limit` signal to use V2-aware resolution:**

Replace the legacy `Subscription.objects.get(business=hq)` lookup with:
```python
from apps.billing.runtime import resolve_subscription
from apps.billing.plans import get_seat_limit

resolved = resolve_subscription(hq)
max_seats = get_seat_limit(resolved.plan) if resolved.source != 'none' else 0
```

Keep fallback: if `resolved.source == 'none'`, try legacy `Subscription.objects.get(business=hq)`.

#### `services/api/src/apps/accounts/services.py`

**B-5: V2-aware seat check in `create_internal_user()` (replace lines 247–262):**

Replace the existing `Subscription.objects.select_for_update().get(business=hq)` block with:

```python
from apps.billing.runtime import resolve_subscription
from apps.billing.plans import get_seat_limit

resolved = resolve_subscription(hq)
if resolved.source == 'v2':
    max_seats = get_seat_limit(resolved.plan)
elif resolved.source == 'legacy':
    try:
        sub = Subscription.objects.select_for_update().get(business=hq)
        max_seats = sub.max_seats if sub.max_seats > 0 else 0
    except Subscription.DoesNotExist:
        max_seats = 0
else:
    max_seats = 0

if max_seats > 0:
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))
    current_count = Membership.objects.filter(
        business__id__in=family_ids,
    ).count()
    if current_count >= max_seats:
        raise ValidationError(
            f'Límite de usuarios ({max_seats}) alcanzado para "{hq.name}". '
            f'Mejora tu plan para agregar más usuarios.'
        )
```

**B-7: Add parameters to `create_internal_user()` signature (line 197):**

Add after `email: str = ''`:
```python
account_mode: str = 'owner_managed',
force_password_change: bool = False,
```

Add validation immediately after role validation:
```python
if account_mode == 'owner_managed' and force_password_change:
    raise ValidationError(
        'Las cuentas administradas por el dueño no permiten forzar cambio de contraseña.'
    )
```

Update the `AccountProfile.objects.filter(user=user).update(...)` call (line 282):
```python
AccountProfile.objects.filter(user=user).update(
    account_status=AccountProfile.AccountStatus.ACTIVE,
    email_verified=True,
    account_mode=account_mode,
    must_change_password=force_password_change if account_mode == 'personal' else False,
)
```

Update audit log `details` dict to include `account_mode`:
```python
'account_mode': account_mode,
```

#### `services/api/src/apps/accounts/owner_serializers.py`

**B-8: Add fields to `CreateMemberSerializer`:**

Locate `CreateMemberSerializer` and add:
```python
account_mode = serializers.ChoiceField(
    choices=['owner_managed', 'personal'],
    default='owner_managed',
    required=False,
)
force_password_change = serializers.BooleanField(default=False, required=False)
```

**B-10: Add field to `UserAccountSerializer` (line 42):**

Add after `membership_status`:
```python
account_mode = serializers.CharField(default='owner_managed')
```

#### `services/api/src/apps/accounts/owner_views.py`

**B-9: Pass new fields in `create_member` view (line 540):**

```python
result = InternalUserService.create_internal_user(
    business=membership.business,
    first_name=data['first_name'],
    last_name=data['last_name'],
    username=data['username'],
    password=data['password'],
    role=data['role'],
    email=data.get('email', ''),
    account_mode=data.get('account_mode', 'owner_managed'),
    force_password_change=data.get('force_password_change', False),
    created_by_user=request.user,
    request=request,
)
```

**B-10: Add `account_mode` to `accounts_list` response (line 474):**

After `'last_login': user.last_login,` add:
```python
'account_mode': getattr(
    getattr(user, 'account_profile', None),
    'account_mode', 'owner_managed'
),
```

Also update the queryset to `select_related('user__account_profile')`:
```python
memberships = Membership.objects.filter(
    business__id__in=family_ids
).select_related('user', 'user__account_profile', 'business').order_by('user__email')
```

**B-11: Add seat info to `accounts_list` response:**

At the top of `accounts_list`, after resolving HQ:
```python
from apps.billing.runtime import resolve_subscription
from apps.billing.plans import get_seat_limit

resolved = resolve_subscription(hq)
if resolved.source == 'v2':
    max_seats = get_seat_limit(resolved.plan)
elif resolved.source == 'legacy':
    try:
        from apps.business.models import Subscription
        sub = Subscription.objects.get(business=hq)
        max_seats = sub.max_seats if sub.max_seats > 0 else 0
    except Subscription.DoesNotExist:
        max_seats = 0
else:
    max_seats = 0

current_count = Membership.objects.filter(business__id__in=family_ids).count()
```

Wrap the response:
```python
return Response({
    'accounts': serializer.data,
    'seat_info': {
        'current': current_count,
        'limit': max_seats,
        'source': resolved.source,
        'plan': resolved.plan,
    },
})
```

**B-12: Mode-aware `reset_password` (after line 650, after `target_user.save()`):**

```python
# For PERSONAL users, force password change on next login
profile = getattr(target_user, 'account_profile', None)
if profile and profile.account_mode == AccountProfile.AccountMode.PERSONAL:
    profile.must_change_password = True
    profile.save(update_fields=['must_change_password', 'updated_at'])
```

Add import at top: `from apps.accounts.models import AccountProfile`

#### `services/api/src/apps/accounts/views.py`

**B-13: Update `_session_payload()` (line 138–141):**

Add after `'email_verified'`:
```python
'account_mode': profile.account_mode if profile else 'personal',
'must_change_password': profile.must_change_password if profile else False,
```

Note: default `'personal'` for the fallback because self-registered owners (no profile edge) should behave as autonomous users. This case is theoretical — all owners get a profile via post_save signal.

**B-14: `ForceChangePasswordView` (new class, add before URL registration):**

```python
class ForceChangePasswordView(APIView):
    """POST /api/v1/auth/force-change-password/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile = getattr(request.user, 'account_profile', None)
        if not profile or not profile.must_change_password:
            return Response({'detail': 'No se requiere cambio de contraseña.'}, status=400)
        if profile.account_mode != AccountProfile.AccountMode.PERSONAL:
            return Response({'detail': 'Esta cuenta no permite cambio de contraseña.'}, status=403)

        current_password = request.data.get('current_password', '')
        new_password = request.data.get('new_password', '')

        if not current_password or not new_password:
            return Response({'detail': 'Se requiere la contraseña actual y la nueva.'}, status=400)
        if not request.user.check_password(current_password):
            return Response({'detail': 'La contraseña actual es incorrecta.'}, status=400)
        if len(new_password) < 8:
            return Response({'detail': 'La nueva contraseña debe tener al menos 8 caracteres.'}, status=400)

        request.user.set_password(new_password)
        request.user.save(update_fields=['password'])

        profile.must_change_password = False
        profile.save(update_fields=['must_change_password', 'updated_at'])

        # Re-issue JWT cookies
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(request.user)
        response = Response({'status': 'ok', 'message': 'Contraseña actualizada exitosamente.'})
        _set_auth_cookies(response, str(refresh.access_token), str(refresh))

        # Audit
        try:
            membership = request.user.memberships.select_related('business').first()
            if membership:
                AccessAuditLog.objects.create(
                    action='PASSWORD_FORCE_CHANGED',
                    actor=request.user, target_user=request.user,
                    business=membership.business,
                    details={'source': 'force_change'},
                    ip_address=_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                )
        except Exception:
            logger.exception("[ForceChangePasswordView] Audit failed")

        return response
```

**B-15: `ChangePasswordView` (new class):**

```python
class ChangePasswordView(APIView):
    """POST /api/v1/auth/change-password/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile = getattr(request.user, 'account_profile', None)
        if not profile or not profile.can_change_password():
            return Response(
                {'detail': 'Tu cuenta no permite cambio de contraseña. Contacta al propietario.'},
                status=403,
            )

        current_password = request.data.get('current_password', '')
        new_password = request.data.get('new_password', '')

        if not current_password or not new_password:
            return Response({'detail': 'Se requiere la contraseña actual y la nueva.'}, status=400)
        if not request.user.check_password(current_password):
            return Response({'detail': 'La contraseña actual es incorrecta.'}, status=400)
        if len(new_password) < 8:
            return Response({'detail': 'La nueva contraseña debe tener al menos 8 caracteres.'}, status=400)

        request.user.set_password(new_password)
        request.user.save(update_fields=['password'])

        # Re-issue JWT cookies
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(request.user)
        response = Response({'status': 'ok', 'message': 'Contraseña actualizada exitosamente.'})
        _set_auth_cookies(response, str(refresh.access_token), str(refresh))

        # Audit
        try:
            membership = request.user.memberships.select_related('business').first()
            if membership:
                AccessAuditLog.objects.create(
                    action='PASSWORD_CHANGED',
                    actor=request.user, target_user=request.user,
                    business=membership.business,
                    details={'source': 'self_service'},
                    ip_address=_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                )
        except Exception:
            logger.exception("[ChangePasswordView] Audit failed")

        return response
```

**B-16: Gate `ForgotPasswordView` (insert after line 462, after `profile, _ = AccountProfile...`):**

```python
# OWNER_MANAGED or PERSONAL-without-email: silently ignore (anti-enumeration)
if not profile.can_self_reset():
    return Response({
        'status': 'ok',
        'message': 'Si el email está registrado, recibirás un enlace para restablecer tu contraseña.',
    })
```

This goes BEFORE `token = profile.generate_password_reset_token()`.

**B-17: Gate `ResetPasswordView` (insert after profile user lookup, before `user.set_password`):**

```python
if profile.account_mode != AccountProfile.AccountMode.PERSONAL:
    return Response(
        {'detail': 'El enlace para restablecer la contraseña no es válido.'},
        status=status.HTTP_400_BAD_REQUEST,
    )
```

After password set, clear `must_change_password` if set:
```python
if profile.must_change_password:
    profile.must_change_password = False
    profile.save(update_fields=['must_change_password', 'updated_at'])
```

#### `services/api/src/apps/accounts/urls.py`

**B-18: Add two new imports + routes:**

Imports:
```python
from .views import (
    ...existing imports...,
    ForceChangePasswordView,
    ChangePasswordView,
)
```

Routes (add before the onboarding block):
```python
path('change-password/', ChangePasswordView.as_view(), name='auth-change-password'),
path('force-change-password/', ForceChangePasswordView.as_view(), name='auth-force-change-password'),
```

### 3.3 Migration Requirements

- Auto-generate: `python manage.py makemigrations accounts`
- Expected migration number: `0024_accountprofile_account_mode_must_change_password`
- Two new columns on `accounts_accountprofile`:
  - `account_mode VARCHAR(16) NOT NULL DEFAULT 'owner_managed'`
  - `must_change_password BOOLEAN NOT NULL DEFAULT FALSE`
- Safe: both have defaults, no data migration needed.
- Verify: `python manage.py migrate --plan` should show only this migration.

### 3.4 API Contract Changes

#### Modified Endpoints

| Endpoint | Change |
|----------|--------|
| `POST /api/v1/owner/access/accounts/create/` | **Request:** accepts optional `account_mode` (default `'owner_managed'`) and `force_password_change` (default `false`). **Response:** unchanged. |
| `GET /api/v1/owner/access/accounts/` | **Response:** now returns `{ accounts: [...], seat_info: { current, limit, source, plan } }` instead of flat array. Each account object gains `account_mode` field. |
| `POST /api/v1/owner/access/accounts/:id/reset-password/` | **Response:** unchanged. **Side effect:** sets `must_change_password=true` for PERSONAL users. |
| `POST /api/v1/auth/forgot-password/` | **Response:** unchanged. **Behavior:** OWNER_MANAGED users silently ignored (no token, no email). |
| `POST /api/v1/auth/reset-password/` | **Response:** 400 for non-PERSONAL token holders. Clears `must_change_password` on success. |
| `POST /api/v1/auth/login/` | **Response:** `user` object in session gains `account_mode` and `must_change_password`. |
| `GET /api/v1/auth/me/` | **Response:** same session payload change as login. |

#### New Endpoints

| Endpoint | Method | Auth | Body | Response |
|----------|--------|------|------|----------|
| `/api/v1/auth/change-password/` | POST | `IsAuthenticated` | `{ current_password, new_password }` | `{ status, message }` or 403 |
| `/api/v1/auth/force-change-password/` | POST | `IsAuthenticated` | `{ current_password, new_password }` | `{ status, message }` + new cookies, or 400/403 |

### 3.5 Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| `account_mode='owner_managed'` + `force_password_change=True` | Rejected at creation time with 400 |
| OWNER_MANAGED user hits `/change-password/` | 403 |
| OWNER_MANAGED user's email used in `/forgot-password/` | 200 (anti-enum) but no token generated |
| PERSONAL user without email hits `/forgot-password/` | 200 (anti-enum) but no token generated |
| Owner resets PERSONAL user's password | `must_change_password=True` set |
| Owner resets OWNER_MANAGED user's password | `must_change_password` stays `False` |
| PERSONAL user completes forced change | `must_change_password=False`, new JWT cookies issued |
| PERSONAL user self-resets via email token | `must_change_password` cleared if it was set |
| User has no `account_profile` (orphan) | All mode checks default to safe values — `can_change_password()=False`, session falls back to `'personal'` for owner compatibility |
| Seat limit check with no V2 and no legacy | `max_seats=0` → no limit enforced (allows creation) |
| V2 source with `plan=''` (empty) | `get_seat_limit('')` returns `DEFAULT_SEAT_LIMIT` (2) |
| `accounts_list` response shape change | Frontend (PR-2) must handle new `{ accounts, seat_info }` shape |

### 3.6 Acceptance Criteria

- [ ] `python manage.py migrate` runs cleanly
- [ ] Creating a member with `account_mode='owner_managed'` does NOT set `must_change_password`
- [ ] Creating a member with `account_mode='personal', force_password_change=True` sets `must_change_password=True`
- [ ] Creating with `account_mode='owner_managed', force_password_change=True` returns 400
- [ ] `accounts_list` response includes `seat_info` and per-account `account_mode`
- [ ] Owner reset password on PERSONAL user sets `must_change_password=True`
- [ ] Owner reset password on OWNER_MANAGED user does NOT set `must_change_password`
- [ ] Login/me session includes `account_mode` and `must_change_password` in `user` object
- [ ] `POST /change-password/` works for PERSONAL, returns 403 for OWNER_MANAGED
- [ ] `POST /force-change-password/` works only when `must_change_password=True` AND `account_mode='personal'`
- [ ] `POST /forgot-password/` with OWNER_MANAGED user email → 200 but no email sent
- [ ] `POST /reset-password/` with token from OWNER_MANAGED user → 400
- [ ] Seat limit uses V2 plan when V2 subscription exists
- [ ] Seat limit falls back to legacy when no V2 exists
- [ ] All 30 tests in `test_seat_limits_v2.py` + `test_account_modes.py` pass

### 3.7 Rollback Considerations

- Migration adds columns with defaults — rollback is `python manage.py migrate accounts 0023`
- New endpoints have new URL paths — removing routes is sufficient to disable
- `_session_payload` changes add fields — frontend ignores unknown fields (safe if PR-2 not yet deployed)
- `accounts_list` response shape change is **breaking** for current frontend — coordinate with PR-2 or introduce a `?v=2` query param. **Recommendation:** ship PR-1 with backward-compatible response (keep flat array as default, add seat_info as top-level if query param `include_seat_info=1` is set). PR-2 sends the param.

**Revised approach for `accounts_list`:**
```python
# Backward-compatible: only wrap if param is set
include_seat_info = request.query_params.get('include_seat_info') == '1'
if include_seat_info:
    return Response({'accounts': serializer.data, 'seat_info': {...}})
return Response(serializer.data)
```

This lets PR-1 merge without breaking the existing frontend. PR-2 adds `?include_seat_info=1`.

---

## 4. PR-2 — Frontend Integration

### 4.1 Ordered Task List

| Order | Task ID | Task | Files | Effort |
|-------|---------|------|-------|--------|
| 1 | F-1 | Update `Session` type with `account_mode` + `must_change_password` | `apps/web/src/lib/auth/types.ts` L46–50 | S |
| 2 | F-2 | Update `UserAccount` type with `account_mode` | `apps/web/src/types/owner-access.ts` L30–41 | S |
| 3 | F-3 | Update `CreateMemberPayload` with `account_mode` + `force_password_change` | `apps/web/src/types/owner-access.ts` L101–108 | S |
| 4 | F-4 | Update API client to send `include_seat_info=1` + type for seat info | `apps/web/src/lib/api/owner-access.ts` L52–53 | S |
| 5 | F-5 | Add account mode selector + force change checkbox to `CreateMemberModal` | `apps/web/src/components/app/owner-access/create-member-modal.tsx` | M |
| 6 | F-6 | Add `account_mode` badge to `AccountsTable` | `apps/web/src/components/app/owner-access/accounts-table.tsx` | S |
| 7 | F-7 | Add `SeatInfoBar` component | `apps/web/src/components/app/owner-access/seat-info-bar.tsx` (NEW) | S |
| 8 | F-8 | Wire seat info in access page | `apps/web/src/app/app/settings/access/page.tsx` | S |
| 9 | F-9 | Fix `canManage` to owner-only | `apps/web/src/app/app/settings/access/page.tsx` L41 | S |
| 10 | F-10 | Create forced password change page | `apps/web/src/app/(auth)/cambiar-contrasena/page.tsx` (NEW) | M |
| 11 | F-11 | Add layout guard for `must_change_password` | `apps/web/src/app/app/layout.tsx` L43–44 | S |

### 4.2 File-by-File Changes

#### `apps/web/src/lib/auth/types.ts`

**F-1: Add fields to `Session.user` (after line 50, after `email_verified: boolean`):**

```typescript
user: {
    id: number;
    email: string;
    name: string;
    email_verified: boolean;
    account_mode: 'owner_managed' | 'personal';  // NEW
    must_change_password: boolean;                 // NEW
};
```

#### `apps/web/src/types/owner-access.ts`

**F-2: Add field to `UserAccount` (after `membership_status`):**

```typescript
account_mode: 'owner_managed' | 'personal';
```

**F-3: Add fields to `CreateMemberPayload` (after `email?`):**

```typescript
account_mode?: 'owner_managed' | 'personal';
force_password_change?: boolean;
```

**Add type for seat info response:**

```typescript
export interface SeatInfo {
    current: number;
    limit: number;
    source: string;
    plan: string;
}

export interface AccountsListResponse {
    accounts: UserAccount[];
    seat_info: SeatInfo;
}
```

#### `apps/web/src/lib/api/owner-access.ts`

**F-4: Update `getAccounts` to send param and use new return type:**

```typescript
getAccounts: () => apiGet<AccountsListResponse>(`${BASE}/accounts/?include_seat_info=1`),
```

Import `AccountsListResponse` from types.

#### `apps/web/src/components/app/owner-access/create-member-modal.tsx`

**F-5: Add state + UI for account mode (after line 27, after `role` state):**

New state:
```typescript
const [accountMode, setAccountMode] = useState<'owner_managed' | 'personal'>('owner_managed');
const [forcePasswordChange, setForcePasswordChange] = useState(false);
```

Add `useEffect` for auto-selecting mode based on role:
```typescript
import { useEffect } from 'react';

useEffect(() => {
    const personalRoles = ['admin', 'manager', 'analyst', 'contador'];
    const recommended = personalRoles.includes(role) ? 'personal' : 'owner_managed';
    setAccountMode(recommended);
    setForcePasswordChange(recommended === 'personal');
}, [role]);
```

Add UI block after the Role `<select>` and before the Email field:
- Two card-style buttons for "Administrada" / "Personal"
- Conditional checkbox for force password change (only when `accountMode === 'personal'`)
- (See spec §4.1 for exact markup)

Update `handleSubmit` payload:
```typescript
const response = await ownerAccessApi.createMember({
    first_name: firstName.trim(),
    last_name: lastName.trim(),
    username: username.trim(),
    password,
    role,
    ...(email.trim() ? { email: email.trim() } : {}),
    account_mode: accountMode,
    force_password_change: forcePasswordChange,
});
```

Update `handleClose` to reset new state:
```typescript
setAccountMode('owner_managed');
setForcePasswordChange(false);
```

#### `apps/web/src/components/app/owner-access/accounts-table.tsx`

**F-6: Add mode badge column:**

Add `<th>` for "Modo" after the "Rol" column header.
Add badge `<td>` per row:
```tsx
<td>
  <span className={`text-xs px-2 py-0.5 rounded-full ${
    account.account_mode === 'personal'
      ? 'bg-indigo-100 text-indigo-700'
      : 'bg-slate-100 text-slate-600'
  }`}>
    {account.account_mode === 'personal' ? 'Personal' : 'Administrada'}
  </span>
</td>
```

#### `apps/web/src/components/app/owner-access/seat-info-bar.tsx` (NEW)

**F-7:** Simple bar showing `{current}/{limit} usuarios` with a progress indicator. Props: `current: number`, `limit: number`, `plan: string`.

If `limit === 0`, show "Sin límite de usuarios".
If `current >= limit`, show warning styling.

#### `apps/web/src/app/app/settings/access/page.tsx`

**F-8:** Import and render `SeatInfoBar` above `AccountsTable`. Pass seat info data from the `getAccounts()` response.

**F-9: Fix `canManage` (line 41):**

```typescript
// BEFORE:
const canManage = summary.role === 'owner' || summary.role === 'admin';

// AFTER:
const canManage = summary.role === 'owner';
```

#### `apps/web/src/app/(auth)/cambiar-contrasena/page.tsx` (NEW)

**F-10:** Page with:
- Lock icon + "Cambiar contraseña" heading
- Info text: "Tu propietario te creó una contraseña temporal. Por seguridad, elegí una contraseña propia."
- Form: current password, new password, confirm new password
- Client-side validation: new password ≥ 8 chars, confirm matches new
- Submit → `POST /api/v1/auth/force-change-password/`
- On success → `router.push('/app')` (or `redirect('/app')`)
- On error → show error inline
- No skip button. No back link.

Must work with the `(auth)` layout — ensure it exists and is minimal (no AppShell sidebar).

#### `apps/web/src/app/app/layout.tsx`

**F-11: Add guard after session check (after line 42, after `const resolvedSession`):**

```typescript
// Forced password change — intercept before subscription/billing checks
if (resolvedSession.user.must_change_password) {
    redirect('/cambiar-contrasena');
}
```

### 4.3 State / Data Flow

```
getSession() → resolvedSession.user.must_change_password
  └─ if true → redirect('/cambiar-contrasena')
  └─ if false → normal app flow

getAccounts() → { accounts: UserAccount[], seat_info: SeatInfo }
  └─ AccountsTable reads accounts (+ account_mode badge)
  └─ SeatInfoBar reads seat_info

CreateMemberModal
  └─ role state → useEffect → accountMode + forcePasswordChange defaults
  └─ user can override accountMode manually
  └─ forcePasswordChange checkbox visible only when accountMode === 'personal'
  └─ submit sends account_mode + force_password_change to backend
```

### 4.4 Validation Rules

| Field | Rule | Error |
|-------|------|-------|
| `accountMode` | Required, one of `'owner_managed'` / `'personal'` | N/A (buttons, always selected) |
| `forcePasswordChange` | Only visible when `accountMode === 'personal'` | N/A (checkbox) |
| Forced change page: current password | Required, non-empty | "Ingresá tu contraseña actual" |
| Forced change page: new password | ≥ 8 chars | "La nueva contraseña debe tener al menos 8 caracteres" |
| Forced change page: confirm | Must match new password | "Las contraseñas no coinciden" |

### 4.5 Acceptance Criteria

- [ ] `CreateMemberModal` shows account mode selector after role
- [ ] Selecting "admin" auto-selects PERSONAL mode
- [ ] Selecting "cashier" auto-selects OWNER_MANAGED mode
- [ ] Force password change checkbox visible only for PERSONAL, hidden for OWNER_MANAGED
- [ ] Submit includes `account_mode` and `force_password_change` in payload
- [ ] `AccountsTable` shows "Administrada" / "Personal" badge per row
- [ ] `SeatInfoBar` shows current/limit usage
- [ ] `SeatInfoBar` shows warning when at limit
- [ ] Access management tabs (business-roles, accounts, employees) hidden for non-owner users
- [ ] Login as user with `must_change_password=true` → redirected to `/cambiar-contrasena`
- [ ] `/cambiar-contrasena` form validates current password, new password ≥ 8, confirm match
- [ ] Successful password change → redirected to `/app`
- [ ] After change, `must_change_password` is `false` in subsequent session
- [ ] Login as OWNER_MANAGED user → no redirect, no change-password UI

### 4.6 Regression Risks

| Risk | Mitigation |
|------|------------|
| `getAccounts()` response shape change breaks table | Use `include_seat_info=1` flag — backend returns old shape without it |
| `must_change_password` guard triggers for owners | Owners never have `must_change_password=True` — backend enforces this. Verify with test. |
| `(auth)` layout doesn't exist or has different structure | Verify `apps/web/src/app/(auth)/` exists before creating the page. If it doesn't, create the directory + a minimal layout. |
| Modal state not resetting after close | `handleClose` explicitly resets `accountMode` and `forcePasswordChange` |
| `role` changes after mode override → unexpected auto-select | `useEffect([role])` only runs on role change, not on mode change. User's manual mode override persists until role changes. |

---

## 5. PR-3 — Hardening & Cleanup

### 5.1 Ordered Task List

| Order | Task ID | Task | Files | Effort |
|-------|---------|------|-------|--------|
| 1 | H-1 | Fix `ForgotPasswordView` audit action `PASSWORD_RESET_CONFIRMED` → `PASSWORD_RESET_REQUESTED` | `services/api/src/apps/accounts/views.py` L477 | S |
| 2 | H-2 | Remove `VerifyEmailView` unreachable first query (dead code) | `services/api/src/apps/accounts/views.py` (VerifyEmailView) | S |
| 3 | H-3 | Sync `Membership.status` in `disable_account()` | `services/api/src/apps/accounts/owner_views.py` (disable_account function) | S |
| 4 | H-4 | Add `PASSWORD_FORCE_CHANGED` and `PASSWORD_CHANGED` to audit action choices (if ActionType enum exists) | `services/api/src/apps/accounts/models.py` (AccessAuditLog) | S |

### 5.2 File-by-File Changes

#### `services/api/src/apps/accounts/views.py`

**H-1:** Line 477:
```python
# BEFORE:
action='PASSWORD_RESET_CONFIRMED',  # "requested" intent
# AFTER:
action='PASSWORD_RESET_REQUESTED',
```

**H-2:** Locate `VerifyEmailView` — find the unreachable query that tries `AccountProfile.objects.get(email_verification_token_hash=...)` before the actual token verification. Remove the dead branch.

#### `services/api/src/apps/accounts/owner_views.py`

**H-3:** In `disable_account()`, after `target_user.is_active = False; target_user.save()`, add:
```python
target_membership.status = Membership.Status.SUSPENDED
target_membership.save(update_fields=['status', 'updated_at'])
```

And in the re-enable branch (if `target_user.is_active` was already False):
```python
target_membership.status = Membership.Status.ACTIVE
target_membership.save(update_fields=['status', 'updated_at'])
```

### 5.3 Acceptance Criteria

- [ ] Triggering forgot-password creates audit log with action `PASSWORD_RESET_REQUESTED`
- [ ] `VerifyEmailView` has no unreachable code paths
- [ ] Disabling a user sets `Membership.status = 'suspended'`
- [ ] Re-enabling a user sets `Membership.status = 'active'`
- [ ] Existing tests still pass

### 5.4 Deployment Notes

- No migration required.
- Can deploy independently of PR-1/PR-2 once PR-1 is merged.
- Zero user-facing behavior change (audit action string is internal).
- Safe to merge at any time after PR-1.

---

## 6. PR-4 — Branch Scope Follow-Up (Optional)

### 6.1 What Remains Out of Scope from PR-1–PR-3

- `Membership.branch_scope` field exists but is never enforced in querysets
- No branch-scoped memberships exist in production yet
- `_try_resolve_inherited_membership()` in `access.py` allows HQ owners to access branch resources, but branch users are not restricted to their branch data

### 6.2 Exact Queryset/Filtering Work Needed

1. Create `get_branch_filter(membership)` utility in `services/api/src/apps/accounts/access.py`:
   - If `membership.branch_scope` is NULL or empty → return `Q()` (no filter)
   - If set → return `Q(business_id__in=branch_scope_ids)`

2. Apply the filter in every queryset that returns business-scoped data:
   - `catalog/views.py` — product list, category list
   - `sales/views.py` — sales list, sale detail
   - `cash/views.py` — register list, session list
   - `inventory/views.py` — stock movements
   - `customers/views.py` — customer list
   - `orders/views.py` — order list
   - `invoices/views.py` — invoice list
   - `treasury/views.py` — expense list, account list

3. Write integration tests verifying a branch-scoped user cannot see HQ-only data.

### 6.3 Affected Modules/Apps

All 8 data apps listed above. `reports/` is read-only and should respect the same filters.

### 6.4 Why Isolated in a Separate PR

- Wide surface area: 10+ view files across 8+ apps
- No branch-scoped memberships exist in production — zero current risk
- Requires careful per-app audit to find all unfiltered querysets
- Highest regression risk of all 4 PRs
- Can be scheduled for a later sprint without blocking production readiness

---

## 7. API Diff Summary

| Endpoint | Status | Request Changes | Response Changes | Auth/Perm | Frontend Impact |
|----------|--------|-----------------|------------------|-----------|-----------------|
| `POST /auth/login/` | Modified | None | `user` gains `account_mode`, `must_change_password` | Unchanged | Read new fields for layout guard |
| `GET /auth/me/` | Modified | None | Same as login | Unchanged | Same |
| `POST /auth/forgot-password/` | Modified | None | None (response unchanged) | Unchanged | None — silent backend gate |
| `POST /auth/reset-password/` | Modified | None | 400 for non-PERSONAL tokens | Unchanged | Edge case: OWNER_MANAGED users see "link invalid" |
| `POST /auth/change-password/` | **New** | `{ current_password, new_password }` | `{ status, message }` or 403 | `IsAuthenticated` | P1 settings page |
| `POST /auth/force-change-password/` | **New** | `{ current_password, new_password }` | `{ status, message }` + new cookies | `IsAuthenticated` | Forced change page |
| `GET /owner/access/accounts/` | Modified | Optional `?include_seat_info=1` | With param: `{ accounts, seat_info }`. Without: flat array (backward compat). Each account gains `account_mode`. | `IsAuthenticated + owner` | Frontend sends param in PR-2 |
| `POST /owner/access/accounts/create/` | Modified | Optional `account_mode`, `force_password_change` | Unchanged | `IsAuthenticated + owner` | Modal sends new fields |
| `POST /owner/access/accounts/:id/reset-password/` | Modified | None | None | `IsAuthenticated + owner` | Side effect: PERSONAL gets `must_change_password=true` |
| `GET /owner/access/summary/` | Unchanged | — | — | Unchanged | — |
| `GET /owner/access/roles/` | Unchanged | — | — | Unchanged | — |
| `GET /owner/access/roles/:role/` | Unchanged | — | — | Unchanged | — |
| `PUT /owner/access/roles/:role/permissions/` | Unchanged | — | — | Unchanged | — |
| `POST /owner/access/accounts/:id/disable/` | Unchanged (PR-3 adds membership sync) | — | — | Unchanged | — |

---

## 8. Migration and Data Backfill Plan

### Migration Order

1. `accounts 0024` — adds `account_mode` (VARCHAR 16, default `'owner_managed'`) and `must_change_password` (BOOLEAN, default `FALSE`) to `accounts_accountprofile`.
2. No other migrations required.

### Are Defaults Enough?

**Yes.** Both fields have safe defaults:
- `account_mode = 'owner_managed'` — all existing secondary users become OWNER_MANAGED (restrictive, correct)
- `must_change_password = False` — no existing user is forced to change password (no disruption)

### Existing Users Default to OWNER_MANAGED

**Correct.** All users created before this feature were created without mode awareness. Making them OWNER_MANAGED is the safest option because:
- No self-service password change was previously possible (no endpoint existed)
- No forced change was previously possible (no field existed)
- This preserves the status quo — no behavior change for existing users

### Manual Review Script for Trusted Admins/Managers

**Recommended but not blocking.** After PR-1 deploys, the owner can manually switch trusted existing users to PERSONAL via a future "Edit user mode" feature (PR-3 or later).

For now, provide a Django management command for operators:

```python
# services/api/src/apps/accounts/management/commands/set_account_modes.py
# Usage: python manage.py set_account_modes --business-id=123 --roles=admin,manager --mode=personal --dry-run

# This is a P3 convenience — not required for PR-1.
```

**Recommendation:** Do NOT auto-migrate existing admins/managers to PERSONAL. Let the business owner explicitly choose. The owner may have created admin accounts that are actually shared terminals.

---

## 9. Test Plan by PR

### PR-1 Tests

#### Backend Unit Tests

**File: `services/api/src/apps/accounts/tests/test_seat_limits_v2.py` (NEW)**

```
test_create_member_v2_sub_within_limit          — V2 plan='pro' (10 seats), 5 existing → success
test_create_member_v2_sub_at_limit              — V2 plan='pro' (10 seats), 10 existing → ValidationError
test_create_member_v2_sub_no_v2_falls_to_legacy — No V2, legacy with max_seats=5, 4 existing → success
test_create_member_no_subscription_at_all        — No V2, no legacy → success (no limit enforced)
test_create_member_enterprise_high_limit         — V2 plan='enterprise' (100 seats) → success
test_seat_check_uses_hq_family_count             — Branch members counted against HQ limit
test_seat_check_signal_v2_blocks                 — pre_save signal also uses V2 when available
```

**File: `services/api/src/apps/accounts/tests/test_account_modes.py` (NEW)**

```
# Creation
test_create_member_owner_managed_default           — No mode param → account_mode='owner_managed'
test_create_member_personal_with_force_change       — mode='personal', force=True → must_change_password=True
test_create_member_personal_without_force_change    — mode='personal', force=False → must_change_password=False
test_create_member_owner_managed_rejects_force      — mode='owner_managed', force=True → 400
test_create_member_session_includes_account_mode    — Login after creation → session.user.account_mode present

# OWNER_MANAGED password restrictions
test_owner_managed_cannot_change_own_password       — POST /change-password/ → 403
test_owner_managed_forgot_password_silently_ignored — POST /forgot-password/ → 200, no token generated
test_owner_managed_reset_token_rejected             — POST /reset-password/ with OM token → 400

# PERSONAL password self-service
test_personal_can_change_own_password               — POST /change-password/ → 200, password changed
test_personal_can_self_reset_with_email             — POST /forgot-password/ → token generated
test_personal_cannot_self_reset_without_email        — POST /forgot-password/ → 200, no token
test_personal_force_change_clears_flag              — POST /force-change-password/ → must_change=False

# Owner reset interactions
test_owner_reset_personal_sets_must_change          — must_change_password=True after reset
test_owner_reset_owner_managed_no_must_change        — must_change_password stays False
test_force_change_view_rejects_owner_managed         — POST /force-change-password/ for OM → 403

# Audit
test_password_force_changed_audit_log               — Verify ACTION='PASSWORD_FORCE_CHANGED'
test_password_changed_audit_log                     — Verify ACTION='PASSWORD_CHANGED'

# Session payload
test_session_payload_includes_account_mode          — /auth/me/ returns account_mode
test_session_payload_includes_must_change_password   — /auth/me/ returns must_change_password
```

#### Backend Integration Tests

```
# In test_account_modes.py (integration section)
test_full_flow_personal_create_login_force_change   — Create PERSONAL → login → must_change=True → force-change → login again → must_change=False
test_full_flow_owner_managed_create_login_no_force   — Create OM → login → must_change=False → no redirect needed
test_seat_limit_blocks_after_plan_downgrade          — V2 plan downgrades from pro to start → next creation blocked
```

### PR-2 Tests

#### Frontend Tests (Vitest)

```
# File: apps/web/src/__tests__/create-member-modal.test.tsx
test_role_change_updates_account_mode_default        — Selecting 'admin' sets mode to 'personal'
test_role_change_to_cashier_sets_owner_managed        — Selecting 'cashier' sets mode to 'owner_managed'
test_force_password_checkbox_hidden_for_owner_managed — Checkbox not rendered when mode='owner_managed'
test_force_password_checkbox_visible_for_personal     — Checkbox rendered and checked by default
test_submit_includes_account_mode_and_force_change    — Payload includes both new fields

# File: apps/web/src/__tests__/accounts-table.test.tsx
test_account_mode_badge_renders_personal             — PERSONAL account shows "Personal" badge
test_account_mode_badge_renders_administrada          — OM account shows "Administrada" badge
```

#### E2E Scenarios (manual or Playwright)

```
e2e_create_personal_admin_forced_change
  1. Owner logs in
  2. Goes to Settings > Acceso
  3. Creates admin user with PERSONAL mode, force change checked
  4. Logs out
  5. Logs in as new admin
  6. Sees forced password change page
  7. Changes password
  8. Lands on /app dashboard

e2e_create_owner_managed_cashier_no_force
  1. Owner logs in
  2. Creates cashier with OWNER_MANAGED mode
  3. Logs out
  4. Logs in as cashier
  5. Lands directly on /app (no forced change)
  6. No "Change password" in settings

e2e_seat_limit_block
  1. Owner on START plan (2 seats)
  2. Owner already has 1 other member (2 total)
  3. Tries to create 3rd → sees error
  4. Sees SeatInfoBar showing 2/2
```

### PR-3 Tests

```
# In existing test files or new test_hardening.py
test_forgot_password_audit_action_is_requested       — Action='PASSWORD_RESET_REQUESTED'
test_disable_account_syncs_membership_suspended       — Membership.status='suspended' after disable
test_enable_account_syncs_membership_active            — Membership.status='active' after enable
```

---

## 10. Definition of Done

### PR-1 — Backend Foundation

**Must be true to merge:**
- [ ] All 27+ new tests pass
- [ ] Existing test suite passes (`test_internal_users.py`, `test_owner_access.py`, `test_v2_first_session.py`)
- [ ] Migration applies and rolls back cleanly
- [ ] No regressions in login/register/me/logout flows
- [ ] `flake8` / linter passes on changed files

**Must be manually validated in staging:**
- [ ] Create member API accepts `account_mode` + `force_password_change`
- [ ] Login session includes new fields
- [ ] `/forgot-password/` with OM user's email → 200, no email received
- [ ] `/reset-password/` with OM token → 400
- [ ] `/change-password/` with OM user → 403
- [ ] `/force-change-password/` with PERSONAL + `must_change=true` → 200
- [ ] Owner reset password on PERSONAL user → check DB `must_change_password=true`
- [ ] Seat limit blocks creation when at plan capacity

**Logs/behaviors to check after deploy:**
- [ ] No 500 errors in auth endpoints
- [ ] Audit log entries created for new actions (PASSWORD_CHANGED, PASSWORD_FORCE_CHANGED)
- [ ] Existing frontend still works (backward-compatible `accounts_list`)

### PR-2 — Frontend Integration

**Must be true to merge:**
- [ ] All frontend tests pass
- [ ] No TypeScript errors
- [ ] `canManage` restricted to owner-only
- [ ] Create modal includes account mode selector
- [ ] Forced change page renders and submits correctly

**Must be manually validated in staging:**
- [ ] Full e2e: create PERSONAL admin → login as admin → forced change → lands on /app
- [ ] Full e2e: create OWNER_MANAGED cashier → login as cashier → no forced change, no change-password option
- [ ] Seat info bar shows correct counts
- [ ] Admin user cannot see business-roles/accounts/employees tabs

**Logs/behaviors to check after deploy:**
- [ ] No console errors in browser
- [ ] No infinite redirect loops on forced change page
- [ ] Session refresh after forced change works (new JWT cookies)

### PR-3 — Hardening

**Must be true to merge:**
- [ ] Changed tests pass
- [ ] Audit action string fixed
- [ ] Disable/enable syncs membership status

**Must be manually validated in staging:**
- [ ] Disable user → check DB Membership.status = 'suspended'
- [ ] Re-enable → check DB Membership.status = 'active'

---

## 11. Implementation Notes for the Coding Agent

### Critical Warnings

1. **DO NOT use legacy `Subscription` as primary seat source.** Always try `resolve_subscription()` first. Legacy is fallback only when `resolved.source != 'v2'`.

2. **DO NOT allow OWNER_MANAGED users to self-change password.** Every password self-service endpoint (`ChangePasswordView`, `ForceChangePasswordView`, `ForgotPasswordView`, `ResetPasswordView`) must check `account_mode`. The check is NOT optional.

3. **DO NOT set `must_change_password=True` for OWNER_MANAGED users.** This field must only be `True` when `account_mode == 'personal'`. Enforce this invariant in:
   - `InternalUserService.create_internal_user()` — reject if `account_mode='owner_managed'` and `force_password_change=True`
   - `reset_password()` owner view — only set `must_change_password=True` for PERSONAL targets
   - `ForceChangePasswordView` — double-check mode before allowing change

4. **DO NOT expose management tabs to admin users.** The fix is: `canManage = summary.role === 'owner'`. Remove `|| summary.role === 'admin'`.

5. **DO NOT break owner-created legacy users.** Migration defaults all existing users to `account_mode='owner_managed'` and `must_change_password=False`. This means zero behavior change for existing users. Do not run a data migration that changes these values.

6. **Keep changes backward-compatible.** The `accounts_list` endpoint must return the flat array by default. Only wrap in `{ accounts, seat_info }` when `include_seat_info=1` is passed. This prevents breaking the existing frontend before PR-2 is deployed.

7. **Re-issue JWT cookies after password change.** Both `ForceChangePasswordView` and `ChangePasswordView` must call `_set_auth_cookies()` with new tokens after `set_password()`. Otherwise the user's session becomes invalid and they get logged out.

8. **Use `update_fields` on all `.save()` calls.** Never call `.save()` without `update_fields` on `AccountProfile` — it has `auto_now` fields that should update, but unrelated fields should not be accidentally overwritten.

9. **Import `AccountProfile` in `owner_views.py`.** The import `from apps.accounts.models import AccountProfile` does not currently exist in this file. Add it to the existing import line: `from apps.accounts.models import Membership, AccessAuditLog, AccountProfile`.

10. **Anti-enumeration guarantee in `ForgotPasswordView`.** The mode gate must return the EXACT same 200 response as the existing success path. Do not return a different status code or different message body for OWNER_MANAGED users.

11. **`_session_payload` default for missing profile.** Use `'personal'` as default `account_mode` when profile is None. This ensures self-registered owners (who theoretically could have no profile, though the signal creates one) retain full password capabilities. Use `False` as default for `must_change_password`.

12. **Test file organization.** Create test files in `services/api/src/apps/accounts/tests/`. Use `TestCase` (Django), not `pytest`. Follow the existing pattern from `test_internal_users.py` and `test_owner_access.py`.

13. **Do not add a `contador` role option to the frontend modal yet.** The `ROLE_OPTIONS` array currently has 8 entries. Only add `contador` if it already exists in the array. Check first. (It does NOT currently exist in `ROLE_OPTIONS` — do not add it in this PR.)

14. **Forced change page must be in `(auth)` layout group.** Verify `apps/web/src/app/(auth)/` exists. If it does, create `cambiar-contrasena/page.tsx` inside it. If it doesn't exist, create the directory with a minimal layout.

15. **Layout guard order matters.** The `must_change_password` redirect must fire BEFORE the subscription/billing checks in `layout.tsx`. A user who needs to change their password should not be redirected to a billing page first.
