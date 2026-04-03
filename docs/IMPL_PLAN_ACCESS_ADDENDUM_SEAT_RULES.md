# Addendum — Seat Counting & Subscription Gating Rules

> **Purpose:** Focused update to `IMPL_PLAN_ACCESS_REMEDIATION.md` incorporating two new frozen business rules.
> **Scope:** Seat limit logic, subscription gating, owner exclusion from count.
> **Date:** 2025-07-14
> **Status:** FROZEN — supersedes conflicting sections in the base plan.

---

## 1. Updated Frozen Decisions

The following rows in the base plan's §2 "Frozen Decisions" table are **replaced** by this addendum:

| # | Decision | Details |
|---|----------|---------|
| F-NEW-1 | **No active subscription = hard block** | Member creation is allowed **only when `resolved.access_granted is True`**. This reuses exactly the same access decision that `resolve_subscription()` already computes via `_v2_grants_access()` for V2 and `status == 'active'` for legacy. When `access_granted is False` — regardless of reason (no subscription, suspended, canceled, past_due-expired, checkout_pending) — member creation is **forbidden** (raise `PermissionDenied`). |
| F-NEW-2 | **Owner never counts as a seat** | Seat counting queries **exclude** `role='owner'`. Only secondary users (admin, manager, cashier, staff, viewer, kitchen, salon, analyst, contador) consume seats. The owner is the subscription holder, not a consumer. |
| 15 (revised) | **Seat limit source** | Canonical V2 via `resolve_subscription()` + `get_seat_limit()`. Fallback legacy `max_seats` only when `resolved.source == 'legacy'`. When `access_granted is False` → **hard block**, not unlimited. |

### 1.1 Subscription States Reference

`resolve_subscription(hq)` resolves to one of these combinations. The `access_granted` boolean is the **sole gate** for member creation:

| `source` | `status` | `access_granted` | Member creation? |
|----------|----------|-------------------|------------------|
| `v2` | `active` | `True` | Allowed (within seat limit) |
| `v2` | `trialing` (within trial_ends_at) | `True` | Allowed (within seat limit) |
| `v2` | `past_due` (within grace_until) | `True` | Allowed (within seat limit) |
| `v2` | `past_due` (grace expired) | `False` | **Blocked** |
| `v2` | `suspended` | `False` | **Blocked** |
| `v2` | `canceled` | N/A (excluded by `_find_best_v2`) | **Blocked** (falls to legacy/none) |
| `v2` | `checkout_pending` | N/A (excluded) | **Blocked** (falls to legacy/none) |
| `legacy` | `active` | `True` | Allowed (within legacy max_seats) |
| `legacy` | any other | `False` | **Blocked** |
| `none` | — | `False` | **Blocked** |

### 1.2 Why `access_granted` and not `source != 'none'`

`resolve_subscription()` already encodes the exact same business logic the rest of the app uses (active, trialing-in-range, past_due-in-grace). Reusing `access_granted` means:
- No duplicated status logic in the seat gate
- Suspended V2 subscriptions are correctly blocked (they have `source='v2'` but `access_granted=False`)
- Any future status changes propagate automatically

All other frozen decisions remain unchanged.

---

## 2. Backend Corrections

### 2.1 `billing/plans.py` — No Change to Structure

The `PLAN_SEAT_LIMITS` dict and `get_seat_limit()` function defined in the base plan remain correct. No changes needed.

### 2.2 `services.py` — Task B-5 Replacement Code (REVISED)

**Replace** the base plan's B-5 code block entirely with the following:

```python
# ── Seat limit check (V2-first) ────────────────────────────────────
hq = business.parent if business.parent else business
family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))

from apps.billing.runtime import resolve_subscription
from apps.billing.plans import get_seat_limit

resolved = resolve_subscription(hq)

# ── RULE 1: No active subscription → hard block ──────────────────
# Reuses the same access_granted decision used by the rest of the app.
# Covers: no subscription, suspended, canceled, past_due-expired,
# checkout_pending, trialing-expired.
if not resolved.access_granted:
    from rest_framework.exceptions import PermissionDenied
    raise PermissionDenied(
        'No tenés una suscripción activa. '
        'Activá un plan para poder agregar usuarios.'
    )

# ── Resolve seat limit ────────────────────────────────────────────
if resolved.source == 'v2':
    max_seats = get_seat_limit(resolved.plan)
elif resolved.source == 'legacy':
    # Legacy with access_granted=True always has status='active'
    max_seats = resolved.legacy_sub.max_seats if resolved.legacy_sub else 0
else:
    max_seats = 0  # Unreachable: access_granted=True implies source is v2 or legacy

# ── RULE 2: Count only secondary users (exclude owner) ───────────
if max_seats > 0:
    current_count = Membership.objects.filter(
        business__id__in=family_ids,
    ).exclude(
        role='owner',
    ).count()

    if current_count >= max_seats:
        raise ValidationError(
            f'Límite de usuarios ({max_seats}) alcanzado para "{hq.name}". '
            f'Actualmente tenés {current_count} usuario(s) secundario(s). '
            f'Mejora tu plan para agregar más.'
        )
```

