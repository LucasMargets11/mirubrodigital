"""
accounts/admin_client_provisioning_service.py — ADMIN-CLIENTES 02A

Transactional service to provision a full client from the (future) platform
admin backoffice: a root ``Business`` + an owner ``User`` (new or reused) +
a single owner ``Membership`` + complimentary ("bonificado") access granted
via the existing ``billing.complimentary_access_service.grant_complimentary_access``.

Backend-only slice: no HTTP endpoint, no serializer, no Google OAuth, no
frontend. The single entry point is ``provision_admin_client()``.

This service does NOT re-validate plan/service compatibility, the bonified
period, or generate ``external_reference`` — all of that is owned by
``grant_complimentary_access()`` and is reused as-is.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.utils.crypto import constant_time_compare

from apps.accounts.models import AccountProfile, Membership
from apps.accounts.platform_audit import record_platform_action
from apps.billing.complimentary_access_service import (
    ActiveSubscriptionConflictError,
    ComplimentaryAccessError,
    InvalidCustomAllowanceError,
    InvalidGrantReasonError,
    InvalidPeriodError,
    InvalidServiceTypeError,
    InvalidUsageTierError,
    PlanNotAvailableError,
    PlanServiceMismatchError,
    grant_complimentary_access,
)
from apps.billing.models import SubscriptionV2
from apps.business.models import Business

if TYPE_CHECKING:
    from django.contrib.auth.models import User as UserType

logger = logging.getLogger(__name__)

User = get_user_model()


# ── Domain errors ─────────────────────────────────────────────────────────

class AdminClientProvisioningError(Exception):
    """Base class for all ADMIN-CLIENTES 02A provisioning domain errors."""


class UnauthorizedProvisioningActorError(AdminClientProvisioningError):
    """``granted_by`` is not an active platform-staff superadmin."""


class InvalidOwnerEmailError(AdminClientProvisioningError):
    """``owner_email`` is not a syntactically valid email address."""


class MultipleOwnerAccountsError(AdminClientProvisioningError):
    """More than one existing user matches ``owner_email`` case-insensitively."""


class InactiveOwnerAccountError(AdminClientProvisioningError):
    """The single existing user matching ``owner_email`` is inactive."""


class _OwnerConfirmationPrompt(AdminClientProvisioningError):
    """
    Base for the two errors that ask the admin to (re)confirm reusing an
    existing account. Carries a fresh confirmation token bound to the
    identity resolved right now, plus only the email the admin typed — never
    the account's other businesses, roles or profile data.
    """

    def __init__(self, message: str, *, confirmation_token: str, owner_email: str):
        super().__init__(message)
        self.confirmation_token = confirmation_token
        self.owner_email = owner_email

    def confirmation_payload(self) -> dict:
        return {
            'token': self.confirmation_token,
            'owner_email': self.owner_email,
            'expires_in_seconds': OWNER_CONFIRMATION_MAX_AGE_SECONDS,
        }


class ExistingOwnerRequiresConfirmationError(_OwnerConfirmationPrompt):
    """
    PROD-02F4 (all products): an existing, eligible account matches
    ``owner_email`` and the request did not confirm attaching it
    (``attach_existing_owner`` + ``owner_confirmation_token``).
    """


class ExistingOwnerConfirmationInvalidError(_OwnerConfirmationPrompt):
    """
    PROD-02F4: a confirmation was sent but it does not belong to the identity
    resolved now (email changed, account replaced, other admin, expired or
    tampered). Never reused: the admin must confirm the current identity.
    """


class OwnerAccountNotEligibleError(AdminClientProvisioningError):
    """
    PROD-02F4: the existing account can never become an owner through this
    flow (superuser, Django staff, platform staff, no AccountProfile, or
    credentials controllable by another business). ``reason`` is internal
    only (logs); the API answers one generic code.
    """

    def __init__(self, message: str, *, reason: str):
        super().__init__(message)
        self.reason = reason


class OwnerAccountConflictError(AdminClientProvisioningError):
    """PROD-02F4: a concurrent write created an account for the same email."""


# Confirmation tokens: signed, time-limited, and bound to the resolved
# identity (user pk + normalized email + date_joined) AND the admin.
OWNER_CONFIRMATION_MAX_AGE_SECONDS = 15 * 60
_OWNER_CONFIRMATION_SALT = 'accounts.admin_client_provisioning.owner_confirmation.v1'


class InvalidBusinessSlugError(AdminClientProvisioningError):
    """``business_slug`` fails canonical slug format validation."""


class DuplicateBusinessSlugError(AdminClientProvisioningError):
    """``business_slug`` is already used by another business."""


class InvalidBusinessNameError(AdminClientProvisioningError):
    """``business_name`` is blank/whitespace-only or exceeds Business.name.max_length."""


class InvalidBusinessCountryError(AdminClientProvisioningError):
    """``country`` is blank or exceeds Business.country's max_length."""


