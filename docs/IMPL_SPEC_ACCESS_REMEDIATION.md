# Mirubro Digital — Implementation Specification: Access & Roles Remediation (v2)

**Date:** 2026-04-01
**Revision:** v2 — dual account mode (OWNER_MANAGED / PERSONAL)
**Status:** SPEC DRAFT — requires owner sign-off before implementation
**Input:** `AUDIT_ROLES_ACCESS_COMPLETE.md` (score 72/100)
**Target:** Production remediation to score ≥ 92/100
**Constraint:** Owner remains the authoritative actor for all secondary accounts. No self-service invitation acceptance. No invitation flows.

---

## 1. Revised Product Model

### Two Account Modes

Mirubro does NOT enforce a single password policy for all secondary users. Instead, the owner chooses one of two modes at user creation time.

#### OWNER_MANAGED

The owner fully administers the account. Intended for shared terminals, low-trust personnel, or high-turnover roles where the owner must retain total credential control.

| Aspect | Behavior |
|--------|----------|
| **Created by** | Owner (via Create Member) |
| **Can change own password** | No — endpoint rejects the request |
| **Can self-reset password** (forgot password) | No — `ForgotPasswordView` silently ignores the user |
| **First login forced password change** | No — user logs in with the owner-provided password and stays on it |
| **Owner can reset password** | Yes — generates temp password, user uses it immediately |
| **Owner can suspend / disable / remove** | Yes |
| **Typical roles** | cashier, kitchen, salon, staff, viewer |
| **Rationale** | Store POS accounts, shared registers, delivery terminals. Owner needs to swap credentials instantly without user friction. |

#### PERSONAL

The owner creates the account but the user takes partial ownership of their credentials. Intended for trusted, named individuals who need autonomy.

| Aspect | Behavior |
|--------|----------|
| **Created by** | Owner (via Create Member) |
| **Can change own password** | Yes — via a self-service change-password endpoint |
| **Can self-reset password** (forgot password) | Yes, if email is configured on the account |
| **First login forced password change** | Optional — owner chooses at creation time. Defaults to `true` for PERSONAL accounts to encourage credential hygiene. |
| **Owner can reset password** | Yes — generates temp password, sets `must_change_password=true` so user must change on next login |
| **Owner can suspend / disable / remove** | Yes |
| **Typical roles** | admin, manager, analyst, contador |
| **Rationale** | Supervisors, managers, accountants who need their own secure credentials. |

### Differences Summary Table

| Capability | OWNER_MANAGED | PERSONAL |
|------------|:-------------:|:--------:|
| User changes own password | ✗ | ✓ |
| User self-resets via email | ✗ | ✓ (if email set) |
| Forced change on first login | Never | Owner's choice (default: yes) |
| Owner resets password | ✓ (direct) | ✓ (+ forces change) |
| Owner suspend/disable/remove | ✓ | ✓ |

### Recommended Default Mode by Role

| Role | Recommended Mode | Rationale |
|------|:----------------:|-----------|
| owner | N/A (self-registered) | Owners register themselves; never created via this flow |
| admin | PERSONAL | Trusted, named individual — needs password autonomy |
| manager | PERSONAL | Named supervisor — needs password autonomy |
| analyst | PERSONAL | Data analyst — named individual |
| contador | PERSONAL | Accountant — needs own secure credentials |
| cashier | OWNER_MANAGED | Shared POS terminal — owner controls credentials |
| staff | OWNER_MANAGED | General staff — owner controls |
| viewer | OWNER_MANAGED | Read-only — typically shared or transient |
| kitchen | OWNER_MANAGED | Shared kitchen display — owner controls |
| salon | OWNER_MANAGED | Shared floor device — owner controls |

The UI pre-selects the recommended mode based on the chosen role, but the owner can override.

---

## 2. Data Model Changes

### Design Evaluation

Four candidate fields were considered:

| Field | Purpose | Verdict |
|-------|---------|---------|
| `account_mode` | Single enum: `owner_managed` / `personal` | **Use.** This is the authoritative switch. All behavior derives from it. |
| `can_change_password` | Derived boolean | **Skip.** Derivable from `account_mode == 'personal'`. Adding it would create a sync risk. |
| `can_self_reset_password` | Derived boolean | **Skip.** Derivable from `account_mode == 'personal' AND user.email != ''`. Two sources of truth is worse than one. |
| `must_change_password` | Transient flag for forced first-login change | **Use.** Cannot be derived — it's a one-time state that clears after the user changes their password. Orthogonal to `account_mode`. |

