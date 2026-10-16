"""API humana de Leads (LEADS 04A) — `/api/v1/leads/`.

Distinta del endpoint máquina `/api/v1/integrations/agent/leads/...` (HMAC):
acá autentica la sesión del usuario y el tenant sale SIEMPRE del contexto
autenticado (`request.business`), nunca de un `business_id` del cliente. Un
Lead o nota de otro Business responde 404 (indistinguible de inexistente).

Acceso (LEADS 04A.1): entitlement `appointments.leads` del plan (Turnos Base)
Y RBAC del servicio activo — lectura `view_leads`; mutaciones `manage_leads`.
`manage_agent_channels` no da nada sobre Leads humanos.
"""
from __future__ import annotations

import re
import uuid

from django.db import transaction
from django.db.models import BooleanField, Case, F, OuterRef, Prefetch, Q, Subquery, Value, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics, status as http_status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.access import resolve_business_context, resolve_request_membership
from apps.accounts.permissions import HasBusinessMembership, HasEntitlement, HasPermission
from apps.business.entitlements import APPOINTMENTS_LEADS_ENTITLEMENT

from .crm_serializers import (
    LeadDetailSerializer, LeadListSerializer, LeadMessageSerializer, LeadNoteSerializer, LeadSendMessageSerializer,
    LeadUpdateSerializer, _user_ref,
)
from .models import ConversationControl, Lead, LeadActivity, LeadAgentMessage, LeadNote, TakeoverCommand
from .services.activity import record_attention_acknowledged
from .services.assignees import assignable_memberships
from .services.human_messages import authored_by_map, send_staff_message
from .services.takeover import TakeoverConflict, TakeoverUnavailable, request_conversation_command

UNASSIGNED = 'unassigned'
UNLINKED = 'unlinked'
ORDERING_PRIORITY = 'priority'
_BOOLEAN_VALUES = {'true': True, 'false': False}
_NON_DIGITS = re.compile(r'\D+')


class LeadPagination(LimitOffsetPagination):
    default_limit = 25
    max_limit = 100
    limit_query_param = 'limit'
    offset_query_param = 'offset'


class _LeadPermissionsMixin:
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
    required_entitlement = APPOINTMENTS_LEADS_ENTITLEMENT
    permission_map = {
        'GET': 'view_leads',
        'POST': 'manage_leads',
        'PATCH': 'manage_leads',
        'DELETE': 'manage_leads',
    }

    def get_lead(self, *, for_update: bool = False) -> Lead:
        business = getattr(self.request, 'business')
        queryset = Lead.objects.select_for_update(of=('self',)) if for_update else Lead.objects
        return get_object_or_404(queryset, pk=self.kwargs['lead_id'], business=business)


def _active_service(request) -> str:
    """Servicio con el que se evalúa `view_leads` del asignado (PATCH y `/assignees/`)."""
    return resolve_business_context(request, resolve_request_membership(request))['service']


def _parse_bool(params, name: str):
    raw = params.get(name)
    if raw is None or raw == '':
        return None
    value = _BOOLEAN_VALUES.get(raw.lower())
    if value is None:
        raise ValidationError({name: 'Usar true o false.'})
    return value


def _parse_choice(params, name: str, choices):
    raw = params.get(name)
    if raw is None or raw == '':
        return None
    if raw not in choices:
        raise ValidationError({name: 'Valor inválido.'})
    return raw