class InvalidBusinessCurrencyError(AdminClientProvisioningError):
    """``currency`` is blank or exceeds Business.currency's max_length."""


# ── grant_complimentary_access() taxonomy — mirrored 1:1 so callers can
#    distinguish causes without ever inspecting exception message strings.
class InvalidComplimentaryPeriodError(AdminClientProvisioningError):
    """complimentary_start/complimentary_end form an invalid period."""


class ComplimentaryPlanNotAvailableError(AdminClientProvisioningError):
    """plan_code does not exist or is not active in the Plan catalog."""


class ComplimentaryPlanServiceMismatchError(AdminClientProvisioningError):
    """plan_code's canonical vertical does not match service_type."""


class ActiveComplimentarySubscriptionConflictError(AdminClientProvisioningError):
    """business already has a non-canceled subscription for service_type."""


class InvalidComplimentaryGrantReasonError(AdminClientProvisioningError):
    """grant_reason is blank/whitespace-only."""


class InvalidComplimentaryServiceTypeError(AdminClientProvisioningError):
    """service_type is not a valid SubscriptionV2.ServiceType member."""


class InvalidComplimentaryUsageTierError(AdminClientProvisioningError):
    """usage_tier missing/invalid for a tier-priced plan, or sent for one without tiers."""


class InvalidComplimentaryCustomAllowanceError(AdminClientProvisioningError):
    """PROD-02F3: custom_included_sessions missing/invalid, misplaced, or no valid policy window."""


class ComplimentaryGrantFailedError(AdminClientProvisioningError):
    """
    ``grant_complimentary_access()`` rejected the operation for a reason that
    does not map to one of the specific causes above. Reserved exclusively
    for: (a) an unexpected *base* ``ComplimentaryAccessError`` instance (e.g.
    the internal missing-business/missing-actor guards, which a correctly-
    built provisioning call can never trigger), or (b) a genuinely
    unclassified cause. Never raised for a known cause, which always gets
    its own specific subclass instead. Technical/unexpected exceptions that
    are NOT a ComplimentaryAccessError are never caught or converted here.
    """


# ── Result ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AdminClientProvisioningResult:
    business: Business
    owner_user: 'UserType'
    membership: Membership
    subscription: SubscriptionV2
    owner_created: bool
    owner_reuse_confirmed: bool = False


# ── Actor authorization ──────────────────────────────────────────────────

def _authorize_actor(granted_by) -> 'UserType':
    """
    Only an existing, persisted, active user with AccountProfile.is_platform_staff
    and internal_role='superadmin' may provision a client. 'operations' is
    explicitly rejected — this is a sensitive operation the service protects
    itself, independent of any future endpoint's permission classes.

    granted_by is never mutated/reactivated here — only read. The argument
    itself is only used to extract a PK: every field actually checked
    (is_active, AccountProfile) is re-read fresh from the DB, since the
    instance handed to us may be stale (e.g. deactivated by another request
    after it was loaded). Returns that freshly-reloaded User — callers MUST
    use this return value (not the original argument) as the canonical
    actor for grant_complimentary_access(), AccessAuditLog entries, and any
    other record the provisioning writes.
    """
    if granted_by is None or not isinstance(granted_by, User):
        raise UnauthorizedProvisioningActorError(
            'El actor que otorga el acceso debe ser un usuario autenticable existente.'
        )

    pk = granted_by.pk
    if not pk:
        raise UnauthorizedProvisioningActorError(
            'El actor no existe realmente en la base de datos '
            '(usuario no persistido o eliminado).'
        )

    # Reload from the DB — the caller's instance may be stale.
    fresh_user = User.objects.filter(pk=pk).first()
    if fresh_user is None:
        raise UnauthorizedProvisioningActorError(
            'El actor no existe realmente en la base de datos '
            '(usuario no persistido o eliminado).'
        )

    if not fresh_user.is_active:
        raise UnauthorizedProvisioningActorError(
            'El actor administrador está inactivo.'
        )

    profile = AccountProfile.objects.filter(user_id=pk).first()
    if profile is None or not profile.is_platform_staff:
        raise UnauthorizedProvisioningActorError(
            'El actor no tiene permisos de personal interno (is_platform_staff=True).'
        )

    if profile.internal_role != AccountProfile.InternalRole.SUPERADMIN:
        raise UnauthorizedProvisioningActorError(
            f"El rol interno '{profile.internal_role}' no puede provisionar clientes. "
            f"Se requiere el rol 'superadmin'."
        )

    return fresh_user