**Key differences from base plan B-5:**
1. Gates on `not resolved.access_granted` instead of `resolved.source == 'none'` — catches suspended, expired past_due, etc.
2. `.exclude(role='owner')` added to the count query
3. Legacy branch reads `max_seats` from `resolved.legacy_sub` (already resolved, no second query)
4. Error message clarifies "usuario(s) secundario(s)"

### 2.3 `models.py` — Signal `check_seat_limit` (REVISED)

**Base plan task B-3** (the `check_seat_limit` signal) must apply the same two rules. Replace the signal body with:

```python
@receiver(pre_save, sender=Membership)
def check_seat_limit(sender, instance, **kwargs):
    """Block creation if no active subscription or at seat capacity."""
    if not instance._state.adding:
        return
    if instance.role == 'owner':
        return  # Owner never consumes a seat

    business = instance.business
    hq = business.parent if business.parent else business
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))

    from apps.billing.runtime import resolve_subscription
    from apps.billing.plans import get_seat_limit

    resolved = resolve_subscription(hq)

    # Same access_granted gate as create_internal_user — no active sub = block
    if not resolved.access_granted:
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied(
            'No tenés una suscripción activa. '
            'Activá un plan para poder agregar usuarios.'
        )

    if resolved.source == 'v2':
        max_seats = get_seat_limit(resolved.plan)
    elif resolved.source == 'legacy':
        max_seats = resolved.legacy_sub.max_seats if resolved.legacy_sub else 0
    else:
        max_seats = 0

    if max_seats > 0:
        current_count = Membership.objects.filter(
            business__id__in=family_ids,
        ).exclude(
            role='owner',
        ).count()

        if current_count >= max_seats:
            from django.core.exceptions import ValidationError
            raise ValidationError(
                f'Límite de usuarios ({max_seats}) alcanzado.'
            )
```

### 2.4 `owner_views.py` — Task B-11 `accounts_list` seat_info (REVISED)

Replace the B-11 seat info code block:

```python
# ── seat_info (only when ?include_seat_info=1) ────────────────────
include_seat_info = request.query_params.get('include_seat_info') == '1'
if include_seat_info:
    from apps.billing.runtime import resolve_subscription
    from apps.billing.plans import get_seat_limit

    resolved = resolve_subscription(hq)

    # ALWAYS count real secondary users, regardless of subscription state
    current_count = Membership.objects.filter(
        business__id__in=family_ids,
    ).exclude(
        role='owner',
    ).count()

    if resolved.source == 'v2':
        limit = get_seat_limit(resolved.plan)
        source = 'v2'
        plan = resolved.plan or ''
    elif resolved.source == 'legacy':
        limit = resolved.legacy_sub.max_seats if resolved.legacy_sub else 0
        source = 'legacy'
        plan = ''
    else:
        limit = 0
        source = 'none'
        plan = ''

    seat_info = {
        'current': current_count,       # Real count — always accurate
        'limit': limit,                 # 0 when no subscription
        'source': source,
        'plan': plan,
        'access_granted': resolved.access_granted,  # True only for active/trialing/grace
    }
    return Response({'accounts': serializer.data, 'seat_info': seat_info})

return Response(serializer.data)
```

**Key differences from base plan B-11:**
1. `.exclude(role='owner')` in counting query
2. `current` is **always** the real count of secondary users — never artificially zeroed
3. `access_granted` replaces `has_subscription` — uses the same boolean the rest of the app uses
4. Legacy branch reads from `resolved.legacy_sub` (no second query)

---

## 3. Counting Rules

### 3.1 Canonical Seat Count Formula

```
secondary_users = Membership.objects.filter(
    business__id__in=family_ids,    # HQ + all branches
).exclude(
    role='owner',                   # Owner NEVER counts
).count()
```

### 3.2 Status-Based Counting

