"""S8E internal contract. No provider SDK, network, payment, invoice or tax operations."""
from __future__ import annotations

import re
import uuid

from django.db import transaction
from django.utils import timezone

from apps.appointments.models import AppointmentAIUsageBillingIntent, AppointmentAIUsageSettlement
from apps.appointments.services.ai_usage import AIUsageUnavailable
from apps.billing.models import SubscriptionV2


class AIUsageBillingIntentConflict(AIUsageUnavailable):
    """The requested transition is not valid for the persisted attempt."""


_FAILURES = {
    'provider_error': 'Provider processing failed; outcome requires reconciliation.',
    'declined': 'Provider declined the operation.',
    'timeout': 'Provider outcome is unknown; reconciliation is required.',
    'zero_amount': 'Zero amount; no provider operation is required.',
    'canceled': 'Internal billing preparation was voided.',
}


@transaction.atomic
def prepare_ai_usage_billing_intent(
    settlement: AppointmentAIUsageSettlement,
) -> AppointmentAIUsageBillingIntent:
    """Copy only finalized S8D economics; never resolve pricing, access or usage."""
    try:
        frozen = AppointmentAIUsageSettlement.objects.select_for_update().get(pk=settlement.pk)
    except AppointmentAIUsageSettlement.DoesNotExist as exc:
        raise AIUsageUnavailable('The usage settlement does not exist.') from exc
    if (
        frozen.status != 'finalized' or frozen.finalized_at is None
        or frozen.currency != 'ARS' or type(frozen.overage_amount) is not int
        or frozen.overage_amount < 0
        or not SubscriptionV2.objects.filter(
            pk=frozen.subscription_id, business_id=frozen.business_id,
        ).exists()
    ):
        raise AIUsageUnavailable('The usage settlement has inconsistent finalized evidence.')
    existing = AppointmentAIUsageBillingIntent.objects.filter(settlement=frozen).first()
    if existing is not None:
        return existing
    zero = frozen.overage_amount == 0
    return AppointmentAIUsageBillingIntent.objects.create(
        settlement=frozen, business_id=frozen.business_id, subscription_id=frozen.subscription_id,
        amount=frozen.overage_amount, currency=frozen.currency,
        external_reference=f'MIRUBRO-AI-OVERAGE-{frozen.pk}',
        status='void' if zero else 'pending',
        completed_at=timezone.now() if zero else None,
        failure_code='zero_amount' if zero else None,
        failure_message=_FAILURES['zero_amount'] if zero else None,
    )


def _locked(intent: AppointmentAIUsageBillingIntent) -> AppointmentAIUsageBillingIntent:
    try:
        return AppointmentAIUsageBillingIntent.objects.select_for_update().get(pk=intent.pk)
    except AppointmentAIUsageBillingIntent.DoesNotExist as exc:
        raise AIUsageBillingIntentConflict('The billing intent does not exist.') from exc


def _require_attempt(intent: AppointmentAIUsageBillingIntent, attempt_token: uuid.UUID) -> None:
    if not isinstance(attempt_token, uuid.UUID) or intent.attempt_token != attempt_token:
        raise AIUsageBillingIntentConflict('The billing attempt token does not match.')


@transaction.atomic
def claim_ai_usage_billing_intent(
    intent: AppointmentAIUsageBillingIntent,
) -> AppointmentAIUsageBillingIntent:
    current = _locked(intent)
    if current.status != 'pending':
        raise AIUsageBillingIntentConflict('Only a pending billing intent can be claimed.')
    current.status = 'processing'
    current.attempt_token = uuid.uuid4()
    current.processing_started_at = timezone.now()
    current.save(update_fields=['status', 'attempt_token', 'processing_started_at', 'updated_at'])
    return current


def _provider_result(provider: str, provider_reference: str | None) -> None:
    if not isinstance(provider, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', provider):
        raise AIUsageBillingIntentConflict('Invalid provider identifier.')
    if provider_reference is not None and (
        not isinstance(provider_reference, str)
        or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', provider_reference)
    ):
        raise AIUsageBillingIntentConflict('Invalid provider result reference.')


@transaction.atomic
def mark_ai_usage_billing_intent_succeeded(
    intent: AppointmentAIUsageBillingIntent, *, attempt_token: uuid.UUID,
    provider: str, provider_reference: str,
) -> AppointmentAIUsageBillingIntent:
    _provider_result(provider, provider_reference)
    if not provider_reference:
        raise AIUsageBillingIntentConflict('A successful provider result requires a reference.')
    current = _locked(intent)
    _require_attempt(current, attempt_token)
    if current.status != 'processing':
        raise AIUsageBillingIntentConflict('Only the current processing attempt can succeed.')
    current.status = 'succeeded'
    current.provider = provider
    current.provider_reference = provider_reference
    current.completed_at = timezone.now()
    current.save(update_fields=[
        'status', 'provider', 'provider_reference', 'completed_at', 'updated_at',
    ])
    return current


@transaction.atomic
def mark_ai_usage_billing_intent_failed(
    intent: AppointmentAIUsageBillingIntent, *, attempt_token: uuid.UUID,
    provider: str, failure_code: str, failure_message: str | None = None,
    provider_reference: str | None = None,
) -> AppointmentAIUsageBillingIntent:
    """Raw provider messages are deliberately discarded, not regex-redacted."""
    _provider_result(provider, provider_reference)
    current = _locked(intent)
    _require_attempt(current, attempt_token)
    if current.status != 'processing':
        raise AIUsageBillingIntentConflict('Only the current processing attempt can fail.')
    code = failure_code if failure_code in ('declined', 'timeout') else 'provider_error'
    current.status = 'failed'
    current.provider = provider
    current.provider_reference = provider_reference
    current.failure_code = code
    current.failure_message = _FAILURES[code]
    current.completed_at = timezone.now()
    current.save(update_fields=[
        'status', 'provider', 'provider_reference', 'failure_code', 'failure_message',
        'completed_at', 'updated_at',
    ])
    return current


@transaction.atomic
def retry_ai_usage_billing_intent(
    intent: AppointmentAIUsageBillingIntent, *, attempt_token: uuid.UUID,
    confirmed_no_charge: bool,
) -> AppointmentAIUsageBillingIntent:
    """Explicit reconciliation gate; unknown provider outcomes must never be retried."""
    current = _locked(intent)
    _require_attempt(current, attempt_token)
    if current.status != 'failed' or confirmed_no_charge is not True:
        raise AIUsageBillingIntentConflict('Retry requires a failed attempt and confirmed no charge.')
    current.status = 'pending'
    for field in (
        'attempt_token', 'processing_started_at', 'completed_at', 'provider',
        'provider_reference', 'failure_code', 'failure_message',
    ):
        setattr(current, field, None)
    current.save(update_fields=[
        'status', 'attempt_token', 'processing_started_at', 'completed_at', 'provider',
        'provider_reference', 'failure_code', 'failure_message', 'updated_at',
    ])
    return current


@transaction.atomic
def void_ai_usage_billing_intent(
    intent: AppointmentAIUsageBillingIntent,
) -> AppointmentAIUsageBillingIntent:
    current = _locked(intent)
    if current.status not in ('pending', 'failed'):
        raise AIUsageBillingIntentConflict('Only pending or failed billing preparation can be voided.')
    current.status = 'void'
    current.completed_at = timezone.now()
    current.failure_code = 'canceled'
    current.failure_message = _FAILURES['canceled']
    current.save(update_fields=[
        'status', 'completed_at', 'failure_code', 'failure_message', 'updated_at',
    ])
    return current