### Recommended Design: 2 Fields

```python
# services/api/src/apps/accounts/models.py — AccountProfile

class AccountMode(models.TextChoices):
    OWNER_MANAGED = 'owner_managed', 'Administrada por el dueño'
    PERSONAL      = 'personal',      'Personal'

# ADD after email_verified field:
account_mode = models.CharField(
    max_length=16,
    choices=AccountMode.choices,
    default=AccountMode.OWNER_MANAGED,
    help_text='Determines password self-service capabilities. owner_managed: '
              'only the business owner can manage credentials. personal: '
              'user can change and reset their own password.',
)

must_change_password = models.BooleanField(
    default=False,
    help_text='When True, user is forced to change password on next login. '
              'Cleared after successful password change. Only meaningful for '
              'PERSONAL accounts.',
)
```

**Why this is the cleanest design:**

1. **`account_mode`** is a single enum — all password permission behavior derives from it via helpers like `can_change_password()` and `can_self_reset()`. No redundant boolean fields to keep in sync.
2. **`must_change_password`** is inherently transient (set to `true`, consumed once, then `false` forever). It cannot be derived from `account_mode` because a PERSONAL user who has already changed their password should not be forced again. It is the only additional field needed.
3. Owners already-registered via `RegisterView` never go through `InternalUserService`. Their `AccountProfile` stays `account_mode='owner_managed'` (the default) but this is irrelevant because `account_mode` is only checked for secondary users — owners are excluded by role check from the affected endpoints.

**Migration:** Auto-generated. Safe: `default='owner_managed'` and `default=False` mean all existing rows get sensible values. Existing internal users become OWNER_MANAGED (correct — they were created before this feature, so preserving the restrictive default is safest).

### Helper Methods on AccountProfile

```python
# services/api/src/apps/accounts/models.py — AccountProfile methods

def can_change_password(self) -> bool:
    """Whether this user may change their own password."""
    return self.account_mode == self.AccountMode.PERSONAL

def can_self_reset(self) -> bool:
    """Whether this user may use forgot-password self-service."""
    return (
        self.account_mode == self.AccountMode.PERSONAL
        and bool(self.user.email)
    )
```

These are pure derivations — no additional DB columns needed.

### Plan Seat Limits (New File — unchanged from v1)

```python
# services/api/src/apps/billing/plans.py

PLAN_SEAT_LIMITS: dict[str, int] = {
    'start':            2,
    'starter':          2,
    'plus':             5,
    'pro':              10,
    'business':         20,
    'enterprise':       100,
    'menu_qr':          2,
    'menu_qr_lite':     2,
    'menu_qr_visual':   3,
    'menu_qr_marca':    5,
    'menu_qr_premium':  10,
    'menu_qr_pro':      10,
}

DEFAULT_SEAT_LIMIT = 2

def get_seat_limit(plan_tier: str) -> int:
    """Return max seats for a plan tier. 0 means unlimited."""
    return PLAN_SEAT_LIMITS.get(plan_tier, DEFAULT_SEAT_LIMIT)
```

---

## 3. Backend Implementation Changes

### 3.1 Create Member Flow

**Files:** `services/api/src/apps/accounts/services.py`, `services/api/src/apps/accounts/owner_views.py`, `services/api/src/apps/accounts/owner_serializers.py`

**`InternalUserService.create_internal_user()`** — add parameters:

```python
@classmethod
def create_internal_user(
    cls,
    *,
    business,
    first_name, last_name, username, password, role,
    email='',
    account_mode='owner_managed',        # NEW
    force_password_change=False,          # NEW
    created_by_user=None,
    request=None,
) -> dict:
```

Changes inside the method:
1. **Seat check:** Replace legacy `Subscription.objects.select_for_update().get(business=hq)` with V2-aware resolution via `resolve_subscription()` + `get_seat_limit()`.
2. **AccountProfile update:** After creating the user, set `account_mode` and `must_change_password`:
   ```python
   AccountProfile.objects.filter(user=user).update(
       account_status=AccountProfile.AccountStatus.ACTIVE,
       email_verified=True,
       account_mode=account_mode,
       must_change_password=force_password_change,
   )
   ```