| Membership Status | Counts as Seat? | Justification |
|-------------------|-----------------|---------------|
| `active`          | **Yes**         | Active user consuming resources |
| `inactive`        | **Yes**         | Still occupies the slot; owner can reactivate at any time |
| `suspended`       | **Yes**         | Temporary suspension; owner should not be able to add beyond limit by suspending then creating new ones |

**Rationale:** All non-owner memberships count regardless of status. If the owner wants to free a seat, they must **delete** the membership, not just suspend it. This prevents the "suspend → create → unsuspend → exceed limit" loophole.

### 3.3 Who is "Owner"?

The owner is identified solely by `role='owner'` on the Membership model. There is exactly one owner per business family (HQ). The owner:
- Created the business account
- Holds the subscription
- Is NOT counted against the seat limit
- Can never be deleted/suspended via the access management API

### 3.4 Multi-Branch Counting

Seats are counted at the **family level** (HQ + all branches). A business with HQ + 3 branches that has a 10-seat plan can have at most 10 secondary users across all 4 businesses combined.

---

## 4. API Behavior Changes

### 4.1 `POST /api/v1/owner/access/accounts/create/` — Subscription Not Active

**Previous (base plan):** When no subscription exists, creation was allowed with no limit.

**New behavior — applies to ALL cases where `access_granted is False`:**

```
HTTP 403 Forbidden
{
    "detail": "No tenés una suscripción activa. Activá un plan para poder agregar usuarios."
}
```

This single response covers:

| Scenario | `source` | `status` | `access_granted` | Result |
|----------|----------|----------|-------------------|--------|
| No subscription at all | `none` | — | `False` | 403 |
| V2 suspended | `v2` | `suspended` | `False` | 403 |
| V2 canceled (excluded by resolver) | falls to legacy/none | — | `False` | 403 |
| V2 past_due with expired grace | `v2` | `past_due` | `False` | 403 |
| V2 checkout_pending (excluded) | falls to legacy/none | — | `False` | 403 |
| Legacy non-active | `legacy` | e.g. `canceled` | `False` | 403 |

### 4.2 `POST /api/v1/owner/access/accounts/create/` — At Seat Limit

**Unchanged from base plan**, but the count now excludes the owner:

```
HTTP 400 Bad Request
{
    "detail": "Límite de usuarios (10) alcanzado para \"Mi Negocio\". Actualmente tenés 10 usuario(s) secundario(s). Mejora tu plan para agregar más."
}
```

**Practical difference:** A business on a "start" plan (2 seats) with the owner + 2 secondary users now has `current_count = 2` (not 3). Previously the owner was counted, so the limit was hit at owner + 1 secondary user.

### 4.3 `GET /api/v1/owner/access/accounts/?include_seat_info=1` — Seat Info

**Previous (base plan):** `seat_info.current` included the owner in the count.

**New behavior:**

```json
{
    "accounts": [...],
    "seat_info": {
        "current": 3,              // ALWAYS the real count of secondary users (owner excluded)
        "limit": 10,
        "source": "v2",
        "plan": "pro",
        "access_granted": true
    }
}
```

When no subscription:

```json
{
    "seat_info": {
        "current": 2,              // Still the real count — NOT zero
        "limit": 0,
        "source": "none",
        "plan": "",
        "access_granted": false
    }
}
```

When suspended:

```json
{
    "seat_info": {
        "current": 5,              // Real count, even though creation is blocked
        "limit": 10,
        "source": "v2",
        "plan": "pro",
        "access_granted": false
    }
}
```

### 4.4 Frontend SeatInfoBar Adjustments

The `SeatInfoBar` component (F-7 in base plan) should handle states based on `access_granted`:

| State | `access_granted` | `limit` | Display |
|-------|------------------|---------|--------|
| Normal | `true` | > 0 | `{current}/{limit} usuarios secundarios` + progress bar |
| At limit | `true` | > 0, current >= limit | Warning styling + "Has alcanzado el límite" |
| No active subscription | `false` | any | "Suscripción inactiva. No podés agregar usuarios." + disable "Crear usuario" button |

The "Sin límite de usuarios" case from the base plan is **removed** — there is no scenario where a subscribed plan has unlimited seats. If `limit == 0` and `access_granted == true`, treat as a data error and show "Contacta soporte".

---

## 5. Test Corrections

### 5.1 Tests to REVISE from Base Plan §9

