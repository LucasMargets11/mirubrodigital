"""Serializer de `lead.sync` schema_version 1 (Contract V1, AGENT 02B).

Reglas:
- Todas las claves del contrato son obligatorias (las nullable deben venir
  presentes, aunque sea con `null`).
- Tipos estrictos: no se coerciona `"1"` a 1, `"true"` a True ni números a
  texto. Timestamps ISO-8601 con zona explícita; se normalizan a UTC.
- Campos desconocidos: se IGNORAN (forward compatibility menor). DRF solo
  devuelve en `validated_data` los campos declarados, así que nunca llegan
  al hash ni a los modelos.
- Los errores se reportan por código (ver `errors.flatten_serializer_errors`),
  nunca con el valor recibido.
"""
from __future__ import annotations

import datetime as dt
import re
import uuid

from django.utils.dateparse import parse_datetime
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from .contract import (
    AGENT_STATUSES,
    CHANNEL_WHATSAPP,
    CLOSE_REASONS,
    EVENT_TYPE,
    HANDOFF_REASON_CODES,
    SCHEMA_VERSION,
    compute_event_id,
)
from .models import EXTERNAL_ID_REGEX, PHONE_NUMBER_ID_REGEX, LeadAgentMessage, LeadAgentState

CONTRACT_E164_REGEX = r'^\+[1-9][0-9]{6,14}$'
MAX_INT64 = 2 ** 63 - 1
MAX_SYNC_MESSAGES = 500


class StrictIntegerField(serializers.Field):
    default_error_messages = {
        'invalid': 'Debe ser un entero.',
        'min_value': 'Valor fuera de rango.',
        'max_value': 'Valor fuera de rango.',
    }

    def __init__(self, *, min_value: int = 1, max_value: int = MAX_INT64, **kwargs):
        self.min_value = min_value
        self.max_value = max_value
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail('invalid')
        if data < self.min_value:
            self.fail('min_value')
        if data > self.max_value:
            self.fail('max_value')
        return data

    def to_representation(self, value):
        return value


class StrictBooleanField(serializers.Field):
    default_error_messages = {'invalid': 'Debe ser booleano.'}

    def to_internal_value(self, data):
        if not isinstance(data, bool):
            self.fail('invalid')
        return data

    def to_representation(self, value):
        return value


class StrictCharField(serializers.Field):
    """Texto sin coerción ni trim; `max_length` en caracteres."""

    default_error_messages = {
        'invalid': 'Debe ser texto.',
        'blank': 'No puede estar vacío.',
        'max_length': 'Demasiado largo.',
        'pattern': 'Formato inválido.',
    }

    def __init__(self, *, max_length: int | None = None, allow_blank: bool = False, pattern: str | None = None, **kwargs):
        self.max_length = max_length
        self.allow_blank = allow_blank
        self.pattern = re.compile(pattern) if pattern else None
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail('invalid')
        if data == '' and not self.allow_blank:
            self.fail('blank')
        if self.max_length is not None and len(data) > self.max_length:
            self.fail('max_length')
        if self.pattern is not None and not self.pattern.fullmatch(data):
            self.fail('pattern')
        if '\x00' in data:
            self.fail('invalid')
        return data

    def to_representation(self, value):
        return value


class StrictChoiceField(StrictCharField):
    default_error_messages = {**StrictCharField.default_error_messages, 'invalid_choice': 'Valor no permitido.'}

    def __init__(self, choices, **kwargs):
        self.allowed = frozenset(choices)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if value not in self.allowed:
            self.fail('invalid_choice')
        return value


class StrictUUIDField(serializers.Field):
    default_error_messages = {'invalid': 'UUID inválido.'}

    def to_internal_value(self, data):
        if not isinstance(data, str) or len(data) != 36:
            self.fail('invalid')
        try:
            return uuid.UUID(data)
        except ValueError:
            self.fail('invalid')

    def to_representation(self, value):
        return str(value)


class AwareDateTimeField(serializers.Field):
    """ISO-8601 con offset explícito (p. ej. `Z`); devuelve datetime en UTC."""

    default_error_messages = {
        'invalid': 'Fecha inválida.',
        'naive': 'La fecha debe incluir zona horaria.',
    }

    def to_internal_value(self, data):
        if not isinstance(data, str) or len(data) > 40:
            self.fail('invalid')
        try:
            parsed = parse_datetime(data)
        except ValueError:
            parsed = None
        if parsed is None:
            self.fail('invalid')
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            self.fail('naive')
        return parsed.astimezone(dt.timezone.utc)

    def to_representation(self, value):
        return value.isoformat()


class HandoffReasonSerializer(serializers.Serializer):
    code = StrictChoiceField(HANDOFF_REASON_CODES)
    first_at = AwareDateTimeField()
    last_at = AwareDateTimeField()

    def validate(self, attrs):
        if attrs['first_at'] > attrs['last_at']:
            raise serializers.ValidationError({'last_at': ErrorDetail('Orden inválido.', code='before_first_at')})
        return attrs


