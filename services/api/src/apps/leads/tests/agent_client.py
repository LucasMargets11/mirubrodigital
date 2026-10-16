"""Helpers de tests del receiver `lead.sync` (AGENT 02B): payload v1 + firma HMAC."""
from __future__ import annotations

import copy
import json
import time
import uuid

from apps.leads.contract import LEAD_SYNC_PATH_TEMPLATE, body_sha256, canonical_string, compute_event_id, compute_signature

from .factories import SECRET

T0 = '2026-10-04T12:00:00.000000Z'
T1 = '2026-10-04T12:05:00.000000Z'
T2 = '2026-10-04T12:10:00.000000Z'
T3 = '2026-10-04T12:20:00.000000Z'

PII_SENTINEL = 'SUPER_SECRET_PATIENT_VALUE'


def lead_path(external_lead_id) -> str:
    return LEAD_SYNC_PATH_TEMPLATE.format(external_lead_id=str(external_lead_id))


def make_payload(*, agent_instance_id: str, business_id: int, phone_number_id: str,
                 external_lead_id=None, version: int = 1, handoff: dict | None = None, **overrides) -> dict:
    external_lead_id = str(external_lead_id or uuid.uuid4())
    payload = {
        'schema_version': 1,
        'event_id': None,
        'event_type': 'lead.sync',
        'occurred_at': T1,
        'business_id': business_id,
        'agent_instance_id': agent_instance_id,
        'phone_number_id': phone_number_id,
        'external_conversation_id': 'wac1_0123456789abcdef0123456789abcdef',
        'external_lead_id': external_lead_id,
        'previous_external_lead_id': None,
        'version': version,
        'channel': 'whatsapp',
        'phone_e164': '+5491112345678',
        'patient_name': 'Ana Pérez',
        'whatsapp_profile_name': 'Ana',
        'reason': 'Dolor de muela',
        'preferred_time': 'Mañana a la tarde',
        'urgency': False,
        'agent_status': 'active',
        'handoff': handoff if handoff is not None else {'requested': False, 'requested_at': None, 'reasons': []},
        'summary': 'Paciente consulta por dolor.',
        'opened_at': T0,
        'closed_at': None,
        'close_reason': None,
        'last_message_at': T1,
    }
    payload.update(overrides)
    if payload['event_id'] is None:
        payload['event_id'] = str(compute_event_id(
            payload['agent_instance_id'], payload['external_lead_id'], payload['version'],
        ))
    return payload


def handoff_requested(*codes: str, first_at: str = T1, last_at: str = T1) -> dict:
    return {
        'requested': True,
        'requested_at': first_at,
        'reasons': [{'code': code, 'first_at': first_at, 'last_at': last_at} for code in codes],
    }


def bump(payload: dict, version: int, **overrides) -> dict:
    """Misma identidad, otra versión (event_id recalculado)."""
    new = copy.deepcopy(payload)
    new.update(overrides)
    new['version'] = version
    new['event_id'] = str(compute_event_id(new['agent_instance_id'], new['external_lead_id'], version))
    return new


def sign_headers(*, path: str, body: bytes, key_id: str, secret: str = SECRET, timestamp: int | None = None,
                 request_id: str | None = None, method: str = 'PUT') -> dict:
    timestamp_str = str(int(time.time()) if timestamp is None else timestamp)
    request_id = request_id or str(uuid.uuid4())
    canonical = canonical_string(
        method=method, path=path, timestamp=timestamp_str, request_id=request_id, key_id=key_id,
        body_hash=body_sha256(body),
    )
    return {
        'HTTP_X_AGENT_KEY_ID': key_id,
        'HTTP_X_AGENT_TIMESTAMP': timestamp_str,
        'HTTP_X_REQUEST_ID': request_id,
        'HTTP_X_AGENT_SIGNATURE': compute_signature(secret, canonical),
    }


def encode(payload) -> bytes:
    return json.dumps(payload).encode('utf-8')


def signed_put(client, payload, *, key_id: str, secret: str = SECRET, path: str | None = None,
               body: bytes | None = None, headers: dict | None = None, **sign_kwargs):
    body = encode(payload) if body is None else body
    path = path or lead_path(payload['external_lead_id'])
    signed = sign_headers(path=path, body=body, key_id=key_id, secret=secret, **sign_kwargs)
    signed.update(headers or {})
    return client.generic('PUT', path, data=body, content_type='application/json', **signed)