# ── Business basic-data validation ───────────────────────────────────────

def _validate_business_basics(business_name: str, country: str, currency: str) -> tuple[str, str, str]:
    """
    Validate name/country/currency using only what the Business model itself
    already defines — this repo has no canonical ISO country/currency list
    (no choices, validators, or third-party package for it), so the minimal
    honest validation is: non-blank, and within the model field's real
    max_length (Business.country=CharField(max_length=2),
    Business.currency=CharField(max_length=3)). Model.objects.create() does
    NOT call full_clean(), so this must be checked explicitly here.
    """
    clean_name = (business_name or '').strip()
    if not clean_name:
        raise InvalidBusinessNameError('El nombre del negocio es obligatorio.')
    name_max_length = Business._meta.get_field('name').max_length
    if len(clean_name) > name_max_length:
        raise InvalidBusinessNameError(
            f"El nombre del negocio supera el máximo permitido "
            f"({name_max_length} caracteres)."
        )

    clean_country = (country or '').strip().upper()
    country_max_length = Business._meta.get_field('country').max_length
    if not clean_country or len(clean_country) > country_max_length:
        raise InvalidBusinessCountryError(
            f"El país '{country}' es inválido: debe ser no vacío y de a lo sumo "
            f"{country_max_length} caracteres (Business.country no tiene una "
            f"fuente canónica de códigos ISO en este repositorio)."
        )

    clean_currency = (currency or '').strip().upper()
    currency_max_length = Business._meta.get_field('currency').max_length
    if not clean_currency or len(clean_currency) > currency_max_length:
        raise InvalidBusinessCurrencyError(
            f"La moneda '{currency}' es inválida: debe ser no vacía y de a lo sumo "
            f"{currency_max_length} caracteres (Business.currency no tiene una "
            f"fuente canónica de códigos ISO en este repositorio)."
        )

    return clean_name, clean_country, clean_currency


# ── Slug validation ───────────────────────────────────────────────────────

def _validate_business_slug(raw_slug: str) -> str:
    """
    Reuse the canonical Business.slug validator (format + DB uniqueness)
    from apps.reviews.admin_service.validate_slug, splitting its single
    ValueError into the two distinct domain errors this service exposes.
    """
    from apps.reviews.admin_service import validate_slug as _canonical_validate_slug

    if not raw_slug or not raw_slug.strip():
        raise InvalidBusinessSlugError('El slug del negocio es obligatorio.')

    try:
        return _canonical_validate_slug(raw_slug)
    except ValueError as exc:
        message = str(exc)
        if 'ya está en uso' in message:
            raise DuplicateBusinessSlugError(message) from exc
        raise InvalidBusinessSlugError(message) from exc


# ── Owner resolution ──────────────────────────────────────────────────────

def _normalize_owner_email(owner_email: str) -> str:
    normalized_email = (owner_email or '').strip().lower()
    try:
        validate_email(normalized_email)
    except DjangoValidationError as exc:
        raise InvalidOwnerEmailError(
            f"El email de owner '{owner_email}' no es válido."
        ) from exc
    return normalized_email


