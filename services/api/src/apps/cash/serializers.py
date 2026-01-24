from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from apps.sales.models import Sale
from .models import CashMovement, CashRegister, CashSession, Payment
from .services import collect_pending_session_sales, compute_session_totals, get_active_session


class UserSummarySerializer(serializers.Serializer):
  id = serializers.CharField(source='pk', read_only=True)
  name = serializers.SerializerMethodField()
  email = serializers.EmailField(read_only=True)

  def get_name(self, obj):  # pragma: no cover - formatting helper
    full_name = getattr(obj, 'get_full_name', None)
    if callable(full_name):
      value = full_name()
      if value:
        return value
    first_name = getattr(obj, 'first_name', '')
    last_name = getattr(obj, 'last_name', '')
    if first_name or last_name:
      return f"{first_name} {last_name}".strip()
    return getattr(obj, 'email', None) or getattr(obj, 'username', '') or 'Usuario'


class CashRegisterSerializer(serializers.ModelSerializer):
  class Meta:
    model = CashRegister
    fields = ['id', 'name', 'is_active', 'created_at', 'updated_at']
    read_only_fields = fields


class CashSessionSerializer(serializers.ModelSerializer):
  register = CashRegisterSerializer(read_only=True)
  opened_by = UserSummarySerializer(read_only=True)
  closed_by = UserSummarySerializer(read_only=True)
  totals = serializers.SerializerMethodField()

  class Meta:
    model = CashSession
    fields = [
      'id',
      'status',
      'register',
      'opening_cash_amount',
      'closing_cash_counted',
      'expected_cash_total',
      'difference_amount',
      'closing_note',
      'opened_by',
      'opened_by_name',
      'closed_by',
      'opened_at',
      'closed_at',
      'totals',
    ]
    read_only_fields = fields

  def get_totals(self, obj: CashSession) -> Dict[str, Any]:
    return compute_session_totals(obj)


class CashSessionOpenSerializer(serializers.Serializer):
  register_id = serializers.UUIDField(required=False, allow_null=True)
  opening_cash_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal('0'))
  opened_by_name = serializers.CharField(required=False, allow_blank=True, max_length=120)

  def validate_register_id(self, value: Optional[UUID]):
    if value is None:
      return value
    business = self.context['business']
    try:
      register = CashRegister.objects.get(pk=value, business=business, is_active=True)
    except CashRegister.DoesNotExist as exc:
      raise serializers.ValidationError('No encontramos la caja seleccionada en este negocio.') from exc
    self.context['register'] = register
    return value

  def validate(self, attrs: dict) -> dict:
    business = self.context['business']
    register = self.context.get('register')
    queryset = CashSession.objects.filter(business=business, status=CashSession.Status.OPEN)
    if register is None:
      if queryset.filter(register__isnull=True).exists():
        raise serializers.ValidationError('Ya tenés una sesión abierta sin caja asignada.')
    else:
      if queryset.filter(register=register).exists():
        raise serializers.ValidationError('Esta caja ya tiene una sesión abierta.')
    return attrs

  def create(self, validated_data):
    business = self.context['business']
    user = self.context.get('user')
    register = self.context.get('register')
    opening_amount = validated_data.get('opening_cash_amount') or Decimal('0')
    opened_by_name = (validated_data.get('opened_by_name') or '').strip()
    session = CashSession.objects.create(
      business=business,
      register=register,
      opened_by=user if getattr(user, 'is_authenticated', False) else None,
      opening_cash_amount=opening_amount,
      opened_by_name=opened_by_name,
    )
    return session

  def to_representation(self, instance):
    return CashSessionSerializer(instance, context=self.context).data


class CashPaymentSerializer(serializers.ModelSerializer):
  sale_number = serializers.IntegerField(source='sale.number', read_only=True)
  sale_total = serializers.DecimalField(source='sale.total', max_digits=12, decimal_places=2, read_only=True)

  class Meta:
    model = Payment
    fields = [
      'id',
      'sale_id',
      'sale_number',
      'sale_total',
      'session_id',
      'method',
      'amount',
      'reference',
      'created_at',
    ]
    read_only_fields = ['id', 'sale_number', 'sale_total', 'created_at']


