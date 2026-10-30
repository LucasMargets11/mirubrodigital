import hashlib
import logging
import time

from django.conf import settings
from django.db import DatabaseError
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_naive
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.appointments.checks import ai_usage_database_ready
from apps.appointments.services.ai_usage import AIUsageHardCapReached, AIUsageUnavailable
from apps.appointments.services.ai_usage_authorization import authorize_ai_interaction
from apps.billing.services.appointments_checkout import ManualContractRequired
from apps.leads import errors
from apps.leads.authentication import AgentHmacAuthentication
from apps.leads.models import EXTERNAL_CONVERSATION_ID_REGEX
from apps.leads.throttles import AgentLeadSyncThrottle
from apps.leads.views import AgentIntegrationView

logger = logging.getLogger(__name__)


class AIUsageHmacAuthentication(AgentHmacAuthentication):
    nonce_fail_closed = True


class AIUsageThrottle(AgentLeadSyncThrottle):
    fail_closed = True


class AIUsageAuthorizationSerializer(serializers.Serializer):
    external_conversation_id = serializers.RegexField(EXTERNAL_CONVERSATION_ID_REGEX, max_length=64)
    interaction_id = serializers.UUIDField()
    occurred_at = serializers.DateTimeField()

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) != set(self.fields):
            raise serializers.ValidationError('Exactly the canonical authorization fields are required.')
        raw_at = data.get('occurred_at')
        # DRF otherwise silently assigns the server timezone to a naive timestamp.
        try:
            at = parse_datetime(raw_at) if isinstance(raw_at, str) else None
        except ValueError:
            at = None
        if at is None or is_naive(at):
            raise serializers.ValidationError({'occurred_at': 'An explicit timezone is required.'})
        return super().to_internal_value(data)


class AgentAIUsageAuthorizeView(AgentIntegrationView):
    http_method_names = ['post']
    authentication_classes = [AIUsageHmacAuthentication]
    throttle_classes = [AIUsageThrottle]

    def handle_exception(self, exc):
        if isinstance(exc, TimeoutError):
            self._outcome = 'authorization_timeout'
            exc = errors.unavailable()
        elif isinstance(exc, DatabaseError):
            self._outcome = 'backend_error'
            exc = errors.unavailable()
        response = super().handle_exception(exc)
        self._blocked_reason = response.data['error']['code']
        return response

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store'
        outcome = getattr(self, '_outcome', None)
        if outcome is None:
            outcome = (
                'authorization_auth_failed' if response.status_code in (401, 403)
                else 'backend_error' if response.status_code >= 500
                else 'authorization_blocked'
            )
        reason = getattr(self, '_blocked_reason', None)
        fields = {
            'event': 'ai_usage_authorization',
            'metric': outcome,
            'count': 1,
            'reason': reason,
            'status_code': response.status_code,
            'duration_ms': round((time.monotonic() - self._started) * 1000, 3),
            'request_id': self._request_id(),
            'interaction_id': getattr(self, '_interaction_id', None),
            'business_id': getattr(self, '_business_id', None),
            'conversation_hash': getattr(self, '_conversation_hash', None),
            'session_id': getattr(self, '_session_id', None),
            'session_created': getattr(self, '_created', None),
        }
        allowed = outcome in ('authorization_allowed', 'authorization_reused')
        logger.log(
            logging.INFO if allowed else logging.WARNING,
            'ai_usage_authorize metric=%s business=%s allowed=%s reason=%s request_id=%s interaction_id=%s '
            'session=%s session_created=%s conversation_hash=%s duration_ms=%s',
            outcome, fields['business_id'], str(allowed).lower(), reason,
            fields['request_id'], fields['interaction_id'], fields['session_id'],
            fields['session_created'], fields['conversation_hash'], fields['duration_ms'],
            extra=fields,
        )
        return response

    def post(self, request):
        serializer = AIUsageAuthorizationSerializer(data=request.data)
        if not serializer.is_valid():
            raise errors.invalid_request('Invalid AI authorization request.')
        data = serializer.validated_data
        self._interaction_id = str(data['interaction_id'])
        self._conversation_hash = hashlib.sha256(data['external_conversation_id'].encode()).hexdigest()[:16]
        if not getattr(settings, 'AI_USAGE_METERING_ENABLED', False):
            self._blocked_reason = 'metering_disabled'
            return Response({'allowed': False, 'reason': 'metering_disabled'})
        try:
            business, session, created, usage = authorize_ai_interaction(
                agent_instance=request.user.agent_instance,
                conversation_id=data['external_conversation_id'],
                interaction_id=data['interaction_id'], occurred_at=data['occurred_at'],
            )
        except AIUsageHardCapReached:
            reason = 'hard_cap_reached'
        except ManualContractRequired:
            reason = 'manual_contract_required'
        except AIUsageUnavailable as exc:
            reason = exc.reason
        else:
            self._outcome = 'authorization_allowed' if created else 'authorization_reused'
            self._business_id, self._session_id, self._created = business.pk, str(session.pk), created
            return Response({'allowed': True, 'session_id': str(session.pk), 'created': created, **usage})
        self._blocked_reason = reason
        return Response({'allowed': False, 'reason': reason})


class AgentAIUsageHealthView(AgentIntegrationView):
    http_method_names = ['get']
    authentication_classes = [AIUsageHmacAuthentication]
    throttle_classes = [AIUsageThrottle]

    def initial(self, request, *args, **kwargs):
        self._started = time.monotonic()
        # Diagnose integration-off too, but never skip HMAC, permissions or throttling.
        APIView.initial(self, request, *args, **kwargs)

    def get(self, request):
        try:
            ready = ai_usage_database_ready()
        except DatabaseError:
            ready = False
        metering = getattr(settings, 'AI_USAGE_METERING_ENABLED', False)
        integration = getattr(settings, 'AGENT_INTEGRATION_ENABLED', False)
        healthy = ready and (not metering or integration)
        if not healthy:
            logger.warning('ai_usage_health_unavailable', extra={'event': 'ai_usage_health', 'request_id': self._request_id()})
        return Response({
            'status': 'ok' if healthy else 'unavailable',
            'metering_enabled': metering,
            'agent_integration_enabled': integration,
            'database': 'ok' if ready else 'unavailable',
        }, status=200 if healthy else 503, headers={'Cache-Control': 'no-store'})