class LeadListView(_LeadPermissionsMixin, generics.ListAPIView):
    """GET /api/v1/leads/ — bandeja paginada con filtros, búsqueda `q` y orden controlado.

    Orden por defecto (`priority`), por grupos: 1) abiertos con atención
    pendiente (pidió atención y nadie la reconoció después), 2) otros abiertos,
    3) cerrados siempre al final. En los abiertos, urgentes primero; dentro de
    cada grupo, último mensaje más reciente → más nuevo. `needs_attention_at`
    queda como evidencia histórica: un cerrado o ya reconocido no compite por
    el primer lugar.
    """

    serializer_class = LeadListSerializer
    pagination_class = LeadPagination
    ORDERINGS = {
        'created_at': ('created_at', 'id'),
        '-created_at': ('-created_at', '-id'),
        'last_message_at': (F('agent_state__last_message_at').asc(nulls_last=True), 'id'),
        '-last_message_at': (F('agent_state__last_message_at').desc(nulls_last=True), '-id'),
    }

    def get_queryset(self):
        business = getattr(self.request, 'business')
        params = self.request.query_params
        queryset = Lead.objects.filter(business=business).select_related(
            'agent_state', 'assigned_to', 'customer',
        ).annotate(
            # MIRUBRO TAKEOVER 05A: badge `conversation_state` sin query por fila.
            conversation_control_state=Subquery(
                ConversationControl.objects.filter(
                    business_id=OuterRef('business_id'),
                    external_conversation_id=OuterRef('agent_state__external_conversation_id'),
                ).values('state')[:1]
            ),
        )

        status = _parse_choice(params, 'status', Lead.Status.values)
        if status:
            queryset = queryset.filter(status=status)
        source = _parse_choice(params, 'source', Lead.Source.values)
        if source:
            queryset = queryset.filter(source=source)
        outcome = _parse_choice(params, 'outcome', Lead.Outcome.values)
        if outcome:
            queryset = queryset.filter(outcome=outcome)

        urgency = _parse_bool(params, 'urgency')
        if urgency is not None:
            queryset = queryset.filter(agent_state__urgency=urgency)
        handoff = _parse_bool(params, 'handoff')
        if handoff is not None:
            queryset = queryset.filter(agent_state__handoff_requested=handoff)
        needs_attention = _parse_bool(params, 'needs_attention')
        if needs_attention is not None:
            # Atención pendiente (LEADS 04B.1), no la evidencia histórica `needs_attention_at`.
            pending = Lead.attention_pending_q()
            queryset = queryset.filter(pending if needs_attention else ~pending)

        assigned_to = params.get('assigned_to')
        if assigned_to:
            if assigned_to == UNASSIGNED:
                queryset = queryset.filter(assigned_to__isnull=True)
            elif assigned_to.isdigit():
                queryset = queryset.filter(assigned_to_id=int(assigned_to))
            else:
                raise ValidationError({'assigned_to': f'Usar un id de usuario o "{UNASSIGNED}".'})

        customer = params.get('customer')
        if customer:
            if customer == UNLINKED:
                queryset = queryset.filter(customer__isnull=True)
            else:
                try:
                    customer_id = uuid.UUID(customer)
                except ValueError:
                    raise ValidationError({'customer': f'Usar un id de cliente o "{UNLINKED}".'})
                queryset = queryset.filter(customer_id=customer_id)

        q = (params.get('q') or '').strip()
        if q:
            match = (
                Q(agent_state__patient_name__icontains=q)
                | Q(agent_state__whatsapp_profile_name__icontains=q)
                | Q(agent_state__phone_e164__icontains=q)
                | Q(agent_state__reason__icontains=q)
                | Q(agent_state__summary__icontains=q)
                | Q(customer__name__icontains=q)
                | Q(customer__phone__icontains=q)
            )
            digits = _NON_DIGITS.sub('', q)
            if len(digits) >= 3:
                # "11 1234-5678" encuentra "+5491112345678".
                match |= Q(agent_state__phone_e164__contains=digits)
            queryset = queryset.filter(match)

        ordering = params.get('ordering') or ORDERING_PRIORITY
        if ordering == ORDERING_PRIORITY:
            is_open = ~Q(status=Lead.Status.CLOSED)
            return queryset.annotate(
                attention_open=Case(
                    When(Lead.attention_pending_q(), then=Value(True)),
                    default=Value(False), output_field=BooleanField(),
                ),
                lead_open=Case(When(is_open, then=Value(True)), default=Value(False), output_field=BooleanField()),
                # La urgencia solo ordena abiertos: un cerrado urgente no sube dentro de los cerrados.
                urgent_open=Case(
                    When(is_open & Q(agent_state__urgency=True), then=Value(True)),
                    default=Value(False), output_field=BooleanField(),
                ),
            ).order_by(
                '-attention_open',
                '-lead_open',
                '-urgent_open',
                F('agent_state__last_message_at').desc(nulls_last=True),
                '-created_at', '-id',
            )
        if ordering not in self.ORDERINGS:
            allowed = ', '.join([ORDERING_PRIORITY, *self.ORDERINGS])
            raise ValidationError({'ordering': f'Valores permitidos: {allowed}.'})
        return queryset.order_by(*self.ORDERINGS[ordering])