| Test Name (from base plan) | Current Expectation | **New Expectation** |
|---|---|---|
| `test_create_member_no_subscription_at_all` | Success (no limit enforced) | **PermissionDenied (403)** — `access_granted=False` |
| `test_create_member_v2_sub_within_limit` | Success with `current_count` including owner | Success with `current_count` **excluding** owner |
| `test_create_member_v2_sub_at_limit` | Blocked at `count >= max_seats` including owner | Blocked at `count >= max_seats` **excluding** owner (effective capacity increases by 1) |
| `test_seat_check_signal_v2_blocks` | Signal blocks including owner in count | Signal blocks **excluding** owner from count |

### 5.2 NEW Tests to Add

Add these to `test_seat_limits_v2.py`:

```
test_create_member_no_subscription_returns_403
    Setup: Business with no V2 sub, no legacy sub
    Action: Attempt create_internal_user()
    Assert: PermissionDenied raised (not ValidationError)
    Assert: Response status 403
    Assert: Message contains "suscripción activa"

test_create_member_suspended_v2_returns_403
    Setup: V2 sub with status='suspended'
    Action: Attempt create_internal_user()
    Assert: PermissionDenied (403)
    Verify: V2 exists (source='v2') but access_granted=False

test_create_member_past_due_within_grace_succeeds
    Setup: V2 sub with status='past_due', grace_until=future
    Action: Attempt create_internal_user()
    Assert: Success (access_granted=True during grace)

test_create_member_past_due_expired_grace_returns_403
    Setup: V2 sub with status='past_due', grace_until=past
    Action: Attempt create_internal_user()
    Assert: PermissionDenied (403) — grace expired, access_granted=False

test_create_member_trialing_succeeds
    Setup: V2 sub with status='trialing', trial_ends_at=future
    Action: Attempt create_internal_user()
    Assert: Success (access_granted=True during trial)

test_owner_not_counted_in_seat_limit
    Setup: V2 plan='start' (2 seats), HQ has owner + 2 secondary users
    Action: Attempt create_internal_user() for 3rd secondary user
    Assert: ValidationError (at limit: 2/2 secondary users)
    Verify: If we had counted owner, limit would have been hit at 1 secondary user

test_owner_not_counted_allows_full_capacity
    Setup: V2 plan='start' (2 seats), HQ has owner + 1 secondary user
    Action: Attempt create_internal_user() for 2nd secondary user
    Assert: Success (1/2 secondary → 2/2 is allowed)
    Verify: Proves owner is excluded — with owner counting, this would be 3/2

test_signal_blocks_no_subscription
    Setup: No subscription at all
    Action: Directly create Membership via ORM (triggers signal)
    Assert: PermissionDenied raised by signal

test_signal_excludes_owner_from_count
    Setup: V2 plan='start' (2 seats), owner + 2 secondary
    Action: Directly create Membership(role='cashier') via ORM
    Assert: ValidationError from signal (2/2 secondary)
    Verify: Owner was not counted

test_suspended_user_still_counts_as_seat
    Setup: V2 plan='start' (2 seats), owner + 1 active + 1 suspended secondary
    Action: Attempt create_internal_user()
    Assert: ValidationError (2/2, suspended user counts)

test_seat_info_excludes_owner_in_current
    Setup: V2 plan='pro' (10 seats), owner + 3 secondary users
    Action: GET /owner/access/accounts/?include_seat_info=1
    Assert: seat_info.current == 3 (not 4)

test_seat_info_no_subscription_shows_real_count
    Setup: No V2, no legacy, owner + 2 secondary users
    Action: GET /owner/access/accounts/?include_seat_info=1
    Assert: seat_info.access_granted == False
    Assert: seat_info.current == 2 (real count, NOT zero)
    Assert: seat_info.limit == 0

test_seat_info_suspended_v2_shows_real_count
    Setup: V2 status='suspended', plan='pro' (10 seats), owner + 5 secondary
    Action: GET /owner/access/accounts/?include_seat_info=1
    Assert: seat_info.access_granted == False
    Assert: seat_info.current == 5 (real count despite suspended)
    Assert: seat_info.limit == 10 (plan limit still shown)
```

### 5.3 Tests UNCHANGED

All tests in `test_account_modes.py` from the base plan §9 remain as-is — they are not affected by these rules.

---

## 6. Corrected Acceptance Criteria

### 6.1 Replace These Criteria in Base Plan §3.6

Remove:
- ~~(implicit) Creating members with no subscription succeeds~~