class CashPaymentCreateSerializer(serializers.Serializer):
  sale_id = serializers.UUIDField()
  session_id = serializers.UUIDField(required=False, allow_null=True)
  method = serializers.ChoiceField(choices=Payment.Method.choices, default=Payment.Method.CASH)
  amount = serializers.DecimalField(max_digits=12, decimal_places=2)
  reference = serializers.CharField(required=False, allow_blank=True)

  def validate_amount(self, value: Decimal) -> Decimal:
    if value <= 0:
      raise serializers.ValidationError('El monto debe ser mayor a cero.')
    return value

  def _resolve_session(self, session_id: Optional[UUID]) -> CashSession:
    business = self.context['business']
    if session_id:
      try:
        session = CashSession.objects.get(pk=session_id, business=business)
      except CashSession.DoesNotExist as exc:
        raise serializers.ValidationError({'session_id': 'Sesión no encontrada.'}) from exc
    else:
      session = get_active_session(business)
      if session is None:
        raise serializers.ValidationError('No tenés una sesión abierta. Abrí la caja para registrar pagos.')
    if session.status != CashSession.Status.OPEN:
      raise serializers.ValidationError('Esta sesión ya está cerrada.')
    return session

  def validate(self, attrs: dict) -> dict:
    business = self.context['business']
    try:
      sale = Sale.objects.get(pk=attrs['sale_id'], business=business)
    except Sale.DoesNotExist as exc:
      raise serializers.ValidationError({'sale_id': 'La venta no existe en este negocio.'}) from exc
    if sale.status == Sale.Status.CANCELLED:
      raise serializers.ValidationError('No podés registrar pagos en una venta cancelada.')

    session = self._resolve_session(attrs.get('session_id'))
    if sale.business_id != session.business_id:
      raise serializers.ValidationError('La venta y la sesión pertenecen a negocios distintos.')

    paid_total = sale.payments.aggregate(total=Sum('amount')).get('total') or Decimal('0')
    pending_amount = (sale.total or Decimal('0')) - paid_total
    amount = attrs['amount']
    if pending_amount <= 0:
      raise serializers.ValidationError('Esta venta ya está saldada.')
    if amount > pending_amount:
      raise serializers.ValidationError({'amount': f'El pago supera el saldo pendiente (${pending_amount}).'})

    attrs['sale'] = sale
    attrs['session'] = session
    attrs['pending_amount'] = pending_amount
    return attrs

  def create(self, validated_data):
    sale: Sale = validated_data['sale']
    session: CashSession = validated_data['session']
    user = self.context.get('user')
    payment = Payment.objects.create(
      business=sale.business,
      sale=sale,
      session=session,
      method=validated_data.get('method', Payment.Method.CASH),
      amount=validated_data['amount'],
      reference=validated_data.get('reference', ''),
      created_by=user if getattr(user, 'is_authenticated', False) else None,
    )
    return payment

  def to_representation(self, instance):
    return CashPaymentSerializer(instance, context=self.context).data


class CashMovementSerializer(serializers.ModelSerializer):
  session = CashSessionSerializer(read_only=True)
  created_by = UserSummarySerializer(read_only=True)

  class Meta:
    model = CashMovement
    fields = [
      'id',
      'session',
      'movement_type',
      'category',
      'method',
      'amount',
      'note',
      'created_by',
      'created_at',
    ]
    read_only_fields = ['id', 'session', 'created_by', 'created_at']


