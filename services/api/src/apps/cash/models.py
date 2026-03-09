from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class CashRegister(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='cash_registers', on_delete=models.CASCADE)
  name = models.CharField(max_length=128)
  is_active = models.BooleanField(default=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['name']
    constraints = [
      models.UniqueConstraint(fields=['business', 'name'], name='cash_register_unique_name_per_business'),
    ]

  def __str__(self) -> str:  # pragma: no cover
    return f"{self.name} · {self.business_id}"


class CashSession(models.Model):
  class Status(models.TextChoices):
    OPEN   = 'open',    'Abierta'
    CLOSED = 'closed',  'Cerrada'
    AUDITED = 'audited', 'Auditada'  # Phase 2A

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='cash_sessions', on_delete=models.CASCADE)
  register = models.ForeignKey('cash.CashRegister', related_name='sessions', null=True, blank=True, on_delete=models.PROTECT)
  # DEPRECATED: use opened_by_employee (operativo) or keep for admin overrides.
  # Made nullable (migration 0006) so POS employee flow can create sessions without
  # a Django auth.User. Admin flow still populates this field when user is a real User.
  opened_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='cash_sessions_opened',
    on_delete=models.PROTECT,
    null=True,
    blank=True,
  )
  opened_by_name = models.CharField(max_length=120, blank=True, default='')
  # DEPRECATED: use closed_by_employee. Kept for backward compat.
  closed_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='cash_sessions_closed',
    null=True,
    blank=True,
    on_delete=models.PROTECT,
  )
  opening_cash_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
  closing_cash_counted = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
  expected_cash_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
  difference_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
  closing_note = models.TextField(blank=True)
  status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
  opened_at = models.DateTimeField(auto_now_add=True)
  closed_at = models.DateTimeField(null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  # ── Phase 2A: new fields ──────────────────────────────────────────────
  # Branch of the terminal that generated this session
  branch = models.ForeignKey(
    'business.Business',
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name='branch_cash_sessions',
  )
  # FK to new Terminal (Phase 2A). Nullable until data migration populates from `register`.
  # Future: will replace `register` after Phase 2C consolidation.
  terminal = models.ForeignKey(
    'cash.Terminal',
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name='cash_sessions',
    help_text='Phase 2A canonical terminal reference. Coexists with legacy `register`.',
  )
  # Operational actor who opened/closed the session at the POS
  opened_by_employee = models.ForeignKey(
    'accounts.EmployeeProfile',
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name='cash_sessions_opened',
  )
  closed_by_employee = models.ForeignKey(
    'accounts.EmployeeProfile',
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name='cash_sessions_closed',
  )

  class Meta:
    ordering = ['-opened_at']
    constraints = [
      # Legacy: one open session per CashRegister
      models.UniqueConstraint(
        fields=['register'],
        condition=Q(status='open'),
        name='cash_session_unique_open_register',
      ),
      # Phase 2A: one open session per Terminal (NULL terminal rows excluded by PG NULL semantics)
      models.UniqueConstraint(
        fields=['terminal'],
        condition=Q(status='open'),
        name='cash_session_one_open_per_terminal',
      ),
    ]
    indexes = [
      models.Index(fields=['business', 'status'],    name='cashsess_biz_stat_idx'),
      models.Index(fields=['business', 'opened_at'], name='cashsess_biz_open_idx'),
    ]

  def __str__(self) -> str:  # pragma: no cover
    return f"Sesion caja {self.id} · {self.business_id}"


class Payment(models.Model):
  class Method(models.TextChoices):
    CASH = 'cash', 'Efectivo'
    DEBIT = 'debit', 'Débito'
    CREDIT = 'credit', 'Crédito'
    TRANSFER = 'transfer', 'Transferencia'
    WALLET = 'wallet', 'Billetera'
    ACCOUNT = 'account', 'Cuenta corriente'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='payments', on_delete=models.CASCADE)
  sale = models.ForeignKey('sales.Sale', related_name='payments', on_delete=models.PROTECT)
  session = models.ForeignKey('cash.CashSession', related_name='payments', on_delete=models.PROTECT)
  method = models.CharField(max_length=16, choices=Method.choices)
  amount = models.DecimalField(max_digits=12, decimal_places=2)
  reference = models.CharField(max_length=128, blank=True)
  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='payments_created',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['-created_at']
    indexes = [
      models.Index(fields=['business', 'created_at']),
      models.Index(fields=['business', 'session']),
      models.Index(fields=['business', 'sale']),
    ]

  def __str__(self) -> str:  # pragma: no cover
    return f"Pago {self.amount} · {self.sale_id}"


