"""
accounts/admin_client_service_addition.py — PROD-02F5

Add an internally-provisionable service (Recepcionista IA fixed/Custom,
Turnos, Gestión, …) to an EXISTING HQ Business as a complimentary
("bonificado") benefit — the only modality of this flow.

Reuses ``grant_complimentary_access`` (eligibility policy, validators, lock
order Business → SubscriptionV2, AI exclusion and usage-continuity rules,
Custom policy + its audit, mandatory ADMIN_COMPLIMENTARY_ACCESS_GRANTED
audit) inside ONE transaction. Never touches the Business identity
(service_type, default_service, status), its owner, users, memberships,
permission overrides, customers or other subscriptions, and never creates
agents, channels or credentials.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction

from apps.accounts.admin_client_provisioning_service import (
    AdminClientProvisioningError,
    _authorize_actor,
    grant_with_domain_errors,
)
from apps.billing.models import ReceptionAIUsagePolicy, SubscriptionV2
from apps.business.models import Business

logger = logging.getLogger(__name__)


class ClientNotFoundError(AdminClientProvisioningError):
    """No HQ Business with that id (missing, or a branch)."""


class ClientStatusNotEligibleError(AdminClientProvisioningError):
    """
    The Business is not operational (only 'active' and 'trialing' qualify).
    A benefit never reactivates a past_due/suspended/canceled Business nor
    advances an onboarding one: its global status is never changed here.
    """


# Only an operational Business may receive a new service. The global status
# is never written by this flow (see ClientStatusNotEligibleError).
ELIGIBLE_BUSINESS_STATUSES = frozenset({'active', 'trialing'})


@dataclass(frozen=True)
class ClientServiceAdditionResult:
    business: Business
    subscription: SubscriptionV2
    custom_policy: ReceptionAIUsagePolicy | None


def add_service_to_client(
    *,
    business_id: int,
    service_type: str,
    plan_code: str,
    complimentary_start: datetime,
    complimentary_end: datetime,
    granted_by,
    grant_reason: str,
    usage_tier: str | None = None,
    custom_included_sessions: int | None = None,
) -> ClientServiceAdditionResult:
    granted_by = _authorize_actor(granted_by)

    with transaction.atomic():
        # Lock order Business → SubscriptionV2 (grant re-locks the same row).
        business = (
            Business.objects.select_for_update()
            .filter(pk=business_id, parent__isnull=True)
            .first()
        )
        if business is None:
            raise ClientNotFoundError('No existe un cliente (negocio principal) con ese id.')
        if business.status not in ELIGIBLE_BUSINESS_STATUSES:
            raise ClientStatusNotEligibleError(
                f"El negocio está '{business.status}': solo se agregan servicios a negocios "
                f"activos o en período bonificado/trial. No se reactiva ni se cambia su estado."
            )

        subscription = grant_with_domain_errors(
            business=business,
            plan_code=plan_code,
            service_type=service_type,
            starts_at=complimentary_start,
            ends_at=complimentary_end,
            granted_by=granted_by,
            reason=grant_reason,
            usage_tier=usage_tier,
            custom_included_sessions=custom_included_sessions,
            audit_operation='client_service_added',
        )
        custom_policy = (
            ReceptionAIUsagePolicy.objects.filter(subscription=subscription).order_by('created_at').first()
            if custom_included_sessions is not None else None
        )

    logger.info(
        '[admin_client_service_addition] business=%s subscription=%s service=%s plan=%s tier=%s admin=%s',
        business.pk, subscription.pk, service_type, plan_code, subscription.usage_tier, granted_by.pk,
    )
    return ClientServiceAdditionResult(business=business, subscription=subscription, custom_policy=custom_policy)