class CashMovementCreateSerializer(serializers.Serializer):
  session_id = serializers.UUIDField(required=False, allow_null=True)
  movement_type = serializers.ChoiceField(choices=CashMovement.MovementType.choices)
  category = serializers.ChoiceField(choices=CashMovement.Category.choices, default=CashMovement.Category.OTHER)
  method = serializers.ChoiceField(choices=Payment.Method.choices, default=Payment.Method.CASH)
  amount = serializers.DecimalField(max_digits=12, decimal_places=2)
  note = serializers.CharField(required=False, allow_blank=True)

  def validate_amount(self, value: Decimal) -> Decimal:
    if value <= 0:
      raise serializers.ValidationError('El monto debe ser mayor a cero.')
    return value

  def validate(self, attrs: dict) -> dict:
    session = self._resolve_session(attrs.get('session_id'))
    attrs['session'] = session
    return attrs

  def _resolve_session(self, session_id: Optional[UUID]) -> CashSession:
    business = self.context['business']
    if session_id:
      try:
        session = CashSession.objects.get(pk=session_id, business=business)
      except CashSession.DoesNotExist as exc:
        raise serializers.ValidationError({'session_id': 'Sesión no encontrada.'}) from exc
    else:
      session = get_active_session(business)
      if session is None:
        raise serializers.ValidationError('Abrí una sesión de caja para registrar movimientos.')
    if session.status != CashSession.Status.OPEN:
      raise serializers.ValidationError('Esta sesión ya está cerrada.')
    return session

  def create(self, validated_data):
    session: CashSession = validated_data['session']
    user = self.context.get('user')
    movement = CashMovement.objects.create(
      business=session.business,
      session=session,
      movement_type=validated_data['movement_type'],
      category=validated_data.get('category', CashMovement.Category.OTHER),
      method=validated_data.get('method', Payment.Method.CASH),
      amount=validated_data['amount'],
      note=validated_data.get('note', ''),
      created_by=user if getattr(user, 'is_authenticated', False) else None,
    )
    return movement

  def to_representation(self, instance):
    return CashMovementSerializer(instance, context=self.context).data


class CashSessionCloseSerializer(serializers.Serializer):
  closing_cash_counted = serializers.DecimalField(max_digits=12, decimal_places=2)
  note = serializers.CharField(required=False, allow_blank=True)
  collect_pending_sales = serializers.BooleanField(required=False, default=False)

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.collection_summary: dict[str, Any] | None = None

  def validate_closing_cash_counted(self, value: Decimal) -> Decimal:
    if value < 0:
      raise serializers.ValidationError('El monto contado no puede ser negativo.')
    return value

  def save(self, **kwargs):
    session: CashSession = self.context['session']
    if session.status == CashSession.Status.CLOSED:
      raise serializers.ValidationError('Esta sesión ya está cerrada.')
    user = self.context.get('user')
    closing_amount = self.validated_data['closing_cash_counted']
    collect_pending = self.validated_data.get('collect_pending_sales', False)
    self.collection_summary = None

    with transaction.atomic():
      if collect_pending:
        self.collection_summary = collect_pending_session_sales(session, user=user)
      totals = compute_session_totals(session)
      expected_cash = totals['cash_expected_total']
      difference = closing_amount - expected_cash
      session.closing_cash_counted = closing_amount
      session.expected_cash_total = expected_cash
      session.difference_amount = difference
      session.closing_note = (self.validated_data.get('note') or '').strip()
      session.status = CashSession.Status.CLOSED
      session.closed_at = timezone.now()
      update_fields = [
        'closing_cash_counted',
        'expected_cash_total',
        'difference_amount',
        'closing_note',
        'status',
        'closed_at',
        'updated_at',
      ]
      if getattr(user, 'is_authenticated', False):
        session.closed_by = user
        update_fields.append('closed_by')
      session.save(update_fields=update_fields)

    self.instance = session
    return session

  def to_representation(self, instance):
    session_data = CashSessionSerializer(instance, context=self.context).data
    summary = None
    if self.collection_summary:
      summary = {
        'collected_count': self.collection_summary['collected_count'],
        'skipped_count': self.collection_summary['skipped_count'],
        'total_collected': str(self.collection_summary['total_collected']),
        'sale_ids': self.collection_summary['sale_ids'],
        'errors': self.collection_summary.get('errors', []),
      }
    return {
      'session': session_data,
      'collection_summary': summary,
    }