3. **Validation:** If `account_mode == 'owner_managed'` and `force_password_change == True`, reject with error — OWNER_MANAGED users cannot be forced to change password (they can't change it at all).

**`create_member` view** — accept `account_mode` and `force_password_change` in request:
```python
result = InternalUserService.create_internal_user(
    ...
    account_mode=data.get('account_mode', 'owner_managed'),
    force_password_change=data.get('force_password_change', False),
)
```

**`CreateMemberSerializer`** — add fields:
```python
account_mode = serializers.ChoiceField(
    choices=['owner_managed', 'personal'],
    default='owner_managed',
)
force_password_change = serializers.BooleanField(default=False)
```

### 3.2 Reset Password Flow

**File:** `services/api/src/apps/accounts/owner_views.py` — `reset_password()`

After setting the new password:
```python
# If target is PERSONAL, force them to change the owner-assigned password
profile = AccountProfile.objects.get(user=target_user)
if profile.account_mode == AccountProfile.AccountMode.PERSONAL:
    profile.must_change_password = True
    profile.save(update_fields=['must_change_password', 'updated_at'])
```

For OWNER_MANAGED users, `must_change_password` stays `False`. The owner's reset is the final credential — no further user action required.

### 3.3 Login / Session Payload

**File:** `services/api/src/apps/accounts/views.py` — `_session_payload()`

Add to the `user` dict:
```python
'user': {
    'id': user.id,
    'email': user.email,
    'name': user.get_full_name() or user.get_username(),
    'email_verified': profile.email_verified if profile else False,
    'account_mode': profile.account_mode if profile else 'personal',     # NEW
    'must_change_password': profile.must_change_password if profile else False,  # NEW
},
```

Frontend uses `must_change_password` for the layout guard redirect, and `account_mode` to show/hide the "Change password" option in user settings.

### 3.4 Force Change Password Endpoint (NEW)

**Files:** `services/api/src/apps/accounts/views.py`, `services/api/src/apps/accounts/urls.py`

```python
class ForceChangePasswordView(APIView):
    """
    POST /api/v1/auth/force-change-password/
    Body: { "current_password": "...", "new_password": "..." }

    Only callable when AccountProfile.must_change_password == True
    AND AccountProfile.account_mode == 'personal'.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile = getattr(request.user, 'account_profile', None)
        if not profile or not profile.must_change_password:
            return Response(
                {'detail': 'No se requiere cambio de contraseña.'},
                status=400,
            )
        if profile.account_mode != AccountProfile.AccountMode.PERSONAL:
            return Response(
                {'detail': 'Esta cuenta no permite cambio de contraseña.'},
                status=403,
            )
        # validate current_password, new_password...
        # user.set_password(new_password)
        # profile.must_change_password = False
        # profile.save(...)
        # reissue JWT cookies
        # audit log: PASSWORD_FORCE_CHANGED
```

URL registration:
```python
path('force-change-password/', ForceChangePasswordView.as_view(), name='auth-force-change-password'),
```

### 3.5 Self-Service Change Password Endpoint (NEW)

**Files:** `services/api/src/apps/accounts/views.py`, `services/api/src/apps/accounts/urls.py`

```python
class ChangePasswordView(APIView):
    """
    POST /api/v1/auth/change-password/
    Body: { "current_password": "...", "new_password": "..." }

    Only allowed for PERSONAL accounts.
    This is the voluntary self-service password change (not forced).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile = getattr(request.user, 'account_profile', None)
        if not profile or not profile.can_change_password():
            return Response(
                {'detail': 'Tu cuenta no permite cambio de contraseña. '
                           'Contacta al propietario del negocio.'},
                status=403,
            )
        # validate current_password, new_password...
        # user.set_password(new_password)
        # audit log: PASSWORD_CHANGED
```

URL registration:
```python
path('change-password/', ChangePasswordView.as_view(), name='auth-change-password'),
```

### 3.6 Forgot Password Behavior

**File:** `services/api/src/apps/accounts/views.py` — `ForgotPasswordView.post()`

Add a gate after finding the user:
```python
user = User.objects.get(email__iexact=email, is_active=True)
profile, _ = AccountProfile.objects.get_or_create(user=user)

# OWNER_MANAGED users cannot self-reset — silently ignore
if not profile.can_self_reset():
    # Return the same 200 response (anti-enumeration)
    return Response({...})

token = profile.generate_password_reset_token()
EmailService.send_password_reset_email(user, token)
```

For OWNER_MANAGED users (or PERSONAL without email), the endpoint returns the same 200 response but does not generate a token or send an email. This preserves the anti-enumeration guarantee.

### 3.7 Reset Password Via Token (Self-Service)

**File:** `services/api/src/apps/accounts/views.py` — `ResetPasswordView.post()`

After the user successfully resets via token, check mode:
```python
# If this was a self-reset for a PERSONAL user, verify mode allows it
profile = AccountProfile.objects.get(user=profile.user)
if profile.account_mode != AccountProfile.AccountMode.PERSONAL:
    return Response(
        {'detail': 'El enlace no es válido.'},
        status=400,
    )

# Also clear must_change_password if it was set
if profile.must_change_password:
    profile.must_change_password = False
    profile.save(update_fields=['must_change_password', 'updated_at'])
```

### 3.8 Permission Checks Summary

| Endpoint | Check |
|----------|-------|
| `ForceChangePasswordView` | `profile.must_change_password == True AND profile.account_mode == 'personal'` |
| `ChangePasswordView` | `profile.can_change_password()` → `account_mode == 'personal'` |
| `ForgotPasswordView` | `profile.can_self_reset()` → `account_mode == 'personal' AND user.email != ''` |
| `ResetPasswordView` (token) | `profile.account_mode == 'personal'` |
| `reset_password` (owner) | Always allowed — owner authority overrides mode |

OWNER_MANAGED users who attempt any self-service password operation get a clean rejection (403 for authenticated endpoints, silent 200 for forgot-password).

---

## 4. Frontend Implementation Changes

### 4.1 Create Member Modal

**File:** `apps/web/src/components/app/owner-access/create-member-modal.tsx`

**Add account mode selector and conditional forced-change checkbox:**

```tsx
// New state
const [accountMode, setAccountMode] = useState<'owner_managed' | 'personal'>('owner_managed');
const [forcePasswordChange, setForcePasswordChange] = useState(false);

// When role changes, pre-select the recommended mode
useEffect(() => {
  const personalRoles = ['admin', 'manager', 'analyst', 'contador'];
  const recommended = personalRoles.includes(role) ? 'personal' : 'owner_managed';
  setAccountMode(recommended);
  setForcePasswordChange(recommended === 'personal'); // default on for personal
}, [role]);
```

**UI additions** (after the Role selector, before submit):

```tsx
{/* Account Mode */}
<div>
  <label className="block text-sm font-medium text-slate-700">
    Tipo de cuenta <span className="text-red-500">*</span>
  </label>
  <div className="mt-1 grid grid-cols-2 gap-2">
    <button type="button"
      onClick={() => { setAccountMode('owner_managed'); setForcePasswordChange(false); }}
      className={`rounded-lg border px-3 py-2 text-sm text-left ${
        accountMode === 'owner_managed'
          ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500'
          : 'border-slate-300 hover:border-slate-400'
      }`}>
      <strong>Administrada</strong>
      <p className="text-xs text-slate-500 mt-1">Vos controlás la contraseña</p>
    </button>
    <button type="button"
      onClick={() => { setAccountMode('personal'); setForcePasswordChange(true); }}
      className={`rounded-lg border px-3 py-2 text-sm text-left ${
        accountMode === 'personal'
          ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500'
          : 'border-slate-300 hover:border-slate-400'
      }`}>
      <strong>Personal</strong>
      <p className="text-xs text-slate-500 mt-1">El usuario maneja su contraseña</p>
    </button>
  </div>
</div>

{/* Forced password change (only for PERSONAL) */}
{accountMode === 'personal' && (
  <label className="flex items-center gap-2 text-sm text-slate-700">
    <input type="checkbox" checked={forcePasswordChange}
      onChange={(e) => setForcePasswordChange(e.target.checked)}
      className="rounded border-slate-300" />
    Forzar cambio de contraseña en el primer inicio de sesión
  </label>
)}
```

**Submit payload update:**
```tsx
await ownerAccessApi.createMember({
  ...existingFields,
  account_mode: accountMode,
  force_password_change: forcePasswordChange,
});
```

### 4.2 Accounts Table

**File:** `apps/web/src/components/app/owner-access/accounts-table.tsx`

Add an `account_mode` column (or badge) showing "Administrada" / "Personal" per row.

```tsx
<th className="...">Modo</th>
// ...in row:
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

**Type update** (`apps/web/src/types/owner-access.ts` — `UserAccount`):
```typescript
export interface UserAccount {
  // ... existing fields ...
  account_mode: 'owner_managed' | 'personal';  // NEW
}
```

### 4.3 Auth Types

**File:** `apps/web/src/lib/auth/types.ts`

Add to the `user` object inside `Session`:
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

### 4.4 Forced Password Change Page

**File (NEW):** `apps/web/src/app/(auth)/cambiar-contrasena/page.tsx`

Route: `/cambiar-contrasena` — outside `/app/` layout, inside `(auth)` layout.

Minimal form:
- Current password (the one owner provided)
- New password
- Confirm new password
- Submit → `POST /api/v1/auth/force-change-password/`
- On success → redirect to `/app`
- Cannot be skipped — layout guard intercepts

Message at top: "Tu propietario te creó una contraseña temporal. Por seguridad, elegí una contraseña propia."

### 4.5 App Layout Guard

**File:** `apps/web/src/app/app/layout.tsx`

Add **after** the existing `if (!session)` redirect and **before** the subscription access check:

```typescript
// Forced password change — only for PERSONAL accounts with pending change
if (resolvedSession.user.must_change_password) {
    redirect('/cambiar-contrasena');
}
```

This fires before subscription checks because a user who needs to change their password cannot do anything else. OWNER_MANAGED users will never have `must_change_password=true` (enforced at creation and reset time), so this guard never fires for them.

### 4.6 User Settings — Change Password (P1)

**File:** `apps/web/src/app/app/settings/cuenta/page.tsx` (or equivalent profile/settings page)

Show a "Cambiar contraseña" section only if `session.user.account_mode === 'personal'`:

```tsx
{session.user.account_mode === 'personal' && (
  <ChangePasswordSection />
)}
```

For OWNER_MANAGED users, show a note:
> "Tu contraseña es administrada por el propietario del negocio."

### 4.7 Forgot Password Page

No frontend change needed. The "Olvidé mi contraseña" link remains visible for all users. The backend silently ignores OWNER_MANAGED users (anti-enumeration). The user sees "Si el email está registrado, recibirás un enlace..." regardless.

### 4.8 Frontend Fix: `canManage` (owner-only)

**File:** `apps/web/src/app/app/settings/access/page.tsx`

```typescript
// BEFORE (line 42):
const canManage = summary.role === 'owner' || summary.role === 'admin';

// AFTER:
const canManage = summary.role === 'owner';
```

---

## 5. Password Policy Behavior Matrix

| User Type | Account Mode | Can Change Own Password | Can Self Reset | Must Change First Login | Can Owner Reset | Intended Use |
|-----------|:------------:|:-----------------------:|:--------------:|:-----------------------:|:---------------:|-------------|
| **Owner** | N/A (self-reg) | ✓ (always) | ✓ (always) | N/A | N/A | Business owner — full self-service |
| **Admin** | PERSONAL | ✓ | ✓ (if email) | Yes (default) | ✓ (forces change) | Trusted admin — handles sensitive ops |
| **Manager** | PERSONAL | ✓ | ✓ (if email) | Yes (default) | ✓ (forces change) | Supervisor — manages shifts, staff |
| **Analyst** | PERSONAL | ✓ | ✓ (if email) | Yes (default) | ✓ (forces change) | Data viewer — reports, dashboards |
| **Contador** | PERSONAL | ✓ | ✓ (if email) | Yes (default) | ✓ (forces change) | Accountant — tax, fiscal access |
| **Cashier** | OWNER_MANAGED | ✗ | ✗ | No (never) | ✓ (direct) | POS terminal — shared or rotated |
| **Staff** | OWNER_MANAGED | ✗ | ✗ | No (never) | ✓ (direct) | General employee — low autonomy |
| **Viewer** | OWNER_MANAGED | ✗ | ✗ | No (never) | ✓ (direct) | Read-only — typically transient |
| **Kitchen** | OWNER_MANAGED | ✗ | ✗ | No (never) | ✓ (direct) | Kitchen display — shared device |
| **Salon** | OWNER_MANAGED | ✗ | ✗ | No (never) | ✓ (direct) | Floor service — shared device |
| **Shared Account** | OWNER_MANAGED | ✗ | ✗ | No (never) | ✓ (direct) | Multiple operators — one credential |

**Notes:**
- The owner can override recommended mode. A cashier CAN be set to PERSONAL if the owner chooses. The defaults are recommendations, not hard constraints.
- "Can Self Reset" requires PERSONAL mode AND a non-empty email. PERSONAL users without email cannot self-reset but can still change their password from within the app.
- "Must Change First Login" for PERSONAL defaults to `true` but the owner can uncheck it at creation. For OWNER_MANAGED it is always `false` and cannot be set to `true`.

---

## 6. Revised Rollout Priority

### P0 — Must Ship (blocks production readiness)

| ID | Task | Files | Effort | Notes |
|----|------|-------|--------|-------|
| P0-1 | Create `billing/plans.py` with `PLAN_SEAT_LIMITS` | 1 new file | S | Unchanged from v1 |
| P0-2 | V2-aware seat check in `InternalUserService` | services.py | M | Unchanged from v1 |
| P0-3 | V2-aware seat check in `check_seat_limit` signal | models.py | M | Unchanged from v1 |
| P0-4 | Add `account_mode` + `must_change_password` fields + migration | models.py + migration | S | **Revised:** was only `must_change_password`, now includes `account_mode` |
| P0-5 | Add `can_change_password()` + `can_self_reset()` helpers | models.py | S | **New** |
| P0-6 | Update `InternalUserService` to accept `account_mode` + `force_password_change` | services.py | S | **Revised:** conditional `must_change_password` based on mode |
| P0-7 | Add `ForceChangePasswordView` with mode check | views.py, urls.py | M | **Revised:** checks `account_mode == 'personal'` |
| P0-8 | Add `ChangePasswordView` for voluntary self-service | views.py, urls.py | M | **New** — PERSONAL users only |
| P0-9 | Gate `ForgotPasswordView` on `can_self_reset()` | views.py | S | **New** — silently ignores OWNER_MANAGED |
| P0-10 | Gate `ResetPasswordView` (token) on `account_mode == 'personal'` | views.py | S | **New** |
| P0-11 | Update `_session_payload()` with `account_mode` + `must_change_password` | views.py | S | **Revised:** now includes `account_mode` |
| P0-12 | Update `accounts_list` to include `seat_info` + per-account `account_mode` | owner_views.py | S | **Revised** |
| P0-13 | Owner `reset_password`: set `must_change_password` only if PERSONAL | owner_views.py | S | **New** |
| P0-14 | Frontend: update `CreateMemberModal` with account mode selector | create-member-modal.tsx | M | **New** |
| P0-15 | Frontend: create `/cambiar-contrasena` forced change page | 1 new file | M | Unchanged from v1 |
| P0-16 | Frontend: layout guard for `must_change_password` | layout.tsx | S | Unchanged from v1 |
| P0-17 | Frontend: fix `canManage` to owner-only | page.tsx | S | Unchanged from v1 |
| P0-18 | Frontend: `SeatInfoBar` + `account_mode` badge in accounts table | seat-info-bar.tsx, accounts-table.tsx | S | **Revised** |
| P0-19 | Frontend: update auth types | types.ts | S | **Revised** |
| P0-20 | Write P0 tests (see §6.1 Test Specification) | 3 test files | M | **Expanded** |

**Total P0:** ~20 tasks. Recommend splitting into 2 PRs:
- **PR-A:** Backend (P0-1 through P0-13) — all backend + migration
- **PR-B:** Frontend (P0-14 through P0-20) — all frontend changes

### P1 — Should Ship (correctness and hardening)

| ID | Task | Files | Effort |
|----|------|-------|--------|
| P1-1 | Fix `ForgotPasswordView` audit action string (`PASSWORD_RESET_CONFIRMED` → `PASSWORD_RESET_REQUESTED`) | views.py | S |
| P1-2 | Remove `VerifyEmailView` dead code (unreachable first query) | views.py | S |
| P1-3 | Sync `Membership.status` in `disable_account()` | owner_views.py | S |
| P1-4 | Frontend: user settings "Cambiar contraseña" section (PERSONAL only) | cuenta/page.tsx | M |
| P1-5 | Frontend: "Tu contraseña es administrada por el propietario" message for OWNER_MANAGED | cuenta/page.tsx | S |

### P2 — Should Ship (data isolation)

| ID | Task | Files | Effort |
|----|------|-------|--------|
| P2-1 | Audit all querysets for branch scope gaps | research task | L |
| P2-2 | Create `get_branch_filter()` utility | access.py | S |
| P2-3 | Apply branch filter across apps | multiple files | L |
| P2-4 | Write branch isolation tests | 1 test file | M |

**Justification for deferring branch scope:** Branch features are not widely used yet. The `branch_scope` field exists on `Membership` but no branch-scoped memberships have been created in production. Risk is theoretical until multi-branch tenants appear. P0/P1 deliver immediately measurable value.

### P3 — Future (not in this remediation)

- Ownership transfer endpoint
- Allow owner to switch an existing user's `account_mode` after creation
- Remove `billing.Subscription` intermediate dead model
- Email-based invitation system (if constraint ever changes)

### P0 Test Specification

```
File: services/api/src/apps/accounts/tests/test_seat_limits_v2.py

test_create_member_v2_sub_within_limit
test_create_member_v2_sub_at_limit
test_create_member_v2_sub_no_v2_falls_to_legacy
test_create_member_no_subscription_at_all
test_create_member_enterprise_high_limit
test_seat_check_uses_hq_family_count
test_seat_check_signal_v2_blocks

File: services/api/src/apps/accounts/tests/test_account_modes.py

# Creation
test_create_member_owner_managed_default
test_create_member_personal_with_force_change
test_create_member_personal_without_force_change
test_create_member_owner_managed_rejects_force_change
test_create_member_session_includes_account_mode

# OWNER_MANAGED password restrictions
test_owner_managed_cannot_change_own_password           → 403
test_owner_managed_forgot_password_silently_ignored      → 200 but no token generated
test_owner_managed_reset_token_rejected                  → 400

# PERSONAL password self-service
test_personal_can_change_own_password                    → 200
test_personal_can_self_reset_with_email                  → token generated
test_personal_cannot_self_reset_without_email             → 200 but no token generated
test_personal_force_change_clears_flag                   → must_change_password=False after

# Owner reset interactions
test_owner_reset_personal_sets_must_change               → must_change_password=True
test_owner_reset_owner_managed_no_must_change             → must_change_password stays False
test_force_change_view_rejects_owner_managed              → 403

# Audit
test_password_force_changed_audit_log
test_password_changed_audit_log
test_forgot_password_audit_log_fixed_action

File: services/api/src/apps/accounts/tests/test_access_integration.py

test_full_flow_personal_create_login_force_change
test_full_flow_owner_managed_create_login_no_force
test_seat_limit_blocks_after_plan_downgrade
test_disable_account_syncs_membership_status
```

---

## 7. Final Recommendation

### Best Minimal Production Version

Ship `account_mode` (enum) + `must_change_password` (boolean) on `AccountProfile`. These two fields are the minimum surface area to implement the dual-mode model correctly.

**Essential now (P0):**
- `account_mode` field — without it, there is no way to differentiate password behavior per user.
- `must_change_password` field — without it, forced first-login change for PERSONAL accounts is impossible.
- V2-aware seat limits — without it, paid V2 customers can add unlimited users (critical billing gap).
- `ForgotPasswordView` mode gate — without it, OWNER_MANAGED users receive reset emails they shouldn't be able to use (confusing UX, potential support burden).
- `ForceChangePasswordView` + layout guard — without it, PERSONAL users never change their owner-assigned password.
- `ChangePasswordView` — without it, PERSONAL users have no self-service path at all.
- `canManage` fix — without it, admin users see management tabs and get 403 errors.

**Can wait (P1):**
- User settings "Change password" section in the UI (PERSONAL users can still use the forced change flow; voluntary change from settings is a convenience, not a gate).
- Audit action string fixes (correctness, not functionality).
- Dead code removal in `VerifyEmailView`.
- `disable_account` → `Membership.status` sync.

**Can wait longer (P2):**
- Branch scope enforcement — real gap but no branch-scoped memberships exist in production yet.

### Score Projection

| Milestone | Score | Delta |
|-----------|------:|------:|
| Current | 72 | — |
| After P0 | ~90 | +18 |
| After P0 + P1 | ~94 | +22 |
| After P0 + P1 + P2 | ~97 | +25 |

The +2 improvement over v1's P0 projection comes from the dual-mode model being a more complete solution than blanket forced-change. OWNER_MANAGED users get a deliberately locked-down experience (correct for POS/shared accounts), while PERSONAL users get proper credential autonomy. Neither mode is a compromise — each is designed for its specific use case.