Add:
- [ ] Creating member with `access_granted=False` (no sub, suspended, expired grace, etc.) returns **403**
- [ ] Creating member with `access_granted=True` (active, trialing, past_due in grace) within limit succeeds
- [ ] Creating member at seat limit returns **400** with seat limit message
- [ ] Creating member with **suspended V2** returns **403** (not allowed despite V2 existing)
- [ ] Creating member with **past_due V2 within grace** succeeds
- [ ] Creating member with **past_due V2 with expired grace** returns **403**
- [ ] **Owner is NOT counted** in the seat limit — a plan with 2 seats allows owner + 2 secondary users (not owner + 1)
- [ ] **Suspended secondary users** still count toward the seat limit
- [ ] `seat_info.current` always reflects the **real** count of secondary users, even when `access_granted=False`
- [ ] `seat_info.access_granted` is `false` when subscription is not active/trialing/in-grace

### 6.2 Replace Edge Case Row in Base Plan §3.5

| Case | Previous | **Corrected** |
|------|----------|---------------|
| Seat limit check with no V2 and no legacy | `max_seats=0` → no limit enforced (allows creation) | **`PermissionDenied` (403)** — `access_granted=False` → creation blocked |
| Seat limit check with suspended V2 | Not covered | **`PermissionDenied` (403)** — V2 exists but `access_granted=False` |
| Seat limit check with past_due V2 in grace | Not covered | **Allowed** — `access_granted=True` during grace period |

### 6.3 Revised Coding Agent Warning #1 (§11)

Replace base plan warning #1:

> ~~1. **DO NOT use legacy `Subscription` as primary seat source.** Always try `resolve_subscription()` first. Legacy is fallback only when `resolved.source != 'v2'`.~~

With:

> 1. **Two seat gating rules are MANDATORY:**
>    - **Gate on `resolved.access_granted`.** When `not resolved.access_granted`, raise `PermissionDenied` (403). Do NOT check only `resolved.source == 'none'` — this misses suspended and expired-grace states. `access_granted` already encodes the exact status logic from `_v2_grants_access()` and legacy `status == 'active'`.
>    - **Owner never counts.** Every seat counting query MUST include `.exclude(role='owner')`. This applies to `create_internal_user()`, `check_seat_limit` signal, and `accounts_list` seat_info.
>    - Legacy `Subscription` is fallback only when `resolved.source == 'legacy'`. V2 is always primary.

### 6.4 Add to Definition of Done (§10, PR-1)

Add under "Must be true to merge":
- [ ] `test_create_member_no_subscription_returns_403` passes
- [ ] `test_create_member_suspended_v2_returns_403` passes
- [ ] `test_create_member_past_due_within_grace_succeeds` passes
- [ ] `test_create_member_past_due_expired_grace_returns_403` passes
- [ ] `test_owner_not_counted_in_seat_limit` passes
- [ ] `test_owner_not_counted_allows_full_capacity` passes
- [ ] `test_suspended_user_still_counts_as_seat` passes
- [ ] `test_seat_info_no_subscription_shows_real_count` passes

Add under "Must be manually validated in staging":
- [ ] Business with no subscription → attempt create member → sees 403 error
- [ ] Business with suspended V2 → attempt create member → sees 403 error
- [ ] Business on start plan → owner + 2 secondary = at limit → 3rd secondary blocked
- [ ] Seat info bar shows `2/2` (not `3/2`) when owner + 2 secondary exist
- [ ] Seat info bar shows real user count even when subscription is inactive

---

## Summary of All Changed Sections in Base Plan

| Base Plan Section | Type of Change | What Changed |
|---|---|---|
| §2 Frozen Decisions | **3 rows added/revised** | F-NEW-1 (gate on `access_granted`), F-NEW-2 (owner excluded), #15 revised |
| §3.2 B-5 code (services.py) | **Replaced** | `not resolved.access_granted` gate + `.exclude(role='owner')` |
| §3.2 B-3 code (models.py signal) | **Replaced** | Same two rules applied to signal |
| §3.2 B-11 code (owner_views.py) | **Replaced** | `.exclude(role='owner')` + `access_granted` field + real count always |
| §3.5 Edge Cases | **3 rows corrected/added** | No sub → block; suspended V2 → block; past_due in grace → allowed |
| §3.6 Acceptance Criteria | **10 criteria added** | access_granted gating + owner exclusion + suspended counting + real count |
| §9 Test Plan / PR-1 | **4 tests revised, 14 tests added** | Subscription states; owner excluded; suspended counts; seat_info real count |
| §10 Definition of Done | **13 items added** | Merge gates + staging validations |
| §11 Warning #1 | **Rewritten** | Gates on `access_granted`, not `source != 'none'` |
| §4.2 F-7 SeatInfoBar | **Revised** | Uses `access_granted` boolean; shows real count always |
