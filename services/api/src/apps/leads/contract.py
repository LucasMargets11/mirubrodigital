"""Constantes y helpers puros del Contract V1 `lead.sync` (AGENT 02B).

Todo lo de este módulo es determinístico y sin I/O: lo usan la
autenticación HMAC, el serializer y el receiver service, y se testea con los
vectores congelados del contrato.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import uuid

SCHEMA_VERSION = 1
EVENT_TYPE = 'lead.sync'
CHANNEL_WHATSAPP = 'whatsapp'

SIGNATURE_VERSION = 'v1'
SIGNATURE_PREFIX = 'v1='
TIMESTAMP_TOLERANCE_SECONDS = 300
NONCE_TTL_SECONDS = 600

LEAD_SYNC_PATH_TEMPLATE = '/api/v1/integrations/agent/leads/{external_lead_id}/'

EVENT_ID_NAMESPACE = uuid.UUID('6256df71-42ce-43c8-b63d-00ea41f300f0')

AGENT_STATUSES = ('active', 'closed')
CLOSE_REASONS = ('idle', 'reception')
HANDOFF_REASON_CODES = (
    'lead_ready',
    'urgency',
    'patient_asked_human',
    'agent_handoff_required',
    'medication_question',
    'agent_error',
    'unsupported_message',
    'recovery_dropped',
)

# Estados de Business que aceptan ingesta (audit §20 R12).
ALLOWED_BUSINESS_STATUSES = frozenset({'onboarding', 'trialing', 'active', 'past_due'})


# ── HMAC ────────────────────────────────────────────────────────────────────

def body_sha256(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def canonical_string(*, method: str, path: str, timestamp: str, request_id: str, key_id: str, body_hash: str) -> str:
    """Siete líneas unidas con `\\n`, sin newline final."""
    return '\n'.join([SIGNATURE_VERSION, method, path, timestamp, request_id, key_id, body_hash])


def compute_signature(secret: str, canonical: str) -> str:
    digest = hmac.new(secret.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).hexdigest()
    return SIGNATURE_PREFIX + digest


# ── event_id ────────────────────────────────────────────────────────────────

def compute_event_id(agent_instance_id: str, external_lead_id, version: int) -> uuid.UUID:
    name = f'{agent_instance_id}:{str(external_lead_id).lower()}:{int(version)}'
    return uuid.uuid5(EVENT_ID_NAMESPACE, name)


# ── payload_hash ────────────────────────────────────────────────────────────

def format_utc(value: dt.datetime) -> str:
    """Formato estable: siempre UTC, microsegundos y sufijo `Z`."""
    return value.astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def _canonical_value(value):
    if isinstance(value, dt.datetime):
        return format_utc(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def sort_handoff_reasons(reasons: list[dict]) -> list[dict]:
    """El orden recibido no tiene semántica: se ordena por `code` (único)."""
    return sorted(reasons, key=lambda reason: reason['code'])


def canonical_snapshot(validated: dict) -> dict:
    """Representación canónica de los campos validados de schema v1.

    Recibe `validated_data` del serializer (que ya descartó campos
    desconocidos): nunca incluye headers ni `request_id`.
    """
    snapshot = _canonical_value(validated)
    handoff = snapshot.get('handoff')
    if isinstance(handoff, dict) and isinstance(handoff.get('reasons'), list):
        handoff['reasons'] = sort_handoff_reasons(handoff['reasons'])
    return snapshot


def compute_payload_hash(validated: dict) -> str:
    encoded = json.dumps(
        canonical_snapshot(validated), sort_keys=True, separators=(',', ':'), ensure_ascii=False,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()