class HandoffSerializer(serializers.Serializer):
    requested = StrictBooleanField()
    requested_at = AwareDateTimeField(allow_null=True)
    reasons = HandoffReasonSerializer(many=True, allow_empty=True)

    def validate(self, attrs):
        reasons = attrs['reasons']
        if not attrs['requested']:
            if reasons:
                raise _field_error('reasons', 'must_be_empty')
            if attrs['requested_at'] is not None:
                raise _field_error('requested_at', 'must_be_null')
            return attrs
        if not reasons:
            raise _field_error('reasons', 'required_when_requested')
        if attrs['requested_at'] is None:
            raise _field_error('requested_at', 'required_when_requested')
        codes = [reason['code'] for reason in reasons]
        if len(codes) != len(set(codes)):
            raise _field_error('reasons', 'duplicate_code')
        if attrs['requested_at'] != min(reason['first_at'] for reason in reasons):
            raise _field_error('requested_at', 'mismatch_first_at')
        return attrs


class LeadSyncMessageSerializer(serializers.Serializer):
    """Un mensaje de la ventana de historial (LEADS 05C, additive a v1)."""

    external_message_id = StrictCharField(max_length=64)
    role = StrictChoiceField(LeadAgentMessage.Role.values)
    sender = StrictChoiceField(LeadAgentMessage.Sender.values)
    text = StrictCharField(max_length=LeadAgentMessage.TEXT_MAX_LENGTH)
    sent_at = AwareDateTimeField()
    status = StrictChoiceField(LeadAgentMessage.Status.values, allow_null=True)


def _field_error(field: str, code: str) -> serializers.ValidationError:
    return serializers.ValidationError({field: [ErrorDetail('Valor incoherente.', code=code)]})


class LeadSyncSerializer(serializers.Serializer):
    schema_version = StrictIntegerField()
    event_id = StrictUUIDField()
    event_type = StrictCharField()
    occurred_at = AwareDateTimeField()

    business_id = StrictIntegerField()
    agent_instance_id = StrictCharField(pattern=EXTERNAL_ID_REGEX)
    phone_number_id = StrictCharField(pattern=PHONE_NUMBER_ID_REGEX)

    external_conversation_id = StrictCharField(max_length=64)
    external_lead_id = StrictUUIDField()
    previous_external_lead_id = StrictUUIDField(allow_null=True)
    version = StrictIntegerField()

    channel = StrictCharField()

    phone_e164 = StrictCharField(pattern=CONTRACT_E164_REGEX)
    patient_name = StrictCharField(max_length=LeadAgentState.PATIENT_NAME_MAX_LENGTH, allow_blank=True, allow_null=True)
    whatsapp_profile_name = StrictCharField(
        max_length=LeadAgentState.PATIENT_NAME_MAX_LENGTH, allow_blank=True, allow_null=True,
    )

    reason = StrictCharField(max_length=LeadAgentState.REASON_MAX_LENGTH, allow_blank=True, allow_null=True)
    preferred_time = StrictCharField(max_length=LeadAgentState.REASON_MAX_LENGTH, allow_blank=True, allow_null=True)
    urgency = StrictBooleanField()

    agent_status = StrictChoiceField(AGENT_STATUSES)

    handoff = HandoffSerializer()

    summary = StrictCharField(max_length=LeadAgentState.SUMMARY_MAX_LENGTH, allow_blank=True, allow_null=True)

    opened_at = AwareDateTimeField()
    closed_at = AwareDateTimeField(allow_null=True)
    close_reason = StrictChoiceField(CLOSE_REASONS, allow_null=True)
    last_message_at = AwareDateTimeField()
    # LEADS 05C: opcional (default []) — forward-compatible con agentes que
    # todavía no lo mandan; no participa de ningún check de inmutabilidad.
    messages = LeadSyncMessageSerializer(many=True, required=False, default=list)

    def validate_schema_version(self, value):
        if value != SCHEMA_VERSION:
            raise serializers.ValidationError('Versión no soportada.', code='unsupported')
        return value

    def validate_event_type(self, value):
        if value != EVENT_TYPE:
            raise serializers.ValidationError('Tipo de evento no soportado.', code='invalid_choice')
        return value

    def validate_channel(self, value):
        if value != CHANNEL_WHATSAPP:
            raise serializers.ValidationError('Canal no soportado.', code='invalid_choice')
        return value

    def validate(self, attrs):
        if len(attrs['messages']) > MAX_SYNC_MESSAGES:
            raise _field_error('messages', 'too_many')
        if attrs['agent_status'] == 'active':
            if attrs['closed_at'] is not None:
                raise _field_error('closed_at', 'must_be_null')
            if attrs['close_reason'] is not None:
                raise _field_error('close_reason', 'must_be_null')
        else:
            if attrs['closed_at'] is None:
                raise _field_error('closed_at', 'required_when_closed')
            if attrs['close_reason'] is None:
                raise _field_error('close_reason', 'required_when_closed')
        if attrs['opened_at'] > attrs['last_message_at']:
            raise _field_error('last_message_at', 'before_opened_at')
        expected = compute_event_id(attrs['agent_instance_id'], attrs['external_lead_id'], attrs['version'])
        if attrs['event_id'] != expected:
            raise _field_error('event_id', 'mismatch')
        return attrs
