"""S8F provider boundary. No real payment provider is registered."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Literal, Protocol

from django.conf import settings
from django.db import transaction

from apps.appointments.models import (
    AppointmentAIUsageBillingAttempt, AppointmentAIUsageBillingIntent,
)
from apps.appointments.services.ai_usage_billing_intent import (
    AIUsageBillingIntentConflict,
    _locked,
    _provider_result,
    _require_attempt,
    claim_ai_usage_billing_intent,
    mark_ai_usage_billing_intent_failed,
    mark_ai_usage_billing_intent_succeeded,
)

logger = logging.getLogger(__name__)
ProviderStatus = Literal['succeeded', 'failed', 'outcome_unknown']
_FAILURE_CODES = {
    'declined', 'provider_not_enabled', 'provider_error', 'timeout', 'dispatch_incomplete',
}


@dataclass(frozen=True)
class AIUsageBillingRequest:
    intent_id: uuid.UUID
    amount: int
    currency: str
    external_reference: str

    @property
    def idempotency_key(self) -> str:
        return self.external_reference


@dataclass(frozen=True)
class AIUsageBillingResult:
    status: ProviderStatus
    provider_reference: str | None = None
    failure_code: str | None = None

    def __post_init__(self) -> None:
        if self.status not in ('succeeded', 'failed', 'outcome_unknown'):
            raise AIUsageBillingIntentConflict('Invalid normalized provider status.')
        _provider_result('normalized', self.provider_reference)
        if self.status == 'succeeded' and not self.provider_reference:
            raise AIUsageBillingIntentConflict('Provider success requires a reference.')
        code = None if self.status == 'succeeded' else (
            self.failure_code if self.failure_code in _FAILURE_CODES else 'provider_error'
        )
        if self.status == 'failed' and code not in ('declined', 'provider_not_enabled'):
            object.__setattr__(self, 'status', 'outcome_unknown')
        object.__setattr__(self, 'failure_code', code)


class AIUsageBillingProvider(Protocol):
    """Use external_reference as remote idempotency key and validate response correlation.

    A failed result must establish no charge; ambiguous responses must remain unknown.
    """

    name: str

    def charge(self, request: AIUsageBillingRequest) -> AIUsageBillingResult: ...

    def get_status(
        self, provider_reference: str, *, external_reference: str,
    ) -> AIUsageBillingResult: ...


class DisabledAIUsageBillingProvider:
    name = 'disabled'

    def charge(self, request: AIUsageBillingRequest) -> AIUsageBillingResult:
        return AIUsageBillingResult('failed', failure_code='provider_not_enabled')

    def get_status(
        self, provider_reference: str, *, external_reference: str,
    ) -> AIUsageBillingResult:
        # A disabled adapter cannot establish that an earlier operation did not charge.
        return AIUsageBillingResult(
            'outcome_unknown', provider_reference, 'provider_not_enabled',
        )


def get_ai_usage_billing_provider() -> AIUsageBillingProvider:
    if getattr(settings, 'AI_USAGE_BILLING_PROVIDER', 'disabled') != 'disabled':
        logger.warning('AI usage billing provider not enabled; using disabled adapter.')
    return DisabledAIUsageBillingProvider()


def _request(intent: AppointmentAIUsageBillingIntent) -> AIUsageBillingRequest:
    if type(intent.amount) is not int or intent.amount <= 0 or intent.currency != 'ARS':
        raise AIUsageBillingIntentConflict('Provider requires a positive frozen ARS amount.')
    return AIUsageBillingRequest(
        intent.pk, intent.amount, intent.currency, intent.external_reference,
    )


@transaction.atomic(durable=True)
def _reserve(
    intent: AppointmentAIUsageBillingIntent, provider: AIUsageBillingProvider,
    attempt_token: uuid.UUID | None,
) -> tuple[AppointmentAIUsageBillingIntent, AIUsageBillingRequest]:
    _provider_result(provider.name, None)
    current = _locked(intent)
    request = _request(current)
    if current.provider_attempts.filter(status='outcome_unknown').exists():
        raise AIUsageBillingIntentConflict('An unresolved provider operation blocks dispatch.')
    if attempt_token is None:
        current = claim_ai_usage_billing_intent(current)
    else:
        _require_attempt(current, attempt_token)
        if current.status != 'processing':
            raise AIUsageBillingIntentConflict('Only the current claim can dispatch.')
    if current.provider_attempts.filter(attempt_token=current.attempt_token).exists():
        raise AIUsageBillingIntentConflict('This claim was already dispatched.')
    AppointmentAIUsageBillingAttempt.objects.create(
        intent=current, attempt_token=current.attempt_token, provider=provider.name,
        status='outcome_unknown', failure_code='dispatch_incomplete',
    )
    return current, request


def process_ai_usage_billing_intent(
    intent: AppointmentAIUsageBillingIntent, *, provider: AIUsageBillingProvider | None = None,
    attempt_token: uuid.UUID | None = None,
) -> AppointmentAIUsageBillingIntent:
    """Reserve durably before dispatch. Injection is for internal fakes, not configuration."""
    adapter = provider if provider is not None else get_ai_usage_billing_provider()
    current, request = _reserve(intent, adapter, attempt_token)
    try:
        result = adapter.charge(request)
    except (TimeoutError, ConnectionError):
        logger.warning('AI usage billing dispatch outcome unknown; reconciliation required.')
        result = AIUsageBillingResult('outcome_unknown', failure_code='timeout')
    return record_ai_usage_billing_result(
        current, attempt_token=current.attempt_token, result=result,
    )


@transaction.atomic
def record_ai_usage_billing_result(
    intent: AppointmentAIUsageBillingIntent, *, attempt_token: uuid.UUID,
    result: AIUsageBillingResult,
) -> AppointmentAIUsageBillingIntent:
    """Apply late or immediate normalized evidence only to the current reserved claim."""
    if not isinstance(result, AIUsageBillingResult):
        raise AIUsageBillingIntentConflict('A normalized provider result is required.')
    current = _locked(intent)
    _require_attempt(current, attempt_token)
    if current.status != 'processing':
        raise AIUsageBillingIntentConflict('The provider claim is no longer processing.')
    try:
        attempt = current.provider_attempts.select_for_update().get(attempt_token=attempt_token)
    except AppointmentAIUsageBillingAttempt.DoesNotExist as exc:
        raise AIUsageBillingIntentConflict('The claim has no provider reservation.') from exc
    if attempt.status != 'outcome_unknown':
        raise AIUsageBillingIntentConflict('The provider result is already final.')
    if (
        attempt.provider_reference is not None
        and attempt.provider_reference != result.provider_reference
    ):
        raise AIUsageBillingIntentConflict('The provider reference cannot be replaced or cleared.')
    attempt.provider_reference = result.provider_reference
    attempt.status = result.status
    attempt.failure_code = result.failure_code
    attempt.save(update_fields=['provider_reference', 'status', 'failure_code', 'updated_at'])
    if result.status == 'succeeded':
        return mark_ai_usage_billing_intent_succeeded(
            current, attempt_token=attempt_token, provider=attempt.provider,
            provider_reference=result.provider_reference,
        )
    if result.status == 'failed':
        # S8E retains its existing sanitized vocabulary; S8F retains the precise code.
        return mark_ai_usage_billing_intent_failed(
            current, attempt_token=attempt_token, provider=attempt.provider,
            provider_reference=result.provider_reference, failure_code=result.failure_code,
        )
    logger.warning('AI usage billing result unresolved; retry remains blocked.')
    return current


def reconcile_ai_usage_billing_intent(
    intent: AppointmentAIUsageBillingIntent, *, attempt_token: uuid.UUID,
    provider: AIUsageBillingProvider | None = None,
) -> AppointmentAIUsageBillingIntent:
    """Read status only. Without a reference, require late correlated evidence, not retry."""
    adapter = provider if provider is not None else get_ai_usage_billing_provider()
    with transaction.atomic():
        current = _locked(intent)
        _require_attempt(current, attempt_token)
        if current.status != 'processing':
            raise AIUsageBillingIntentConflict('Only an unresolved claim can be reconciled.')
        try:
            attempt = current.provider_attempts.get(attempt_token=attempt_token)
        except AppointmentAIUsageBillingAttempt.DoesNotExist as exc:
            raise AIUsageBillingIntentConflict('The claim has no provider reservation.') from exc
        if attempt.provider != adapter.name or not attempt.provider_reference:
            raise AIUsageBillingIntentConflict('Reconciliation requires the same provider and reference.')
        reference = attempt.provider_reference
        external_reference = current.external_reference
    try:
        result = adapter.get_status(reference, external_reference=external_reference)
    except (TimeoutError, ConnectionError):
        logger.warning('AI usage billing status outcome unknown; reconciliation required.')
        result = AIUsageBillingResult('outcome_unknown', reference, 'timeout')
    return record_ai_usage_billing_result(current, attempt_token=attempt_token, result=result)