def _lock_owner_email(normalized_email: str) -> None:
    """
    Serialize concurrent provisionings of the same owner email (transaction-
    scoped PostgreSQL advisory lock): the second one waits and then resolves
    the account the first one created, instead of creating a duplicate.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT pg_advisory_xact_lock(hashtext(%s))',
            [f'admin_client_provisioning.owner:{normalized_email}'],
        )


def _identity_digest(user, normalized_email: str, actor) -> str:
    joined = user.date_joined.isoformat() if user.date_joined else ''
    raw = f'{user.pk}|{normalized_email}|{joined}|{actor.pk}'
    return hashlib.sha256(raw.encode()).hexdigest()


def _issue_owner_confirmation(user, normalized_email: str, actor) -> str:
    """Opaque token: reveals nothing about the account (only a digest)."""
    return signing.TimestampSigner(salt=_OWNER_CONFIRMATION_SALT).sign(
        _identity_digest(user, normalized_email, actor),
    )


def _owner_confirmation_matches(token: str | None, user, normalized_email: str, actor) -> bool:
    if not token:
        return False
    try:
        digest = signing.TimestampSigner(salt=_OWNER_CONFIRMATION_SALT).unsign(
            token, max_age=OWNER_CONFIRMATION_MAX_AGE_SECONDS,
        )
    except signing.BadSignature:  # includes SignatureExpired
        return False
    return constant_time_compare(digest, _identity_digest(user, normalized_email, actor))


def _credentials_controlled_by_other_business(user) -> bool:
    """
    True when someone OTHER than ``user`` can take over its credentials:
    owner endpoints let any owner of a business family reset the password of /
    disable every account with a membership in that family, and operational
    EmployeeProfiles are managed by their business. Making such an account the
    owner of a new client would hand that client to a third party.
    """
    from apps.accounts.models import EmployeeProfile

    if EmployeeProfile.objects.filter(linked_user=user).exists():
        return True

    family_ids: set[int] = set()
    for business_id, parent_id in Membership.objects.filter(user=user).values_list(
        'business_id', 'business__parent_id',
    ):
        hq_id = parent_id or business_id
        family_ids.add(hq_id)
    if not family_ids:
        return False
    family_q = Q(business_id__in=family_ids) | Q(business__parent_id__in=family_ids)
    return Membership.objects.filter(family_q, role='owner').exclude(user=user).exists()


def _check_existing_owner_eligibility(user, normalized_email: str) -> None:
    """Re-read fresh inside the transaction (the row is already locked)."""
    if not user.is_active:
        raise InactiveOwnerAccountError(
            f"El usuario existente con email '{normalized_email}' está inactivo. "
            f"No se reactiva silenciosamente."
        )
    profile = AccountProfile.objects.filter(user_id=user.pk).first()
    if profile is not None and profile.account_status == AccountProfile.AccountStatus.SUSPENDED:
        raise InactiveOwnerAccountError(
            f"La cuenta existente con email '{normalized_email}' está suspendida."
        )

    reason = None
    if user.is_superuser or user.is_staff:
        reason = 'superuser_or_staff'
    elif profile is None:
        reason = 'missing_profile'
    elif profile.is_platform_staff or profile.internal_role:
        reason = 'platform_staff'
    elif _credentials_controlled_by_other_business(user):
        reason = 'credentials_controlled_by_other_business'
    if reason is not None:
        logger.warning(
            '[admin_client_provisioning] existing owner not eligible user=%s reason=%s',
            user.pk, reason,
        )
        raise OwnerAccountNotEligibleError(
            'La cuenta existente no puede ser propietaria de un cliente nuevo.', reason=reason,
        )


def _resolve_owner(
    owner_email: str,
    *,
    actor,
    attach_existing_owner: bool,
    owner_confirmation_token: str | None,
) -> tuple['UserType', bool]:
    """
    Resolve owner_email to exactly one User. MUST run inside the provisioning
    transaction (advisory lock + row lock live until commit/rollback).

      - 0 matches  -> create a new, active, unusable-password, pre-authorized
                      account (no email sent, no google_sub, no staff grant).
      - 1 match    -> eligible + explicitly confirmed for THIS identity and
                      admin -> reused as-is (never mutated); otherwise a
                      confirmation prompt with a fresh bound token.
      - 2+ matches -> domain error (never chosen arbitrarily).
    """
    normalized_email = _normalize_owner_email(owner_email)
    _lock_owner_email(normalized_email)

    matches = list(
        User.objects.select_for_update().filter(email__iexact=normalized_email).order_by('pk')
    )

    if len(matches) > 1:
        raise MultipleOwnerAccountsError(
            f"Existen {len(matches)} cuentas con el email '{normalized_email}' "
            f"(comparación case-insensitive). No se elige una arbitrariamente."
        )

    if len(matches) == 1:
        user = matches[0]
        _check_existing_owner_eligibility(user, normalized_email)
        if not attach_existing_owner:
            raise ExistingOwnerRequiresConfirmationError(
                'Ya existe una cuenta con ese email. Confirmá que querés asociarla como propietaria.',
                confirmation_token=_issue_owner_confirmation(user, normalized_email, actor),
                owner_email=normalized_email,
            )
        if not _owner_confirmation_matches(owner_confirmation_token, user, normalized_email, actor):
            raise ExistingOwnerConfirmationInvalidError(
                'La confirmación no corresponde a la cuenta identificada ahora. Volvé a confirmar.',
                confirmation_token=_issue_owner_confirmation(user, normalized_email, actor),
                owner_email=normalized_email,
            )
        return user, False

    # ── No existing account — create a pre-authorized owner account ───────
    # A confirmation sent for an account that no longer exists is simply
    # irrelevant: this is the regular new-owner path.
    try:
        with transaction.atomic():
            user = User.objects.create_user(username=normalized_email, email=normalized_email)
    except IntegrityError as exc:
        raise OwnerAccountConflictError(
            'Otra operación creó una cuenta con ese email al mismo tiempo. Reintentá el alta.'
        ) from exc
    user.set_unusable_password()
    user.save(update_fields=['password'])
    return user, True


# ── Public entry point ────────────────────────────────────────────────────

def provision_admin_client(
    *,
    business_name: str,
    business_slug: str,
    service_type: str,
    country: str,
    currency: str,
    owner_email: str,
    plan_code: str,
    complimentary_start: datetime,
    complimentary_end: datetime,
    granted_by,
    grant_reason: str,
    usage_tier: str | None = None,
    custom_included_sessions: int | None = None,
    attach_existing_owner: bool = False,
    owner_confirmation_token: str | None = None,
) -> AdminClientProvisioningResult:
    """
    Atomically provision a platform-admin-created client:
    root Business + owner User (new or reused) + owner Membership +
    complimentary SubscriptionV2 (via grant_complimentary_access).

    Raises AdminClientProvisioningError subclasses on any validation
    failure. On any failure the whole operation rolls back — including a
    newly-created owner user — except a pre-existing owner user, which is
    never created/deleted/modified by this service in the first place.

    PROD-02F4: an existing account is attached only when it is eligible and
    the call carries ``attach_existing_owner=True`` plus the confirmation
    token issued for that exact identity and admin (see ``_resolve_owner``);
    the mandatory ADMIN_CLIENT_CREATED / ADMIN_OWNER_PREAUTHORIZED audit rows
    are written in the same transaction and any failure rolls everything back.
    """
    # _authorize_actor returns a freshly-reloaded User — use it (not the
    # original argument) as the canonical actor for the rest of this call.
    granted_by = _authorize_actor(granted_by)

    clean_slug = _validate_business_slug(business_slug)
    clean_name, clean_country, clean_currency = _validate_business_basics(
        business_name, country, currency,
    )

    with transaction.atomic():
        owner_user, owner_created = _resolve_owner(
            owner_email,
            actor=granted_by,
            attach_existing_owner=attach_existing_owner,
            owner_confirmation_token=owner_confirmation_token,
        )
        owner_reuse_confirmed = not owner_created

        # ── Root Business — explicit slug, never silently re-suffixed ─────
        # Business.save() only auto-generates a slug when none is given, so
        # our explicit, pre-validated slug is preserved verbatim. A nested
        # atomic() isolates the DB-level unique constraint as a last-resort
        # guard against a concurrent duplicate submission.
        try:
            with transaction.atomic():
                business = Business.objects.create(
                    name=clean_name,
                    parent=None,
                    slug=clean_slug,
                    service_type=service_type,
                    default_service=service_type,
                    country=clean_country,
                    currency=clean_currency,
                    status='onboarding',
                )
        except IntegrityError as exc:
            raise DuplicateBusinessSlugError(
                f"El slug '{clean_slug}' ya está en uso por otro negocio "
                f"(conflicto detectado al confirmar la escritura)."
            ) from exc

        # ── Single owner Membership — never consumes a seat (role=owner
        #    is skipped entirely by accounts.models.check_seat_limit) ──────
        membership = Membership.objects.create(
            user=owner_user,
            business=business,
            role='owner',
            status=Membership.Status.ACTIVE,
            created_by_user=granted_by,
        )

        # ── Complimentary access — canonical service owns plan/service
        #    validation, external_reference, Business.status advance to
        #    'trialing', and its own ADMIN_COMPLIMENTARY_ACCESS_GRANTED log ──
        try:
            subscription = grant_complimentary_access(
                business=business,
                plan_code=plan_code,
                service_type=service_type,
                starts_at=complimentary_start,
                ends_at=complimentary_end,
                granted_by=granted_by,
                reason=grant_reason,
                usage_tier=usage_tier,
                custom_included_sessions=custom_included_sessions,
            )
        except InvalidPeriodError as exc:
            raise InvalidComplimentaryPeriodError(str(exc)) from exc
        except InvalidGrantReasonError as exc:
            raise InvalidComplimentaryGrantReasonError(str(exc)) from exc
        except InvalidServiceTypeError as exc:
            raise InvalidComplimentaryServiceTypeError(str(exc)) from exc
        except InvalidUsageTierError as exc:
            raise InvalidComplimentaryUsageTierError(str(exc)) from exc
        except InvalidCustomAllowanceError as exc:
            raise InvalidComplimentaryCustomAllowanceError(str(exc)) from exc
        except PlanNotAvailableError as exc:
            raise ComplimentaryPlanNotAvailableError(str(exc)) from exc
        except PlanServiceMismatchError as exc:
            raise ComplimentaryPlanServiceMismatchError(str(exc)) from exc
        except ActiveSubscriptionConflictError as exc:
            raise ActiveComplimentarySubscriptionConflictError(str(exc)) from exc
        except ComplimentaryAccessError as exc:
            raise ComplimentaryGrantFailedError(str(exc)) from exc

        # ── Mandatory provisioning audit (same transaction, never best
        #    effort): no secrets, tokens or raw payloads are recorded ─────
        custom_policy_id = None
        if custom_included_sessions is not None:
            from apps.billing.models import ReceptionAIUsagePolicy

            custom_policy_id = (
                ReceptionAIUsagePolicy.objects.filter(subscription=subscription)
                .order_by('created_at').values_list('pk', flat=True).first()
            )
        shared_details = {
            'business_id': business.pk,
            'owner_user_id': owner_user.pk,
            'owner_email': owner_user.email,
            'owner_created': owner_created,
            'owner_account': 'created' if owner_created else 'reused',
            'owner_reuse_confirmed': owner_reuse_confirmed,
            'membership_id': membership.pk,
            'subscription_id': str(subscription.pk),
            'service_type': service_type,
            'plan_code': plan_code,
            'usage_tier': subscription.usage_tier,
            'custom_included_sessions': custom_included_sessions,
            'custom_policy_id': str(custom_policy_id) if custom_policy_id else None,
            'complimentary_start': complimentary_start.isoformat(),
            'complimentary_end': complimentary_end.isoformat(),
            'grant_reason': (grant_reason or '').strip(),
        }

        record_platform_action(
            action='ADMIN_CLIENT_CREATED',
            actor=granted_by,
            target_user=owner_user,
            business=business,
            entity_type='business',
            entity_id=str(business.pk),
            details={**shared_details, 'business_slug': business.slug},
        )
        record_platform_action(
            action='ADMIN_OWNER_PREAUTHORIZED',
            actor=granted_by,
            target_user=owner_user,
            business=business,
            entity_type='membership',
            entity_id=str(membership.pk),
            details=shared_details,
        )

    logger.info(
        "[admin_client_provisioning] business=%s owner=%s (created=%s, reuse_confirmed=%s) "
        "membership=%s subscription=%s admin=%s",
        business.pk, owner_user.pk, owner_created, owner_reuse_confirmed, membership.pk,
        subscription.pk, granted_by.pk,
    )

    return AdminClientProvisioningResult(
        business=business,
        owner_user=owner_user,
        membership=membership,
        subscription=subscription,
        owner_created=owner_created,
        owner_reuse_confirmed=owner_reuse_confirmed,
    )
