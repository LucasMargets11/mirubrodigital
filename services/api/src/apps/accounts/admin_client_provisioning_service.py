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

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from apps.accounts.models import AccountProfile, Membership
from apps.accounts.platform_audit import log_platform_action
from apps.billing.complimentary_access_service import (
    ActiveSubscriptionConflictError,
    ComplimentaryAccessError,
    InvalidGrantReasonError,
    InvalidPeriodError,
    InvalidServiceTypeError,
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

def _resolve_owner(owner_email: str) -> tuple['UserType', bool]:
    """
    Normalize + validate owner_email, then resolve to exactly one User:
      - 0 matches  -> create a new, active, unusable-password, pre-authorized
                      account (no email sent, no verification, no google_sub,
                      no platform-staff grant).
      - 1 match    -> reuse as-is (reject if inactive; never mutate it).
      - 2+ matches -> domain error (never chosen arbitrarily).
    """
    normalized_email = (owner_email or '').strip().lower()

    try:
        validate_email(normalized_email)
    except DjangoValidationError as exc:
        raise InvalidOwnerEmailError(
            f"El email de owner '{owner_email}' no es válido."
        ) from exc

    matches = list(User.objects.filter(email__iexact=normalized_email))

    if len(matches) > 1:
        raise MultipleOwnerAccountsError(
            f"Existen {len(matches)} cuentas con el email '{normalized_email}' "
            f"(comparación case-insensitive). No se elige una arbitrariamente."
        )

    if len(matches) == 1:
        user = matches[0]
        if not user.is_active:
            raise InactiveOwnerAccountError(
                f"El usuario existente con email '{normalized_email}' está inactivo. "
                f"No se reactiva silenciosamente."
            )
        return user, False

    # ── No existing account — create a pre-authorized owner account ───────
    user = User.objects.create_user(username=normalized_email, email=normalized_email)
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
) -> AdminClientProvisioningResult:
    """
    Atomically provision a platform-admin-created client:
    root Business + owner User (new or reused) + owner Membership +
    complimentary SubscriptionV2 (via grant_complimentary_access).

    Raises AdminClientProvisioningError subclasses on any validation
    failure. On any failure the whole operation rolls back — including a
    newly-created owner user — except a pre-existing owner user, which is
    never created/deleted/modified by this service in the first place.
    """
    # _authorize_actor returns a freshly-reloaded User — use it (not the
    # original argument) as the canonical actor for the rest of this call.
    granted_by = _authorize_actor(granted_by)

    clean_slug = _validate_business_slug(business_slug)
    clean_name, clean_country, clean_currency = _validate_business_basics(
        business_name, country, currency,
    )

    with transaction.atomic():
        owner_user, owner_created = _resolve_owner(owner_email)

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
            )
        except InvalidPeriodError as exc:
            raise InvalidComplimentaryPeriodError(str(exc)) from exc
        except InvalidGrantReasonError as exc:
            raise InvalidComplimentaryGrantReasonError(str(exc)) from exc
        except InvalidServiceTypeError as exc:
            raise InvalidComplimentaryServiceTypeError(str(exc)) from exc
        except PlanNotAvailableError as exc:
            raise ComplimentaryPlanNotAvailableError(str(exc)) from exc
        except PlanServiceMismatchError as exc:
            raise ComplimentaryPlanServiceMismatchError(str(exc)) from exc
        except ActiveSubscriptionConflictError as exc:
            raise ActiveComplimentarySubscriptionConflictError(str(exc)) from exc
        except ComplimentaryAccessError as exc:
            raise ComplimentaryGrantFailedError(str(exc)) from exc

        # ── Provisioning-specific audit trail (same transaction) ─────────
        shared_details = {
            'business_id': business.pk,
            'owner_user_id': owner_user.pk,
            'owner_email': owner_user.email,
            'owner_created': owner_created,
            'membership_id': membership.pk,
            'service_type': service_type,
            'plan_code': plan_code,
            'complimentary_start': complimentary_start.isoformat(),
            'complimentary_end': complimentary_end.isoformat(),
        }

        log_platform_action(
            action='ADMIN_CLIENT_CREATED',
            actor=granted_by,
            target_user=owner_user,
            business=business,
            entity_type='business',
            entity_id=str(business.pk),
            details={**shared_details, 'business_slug': business.slug},
        )
        log_platform_action(
            action='ADMIN_OWNER_PREAUTHORIZED',
            actor=granted_by,
            target_user=owner_user,
            business=business,
            entity_type='membership',
            entity_id=str(membership.pk),
            details=shared_details,
        )

    logger.info(
        "[admin_client_provisioning] business=%s owner=%s (created=%s) "
        "membership=%s subscription=%s admin=%s",
        business.pk, owner_user.pk, owner_created, membership.pk,
        subscription.pk, granted_by.pk,
    )

    return AdminClientProvisioningResult(
        business=business,
        owner_user=owner_user,
        membership=membership,
        subscription=subscription,
        owner_created=owner_created,
    )