class CashMovement(models.Model):
  class MovementType(models.TextChoices):
    IN = 'in', 'Ingreso'
    OUT = 'out', 'Egreso'

  class Category(models.TextChoices):
    EXPENSE = 'expense', 'Gasto'
    WITHDRAW = 'withdraw', 'Retiro'
    DEPOSIT = 'deposit', 'Depósito'
    OTHER = 'other', 'Otro'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='cash_movements', on_delete=models.CASCADE)
  session = models.ForeignKey('cash.CashSession', related_name='movements', on_delete=models.PROTECT)
  movement_type = models.CharField(max_length=8, choices=MovementType.choices)
  category = models.CharField(max_length=16, choices=Category.choices, default=Category.OTHER)
  method = models.CharField(max_length=16, choices=Payment.Method.choices, default=Payment.Method.CASH)
  amount = models.DecimalField(max_digits=12, decimal_places=2)
  note = models.TextField(blank=True)
  created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    related_name='cash_movements_created',
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
  )
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['-created_at']
    indexes = [
      models.Index(fields=['business', 'created_at']),
      models.Index(fields=['business', 'session']),
    ]

  def __str__(self) -> str:  # pragma: no cover
    return f"Movimiento {self.movement_type} · {self.amount}"


# ── Phase 2A: Terminal ────────────────────────────────────────────────────────
#
# Canonical physical/logical point-of-sale device.
# Replaces and extends the concept of CashRegister.
# CashRegister rows are linked via `cash_register` FK during the transition period.
# Full consolidation (dropping CashRegister) is deferred to Phase 2C.
#
class Terminal(models.Model):

    class TerminalType(models.TextChoices):
        CASHIER  = 'cashier',  'Caja'
        SERVER   = 'server',   'Mozo / Salón'
        KITCHEN  = 'kitchen',  'Cocina'
        DELIVERY = 'delivery', 'Delivery'

    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Always FK to HQ. branch narrows down the physical location.
    business = models.ForeignKey(
        'business.Business',
        on_delete=models.CASCADE,
        related_name='terminals',
    )
    branch = models.ForeignKey(
        'business.Business',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='branch_terminals',
    )
    # Transition FK: if this Terminal was migrated from a CashRegister, the link is preserved.
    # NULL for new Terminals created directly in Phase 2A+.
    cash_register = models.OneToOneField(
        'cash.CashRegister',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='terminal',
        help_text='Transition reference: linked CashRegister. Null for post-Phase-2A terminals.',
    )
    # Unique code per business. e.g. BARRA-01, CAJA-PISO-2
    code          = models.CharField(max_length=32)
    name          = models.CharField(max_length=128)
    terminal_type = models.CharField(
        max_length=16, choices=TerminalType.choices, default=TerminalType.CASHIER,
    )
    # shared_mode_enabled: allows multiple OperatorSessions sequentially without closing
    shared_mode_enabled         = models.BooleanField(default=False)
    # requires_operator_selection: every sensitive operation requires an active OperatorSession
    requires_operator_selection = models.BooleanField(default=False)
    # Opaque token set by the physical device; used for device-level authentication
    device_token = models.CharField(max_length=256, blank=True)
    is_active    = models.BooleanField(default=True)
    config       = models.JSONField(
        null=True, blank=True,
        help_text='Terminal-specific config: default_printer, sector, etc.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['business', 'code'],
                name='uq_terminal_code_per_business',
            ),
        ]
        indexes = [
            models.Index(fields=['business', 'is_active'], name='terminal_business_active_idx'),
            models.Index(fields=['branch'],                name='terminal_branch_idx'),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Terminal {self.code} · {self.name} · {self.business_id}"


# ── Phase 2A: OperatorSession ─────────────────────────────────────────────────
#
# Logical session: who is actively operating a Terminal at a given moment.
# Deliberately DECOUPLED from CashSession:
#   - A kitchen Terminal has OperatorSessions but never a CashSession.
#   - A shared cashier terminal can have multiple sequential OperatorSessions
#     within one CashSession (cash_session FK is optional).
# Rule: only ONE active (logout_at IS NULL) OperatorSession per Terminal at any time.
#
class OperatorSession(models.Model):

    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    terminal = models.ForeignKey(
        'cash.Terminal',
        on_delete=models.CASCADE,
        related_name='operator_sessions',
    )
    employee = models.ForeignKey(
        'accounts.EmployeeProfile',
        on_delete=models.PROTECT,
        related_name='operator_sessions',
    )
    # Optional: set only when terminal_type=CASHIER and a CashSession is open.
    cash_session = models.ForeignKey(
        'cash.CashSession',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='operator_sessions',
    )
    login_at       = models.DateTimeField(auto_now_add=True)
    logout_at      = models.DateTimeField(null=True, blank=True)
    # auto_logout_at: populated by an inactivity timeout task (future)
    auto_logout_at = models.DateTimeField(null=True, blank=True)
    total_orders   = models.PositiveIntegerField(
        default=0,
        help_text='Cached count of orders processed in this session.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Enforces: at most ONE active (no logout) session per terminal.
            # PostgreSQL NULL semantics guarantee: rows with NULL terminal_id are excluded.
            models.UniqueConstraint(
                fields=['terminal'],
                condition=Q(logout_at__isnull=True),
                name='uq_operator_session_active_per_terminal',
            ),
        ]
        indexes = [
            models.Index(fields=['terminal', 'logout_at'], name='opsession_terminal_logout_idx'),
            models.Index(fields=['employee', 'logout_at'], name='opsession_employee_logout_idx'),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"OperatorSession · {self.employee_id} @ {self.terminal_id} · {'active' if not self.logout_at else 'closed'}"