class LeadAssigneesView(_LeadPermissionsMixin, generics.GenericAPIView):
    """GET /api/v1/leads/assignees/ — personas asignables a Leads del Business actual (LEADS 05B.1).

    Misma regla que acepta el PATCH de `assigned_to` (services.assignees).
    Solo `id` + `display_name`: sin email, teléfono ni permisos. Lista corta
    (miembros del Business), sin paginar, ordenada por nombre.
    """

    http_method_names = ['get', 'head', 'options']

    def get(self, request, *args, **kwargs):
        business = getattr(request, 'business')
        rows = [_user_ref(m.user) for m in assignable_memberships(business.pk, _active_service(request))]
        rows.sort(key=lambda row: (row['display_name'].casefold(), row['id']))
        return Response(rows)


class LeadDetailView(_LeadPermissionsMixin, generics.GenericAPIView):
    """GET/PATCH /api/v1/leads/{id}/ — PATCH solo campos CRM, bajo lock de fila.

    El detalle incluye `activity` (LEADS 04B.4): historial read-only y sin
    endpoint de escritura; los eventos solo los genera el backend.
    """

    serializer_class = LeadDetailSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def _detail(self, lead_id) -> dict:
        business = getattr(self.request, 'business')
        lead = get_object_or_404(
            Lead.objects.select_related(
                'agent_state__agent_instance', 'agent_state__channel', 'assigned_to', 'customer', 'appointment',
                'closed_by', 'acknowledged_by',
            ).prefetch_related(
                'notes__author',
                Prefetch('activities', queryset=LeadActivity.objects.select_related('actor').order_by('-created_at', 'position')),
            ),
            pk=lead_id, business=business,
        )
        return LeadDetailSerializer(lead, context=self.get_serializer_context()).data

    def get(self, request, *args, **kwargs):
        return Response(self._detail(self.kwargs['lead_id']))

    def patch(self, request, *args, **kwargs):
        service = _active_service(request)
        with transaction.atomic():
            lead = self.get_lead(for_update=True)
            serializer = LeadUpdateSerializer(
                lead, data=request.data, partial=True,
                context={**self.get_serializer_context(), 'service': service},
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(self._detail(lead.pk))


class LeadAcknowledgeAttentionView(LeadDetailView):
    """POST /api/v1/leads/{id}/acknowledge-attention/ — un humano reconoce el pedido de atención (LEADS 04B.1).

    Idempotente: si el último pedido ya está reconocido responde 200 sin
    cambios (conserva el primer `acknowledged_at`/`acknowledged_by`). Nunca
    toca `needs_attention_at` (evidencia del agente). El body se ignora.
    """

    http_method_names = ['post', 'options']

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            lead = self.get_lead(for_update=True)
            if lead.needs_attention_at is None:
                raise ValidationError({'non_field_errors': ['El lead no tiene un pedido de atención.']})
            if not lead.attention_acknowledged:
                if lead.status == Lead.Status.CLOSED:
                    raise ValidationError({'non_field_errors': ['El lead está cerrado.']})
                lead.acknowledged_at = timezone.now()
                lead.acknowledged_by = request.user
                lead.save(update_fields=['acknowledged_at', 'acknowledged_by', 'updated_at'])
                # LEADS 04B.4: solo el reconocimiento efectivo (el no-op idempotente no).
                record_attention_acknowledged(lead, actor=request.user)
        return Response(self._detail(lead.pk))


class _ConversationCommandView(_LeadPermissionsMixin, generics.GenericAPIView):
    """POST takeover/release (MIRUBRO TAKEOVER 05A) — `manage_leads`.

    Encola el comando (outbox) y responde sin esperar al agente: 202 si creó
    un comando nuevo (`*_pending`), 200 si el pedido ya estaba hecho o en
    curso (idempotente, sin comando nuevo). Nunca dice `taken` antes del ACK.
    Body ignorado. 400 sin conversación del agente; 409 si hay un comando
    opuesto en vuelo; 503 con la integración apagada.
    """

    http_method_names = ['post', 'options']
    command_action: str = ''

    def post(self, request, *args, **kwargs):
        business = getattr(request, 'business')
        lead = get_object_or_404(Lead.objects.select_related('agent_state'), pk=self.kwargs['lead_id'], business=business)
        try:
            result = request_conversation_command(lead, self.command_action, user=request.user)
        except TakeoverUnavailable as exc:
            if exc.code == 'takeover_disabled':
                return Response(
                    {'ok': False, 'code': exc.code, 'detail': 'El control de conversaciones no está habilitado.'},
                    status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            return Response(
                {'ok': False, 'code': exc.code, 'detail': 'El lead no tiene una conversación del agente.'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        except TakeoverConflict:
            return Response(
                {'ok': False, 'code': 'command_in_progress',
                 'detail': 'Hay otra acción en curso para esta conversación. Esperá a que termine.'},
                status=http_status.HTTP_409_CONFLICT,
            )
        return Response(
            {'ok': True, 'state': result.state, 'command_version': result.command_version},
            status=http_status.HTTP_202_ACCEPTED if result.created else http_status.HTTP_200_OK,
        )


class LeadTakeoverView(_ConversationCommandView):
    """POST /api/v1/leads/{id}/takeover/ — tomar la conversación (pausa el bot)."""

    command_action = TakeoverCommand.Action.TAKEOVER


class LeadReleaseView(_ConversationCommandView):
    """POST /api/v1/leads/{id}/release/ — devolver la conversación (reanuda el bot)."""

    command_action = TakeoverCommand.Action.RELEASE


class LeadMessagesView(_LeadPermissionsMixin, generics.ListCreateAPIView):
    """GET/POST /api/v1/leads/{id}/messages/ (LEADS 05C + MIRUBRO HUMAN MESSAGES).

    GET: historial real de la conversación, orden cronológico ascendente,
    paginado (`limit`/`offset`, igual que `/leads/`). `since` (ISO-8601 con
    zona) filtra a mensajes posteriores, para que el panel actualice sin
    volver a pedir todo el historial. Decorado con `authored_by` para los
    mensajes `sender=staff` ya sincronizados (join local, ver
    `services.human_messages.authored_by_map`).

    POST: recepción escribe un mensaje nuevo hacia el paciente. Encola un
    outbox local (`LeadStaffMessage`, mismo patrón que `TakeoverCommand`) y
    responde de inmediato SIN esperar al agente: nunca dice "enviado", solo
    que se aceptó para envío. La entrega real (queued/duplicate o un error
    terminal del contrato) es asíncrona (Celery); el estado real de WhatsApp
    (sent/delivered/read/failed) llega después, solo, vía `lead.sync`
    (reaparece acá como `LeadAgentMessage` con `authored_by`).
    """

    serializer_class = LeadMessageSerializer
    pagination_class = LeadPagination

    def get_queryset(self):
        lead = self.get_lead()
        queryset = LeadAgentMessage.objects.filter(lead=lead).order_by('sent_at', 'id')
        since = self.request.query_params.get('since')
        if since:
            parsed = parse_datetime(since)
            if parsed is None or parsed.tzinfo is None:
                raise ValidationError({'since': 'Usar ISO-8601 con zona horaria.'})
            queryset = queryset.filter(sent_at__gt=parsed)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        objects = page if page is not None else list(queryset)
        external_ids = [m.external_message_id for m in objects if m.sender == LeadAgentMessage.Sender.STAFF]
        context = {**self.get_serializer_context(), 'authored_by_map': authored_by_map(self.get_lead(), external_ids)}
        serializer = self.get_serializer(objects, many=True, context=context)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    def post(self, request, *args, **kwargs):
        lead = self.get_lead()
        serializer = LeadSendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            message = send_staff_message(lead, serializer.validated_data['text'], user=request.user)
        except TakeoverUnavailable as exc:
            if exc.code == 'takeover_disabled':
                return Response(
                    {'ok': False, 'code': exc.code, 'detail': 'El envío de mensajes no está habilitado.'},
                    status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            return Response(
                {'ok': False, 'code': exc.code, 'detail': 'El lead no tiene una conversación del agente.'},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {'ok': True, 'status': 'queued_locally', 'id': str(message.pk)},
            status=http_status.HTTP_202_ACCEPTED,
        )


class _LeadNotesMixin(_LeadPermissionsMixin):
    serializer_class = LeadNoteSerializer

    def get_queryset(self):
        lead = self.get_lead()
        return (
            LeadNote.objects.filter(business=lead.business_id, lead=lead)
            .select_related('author')
            .order_by('-created_at', '-id')
        )


class LeadNotesView(_LeadNotesMixin, generics.ListCreateAPIView):
    """GET/POST /api/v1/leads/{id}/notes/ — más recientes primero, paginado."""

    pagination_class = LeadPagination

    def perform_create(self, serializer):
        lead = self.get_lead()
        serializer.save(business_id=lead.business_id, lead=lead, author=self.request.user)


class LeadNoteDetailView(_LeadNotesMixin, generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/v1/leads/{id}/notes/{note_id}/ (sin PUT: solo `body` es editable)."""

    lookup_url_kwarg = 'note_id'
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']
