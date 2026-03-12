"""
cash/pos_serializers.py — POS employee-specific serializers for cash domain.

These serializers are intentionally separate from the admin cash serializers
to keep POS flows clean and avoid coupling with auth.User assumptions.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.utils import timezone
from rest_framework import serializers

from .models import CashMovement, CashRegister, CashSession, Payment
from .services import compute_session_totals


class PosEmployeeSummarySerializer(serializers.Serializer):
    """Minimal employee identity for POS session responses."""
    id = serializers.CharField()
    employee_code = serializers.CharField()
    display_name = serializers.SerializerMethodField()

    def get_display_name(self, obj):
        return obj.alias or f'{obj.first_name} {obj.last_name}'.strip()


class PosCashSessionSerializer(serializers.Serializer):
    """Read-only representation of a CashSession for POS consumers."""
    id = serializers.UUIDField()
    status = serializers.CharField()
    opening_cash_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    closing_cash_counted = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    expected_cash_total = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    difference_amount = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    closing_note = serializers.CharField()
    opened_by_name = serializers.CharField()
    opened_at = serializers.DateTimeField()
    closed_at = serializers.DateTimeField(allow_null=True)
    opened_by_employee = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()

    def get_opened_by_employee(self, obj):
        if obj.opened_by_employee:
            return PosEmployeeSummarySerializer(obj.opened_by_employee).data
        return None

    def get_totals(self, obj):
        raw = compute_session_totals(obj)
        return {
            'total_sales': raw['payments_total'],
            'cash_in_from_sales': raw['cash_payments_total'],
            'total_in': raw['movements_in_total'],
            'total_out': raw['movements_out_total'],
            'cash_expected_total': raw['cash_expected_total'],
        }


class PosCashMovementSerializer(serializers.Serializer):
    """Read-only representation of a single CashMovement for POS consumers."""
    id = serializers.UUIDField()
    movement_type = serializers.CharField()
    category = serializers.CharField()
    method = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    note = serializers.CharField()
    created_at = serializers.DateTimeField()
    session_id = serializers.UUIDField()


class PosCashOpenSerializer(serializers.Serializer):
    """Validates and creates a CashSession from an employee POS request."""
    opening_cash_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2,
        required=False,
        default=Decimal('0'),
        min_value=Decimal('0'),
    )
    register_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_register_id(self, value):
        if value is None:
            return value
        business = self.context['business']
        try:
            register = CashRegister.objects.get(pk=value, business=business, is_active=True)
        except CashRegister.DoesNotExist as exc:
            raise serializers.ValidationError(
                'No encontramos la caja seleccionada en este negocio.'
            ) from exc
        self.context['register'] = register
        return value

    def validate(self, attrs):
        employee = self.context['employee']
        business = self.context['business']
        register = self.context.get('register')

        # An employee can only have one open session at a time.
        if CashSession.objects.filter(
            business=business,
            status=CashSession.Status.OPEN,
            opened_by_employee=employee,
        ).exists():
            raise serializers.ValidationError(
                'Ya tenés una sesión de caja abierta. Cerrala antes de abrir una nueva.'
            )

        # If a register was specified, check it's not already in use by another session.
        if register is not None:
            if CashSession.objects.filter(
                business=business,
                status=CashSession.Status.OPEN,
                register=register,
            ).exists():
                raise serializers.ValidationError(
                    'Esta caja física ya tiene una sesión abierta.'
                )

        return attrs

    def create(self, validated_data):
        employee = self.context['employee']
        business = self.context['business']
        register = self.context.get('register')
        opening_amount = validated_data.get('opening_cash_amount') or Decimal('0')
        display_name = (
            employee.alias or f'{employee.first_name} {employee.last_name}'.strip()
        )
        session = CashSession.objects.create(
            business=business,
            register=register,
            branch=employee.branch,
            opened_by=None,                   # employee flow — no auth.User
            opened_by_employee=employee,
            opened_by_name=display_name,
            opening_cash_amount=opening_amount,
        )
        return session

    def to_representation(self, instance):
        return PosCashSessionSerializer(instance).data


class PosCashCloseSerializer(serializers.Serializer):
    """Validates and closes the employee's current CashSession."""
    closing_cash_counted = serializers.DecimalField(
        max_digits=12, decimal_places=2,
        required=False,
        allow_null=True,
        min_value=Decimal('0'),
    )
    closing_note = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        session = self.context.get('session')
        if session is None or session.status != CashSession.Status.OPEN:
            raise serializers.ValidationError('No hay una sesión de caja abierta para cerrar.')
        return attrs

    def save(self, **kwargs):
        session: CashSession = self.context['session']
        employee = self.context['employee']
        closing_counted = self.validated_data.get('closing_cash_counted')
        closing_note = self.validated_data.get('closing_note', '')

        # Compute expected total before closing
        totals = compute_session_totals(session)
        expected = totals['cash_expected_total']

        difference = None
        if closing_counted is not None:
            difference = closing_counted - expected

        session.status = CashSession.Status.CLOSED
        session.closed_at = timezone.now()
        session.closed_by = None                  # employee flow — no auth.User
        session.closed_by_employee = employee
        if closing_counted is not None:
            session.closing_cash_counted = closing_counted
        session.expected_cash_total = expected
        if difference is not None:
            session.difference_amount = difference
        session.closing_note = closing_note
        session.save(update_fields=[
            'status', 'closed_at', 'closed_by', 'closed_by_employee',
            'closing_cash_counted', 'expected_cash_total', 'difference_amount',
            'closing_note',
        ])
        return session

    def to_representation(self, instance):
        return PosCashSessionSerializer(instance).data


class PosCashMovementCreateSerializer(serializers.Serializer):
    """Validates and creates a CashMovement inside the employee's current session."""
    movement_type = serializers.ChoiceField(choices=CashMovement.MovementType.choices)
    category = serializers.ChoiceField(
        choices=CashMovement.Category.choices,
        default=CashMovement.Category.OTHER,
    )
    method = serializers.ChoiceField(
        choices=Payment.Method.choices,
        default=Payment.Method.CASH,
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    note = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        session = self.context.get('session')
        if session is None or session.status != CashSession.Status.OPEN:
            raise serializers.ValidationError(
                'No hay una sesión de caja abierta para registrar movimientos.'
            )
        return attrs

    def create(self, validated_data):
        session: CashSession = self.context['session']
        business = self.context['business']
        movement = CashMovement.objects.create(
            business=business,
            session=session,
            movement_type=validated_data['movement_type'],
            category=validated_data.get('category', CashMovement.Category.OTHER),
            method=validated_data.get('method', Payment.Method.CASH),
            amount=validated_data['amount'],
            note=validated_data.get('note', ''),
            created_by=None,  # employee flow — no auth.User
        )
        return movement

    def to_representation(self, instance):
        return PosCashMovementSerializer(instance).data
