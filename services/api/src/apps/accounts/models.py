import uuid

from django.conf import settings
from django.db import models


class Membership(models.Model):
  ROLE_CHOICES = [
    ('owner', 'Owner'),
    ('admin', 'Admin'),
    ('manager', 'Manager / Encargado'),
    ('cashier', 'Cashier / Caja'),
    ('staff', 'Staff / Empleado'),
    ('viewer', 'Solo lectura'),
    ('kitchen', 'Cocina'),
    ('salon', 'Salon / Toma pedidos'),
    ('analyst', 'Analyst'),
  ]

  user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='memberships', on_delete=models.CASCADE)
  business = models.ForeignKey('business.Business', related_name='memberships', on_delete=models.CASCADE)
  # ── Phase 2A: membership status ─────────────────────────────────────────
  class Status(models.TextChoices):
    ACTIVE    = 'active',    'Activo'
    INACTIVE  = 'inactive',  'Inactivo'
    SUSPENDED = 'suspended', 'Suspendido'

  role       = models.CharField(max_length=24, choices=ROLE_CHOICES, default='owner')
  created_at = models.DateTimeField(auto_now_add=True)

  # ── Phase 2A: new fields ──────────────────────────────────────────────────
  status = models.CharField(
    max_length=16, choices=Status.choices, default=Status.ACTIVE,
  )
  # branch_scope: NULL = access to HQ + all branches; set = access to that branch only
  # NOTE: OWNER always has NULL branch_scope (enforced at service layer)
  branch_scope = models.ForeignKey(
    'business.Business',
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name='scoped_memberships',
    help_text='NULL = full tree access. Set to restrict to one branch.',
  )
  # Individual permission overrides over role defaults (JSONB)
  permissions = models.JSONField(
    null=True, blank=True,
    help_text='Per-user permission overrides. e.g. {"can_void_order": true}',
  )
  created_by_user = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name='memberships_created',
  )
  updated_by_user = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name='memberships_updated',
  )
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    unique_together = ('user', 'business')
    indexes = [
      models.Index(fields=['business', 'status'], name='membership_business_status_idx'),
      models.Index(fields=['user',     'status'], name='membership_user_status_idx'),
    ]

  def __str__(self) -> str:
    return f"{self.user} → {self.business} ({self.role})"


from django.db.models.signals import pre_save
from django.dispatch import receiver
from rest_framework.exceptions import ValidationError

@receiver(pre_save, sender=Membership)
def check_seat_limit(sender, instance, raw=False, **kwargs):
    if raw or instance.pk: 
        return
        
    business = instance.business
    # Resolve HQ: avoid circular import if business logic is complex, 
    # but here we just need to follow relation.
    # Note: 'business' field might not be loaded if set by ID.
    # Safe guard:
    if not business:
        return

    # Restrict menu_qr service roles
    menu_qr_allowed_roles = {'owner', 'manager', 'staff', 'viewer'}
    if getattr(business, 'default_service', None) == 'menu_qr' and instance.role not in menu_qr_allowed_roles:
      raise ValidationError("Este rol no está disponible para el servicio de Menú QR.")

    # Helper to find HQ
    hq = business.parent if getattr(business, 'parent', None) else business
    
    # We use select_related in the query if possible, but here we are in a signal.
    # We just want to prevent obvious violations. Race conditions are handled in service.
    
    sub = getattr(hq, 'subscription', None)
    if not sub:
        return
        
    max_seats = getattr(sub, 'max_seats', 0)
    if max_seats <= 0:
        return 
        
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))
    
    # Exclude self if somehow this is run (it is pre_save create, so self is not in DB yet)
    # Using count() here is subject to race conditions, but serves as a second line of defense.
    current_count = Membership.objects.filter(business__id__in=family_ids).count()
    
    if current_count >= max_seats:
        raise ValidationError(f"Límite de usuarios ({max_seats}) alcanzado para la cuenta {hq.name}.")


class AccessAuditLog(models.Model):
    """
    Audit log for sensitive access management operations.
    Tracks password resets, role changes, account disabling, etc.
    """
    # ── Phase 2A: actor type enum ──────────────────────────────────────────
    class ActorType(models.TextChoices):
      USER     = 'USER',     'Usuario Admin'
      EMPLOYEE = 'EMPLOYEE', 'Empleado Operativo'
      SYSTEM   = 'SYSTEM',   'Sistema / Tarea Automatizada'

    ACTION_CHOICES = [
        # ── Memberships ───────────────────────────────────────────────────
        ('MEMBERSHIP_CREATED',    'Membership Created'),
        ('MEMBERSHIP_UPDATED',    'Membership Updated'),
        ('MEMBERSHIP_DELETED',    'Membership Deleted'),
        ('MEMBERSHIP_SUSPENDED',  'Membership Suspended'),
        # ── Contraseñas / acceso admin ────────────────────────────────────
        ('PASSWORD_RESET',              'Password Reset'),
        ('PASSWORD_RESET_CONFIRMED',    'Password Reset Confirmed'),
        ('EMAIL_VERIFICATION_SENT',     'Email Verification Sent'),
        ('EMAIL_VERIFIED',              'Email Verified'),
        # ── Cuentas operativas ────────────────────────────────────────────
        ('EMPLOYEE_CREATED',      'Employee Created'),
        ('EMPLOYEE_UPDATED',      'Employee Updated'),
        ('EMPLOYEE_SUSPENDED',    'Employee Suspended'),
        ('EMPLOYEE_REACTIVATED',  'Employee Reactivated'),
        ('EMPLOYEE_DELETED',      'Employee Deleted'),
        ('PIN_RESET',          'PIN Reset'),
        ('PIN_CHANGED',        'PIN Changed'),
        ('PIN_ROTATED',        'PIN Rotated'),   # legacy compat
        # ── Roles y permisos ──────────────────────────────────────────────
        ('ROLE_CHANGED',              'Role Changed'),
        ('PERMISSION_OVERRIDE_SET',   'Permission Override Set'),
        ('ROLE_PERMISSIONS_UPDATED',  'Role Permissions Updated'),  # legacy
        # ── Caja ─────────────────────────────────────────────────────────
        ('CASH_SESSION_OPENED',      'Cash Session Opened'),
        ('CASH_SESSION_CLOSED',      'Cash Session Closed'),
        ('CASH_SESSION_FORCE_CLOSED','Cash Session Force Closed'),
        ('CASH_MOVEMENT_CREATED',    'Cash Movement Created'),
        ('OPERATOR_SESSION_STARTED', 'Operator Session Started'),
        ('OPERATOR_SESSION_ENDED',   'Operator Session Ended'),
        # ── Sales POS ─────────────────────────────────────────────────────────
        ('SALE_CREATED_POS', 'Sale Created (POS)'),
        # ── Suscripción ───────────────────────────────────────────────────
        ('SUBSCRIPTION_CREATED',        'Subscription Created'),
        ('SUBSCRIPTION_STATUS_CHANGED', 'Subscription Status Changed'),
        ('SUBSCRIPTION_CANCELED',       'Subscription Canceled'),
        ('TRIAL_STARTED',               'Trial Started'),
        ('TRIAL_EXPIRED',               'Trial Expired'),
        # ── Seguridad ─────────────────────────────────────────────────────
        ('SESSION_REVOKED',   'Session Revoked'),
        ('SESSIONS_REVOKED',  'Sessions Revoked'),  # legacy compat
        ('LOGIN_FAILED',      'Login Failed'),
        ('ACCESS_DENIED',     'Access Denied'),
        # ── Legacy ────────────────────────────────────────────────────────
        ('ACCOUNT_DISABLED', 'Account Disabled'),  # legacy → EMPLOYEE_SUSPENDED
        ('ACCOUNT_ENABLED',  'Account Enabled'),   # legacy
    ]
    
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='audit_actions_performed',
        on_delete=models.SET_NULL,
        null=True,
        help_text='User who performed the action'
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='audit_actions_received',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text='User affected by the action. NULL for employee-only actions.',
    )
    business = models.ForeignKey(
        'business.Business',
        related_name='access_audit_logs',
        on_delete=models.CASCADE
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional context (e.g., old_role, new_role)'
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    # ── Phase 2A: new fields ──────────────────────────────────────────────
    actor_type = models.CharField(
        max_length=16,
        choices=ActorType.choices,
        default=ActorType.USER,
        help_text='USER for admin actions; EMPLOYEE for POS actions; SYSTEM for automated tasks.',
    )
    # actor_employee: set when actor_type=EMPLOYEE (complements existing `actor` FK for USER)
    actor_employee = models.ForeignKey(
        'accounts.EmployeeProfile',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='audit_actions_performed',
        help_text='Set when actor_type=EMPLOYEE.',
    )
    entity_type = models.CharField(
        max_length=64, blank=True, default='',
        help_text='Model name of affected object. e.g. membership, employee_profile, cash_session.',
    )
    entity_id = models.CharField(
        max_length=64, blank=True, default='',
        help_text='PK of the affected object (UUID or int as string).',
    )
    before_json = models.JSONField(
        null=True, blank=True,
        help_text='State of the object before the action.',
    )
    after_json = models.JSONField(
        null=True, blank=True,
        help_text='State of the object after the action.',
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', '-created_at']),
            models.Index(fields=['target_user', '-created_at']),
            # Phase 2A: entity-level lookup (e.g. full history of a specific object)
            models.Index(fields=['entity_type', 'entity_id'], name='auditlog_entity_idx'),
        ]
    
    def __str__(self) -> str:
        return f"{self.action} - {self.target_user} by {self.actor} at {self.created_at}"


class RolePermissionOverride(models.Model):
    """
    Custom permission overrides for roles per business.
    Allows owners to enable/disable specific permissions for each role.
    
    If no override exists, default permissions from rbac.py apply.
    If override exists with enabled=False, permission is revoked.
    If override exists with enabled=True, permission is granted (even if not in defaults).
    """
    business = models.ForeignKey(
        'business.Business',
        related_name='role_permission_overrides',
        on_delete=models.CASCADE
    )
    role = models.CharField(
        max_length=24,
        choices=Membership.ROLE_CHOICES,
        help_text='Role to configure (e.g., manager, cashier)'
    )
    service = models.CharField(
        max_length=24,
        help_text='Service context (gestion, restaurante, menu_qr)'
    )
    permission = models.CharField(
        max_length=64,
        help_text='Permission key (e.g., view_sales, manage_products)'
    )
    enabled = models.BooleanField(
        default=True,
        help_text='Whether this permission is enabled for the role'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('business', 'role', 'service', 'permission')
        indexes = [
            models.Index(fields=['business', 'service', 'role']),
        ]
    
    def __str__(self) -> str:
        status = "✓" if self.enabled else "✗"
        return f"{status} {self.business} - {self.role} - {self.service}.{self.permission}"


# ── Phase 2A: EmployeeProfile ─────────────────────────────────────────────────
#
# Operational identity for POS staff (cashiers, servers, kitchen, delivery).
# Does NOT require an email address. Authentication is via employee_code + PIN hash.
# Deliberately separated from Membership (administrative users) per Phase 1 v2.0 design.
#
class EmployeeProfile(models.Model):

    class RoleType(models.TextChoices):
        CASHIER    = 'cashier',    'Cajero'
        SERVER     = 'server',     'Mozo / Salón'
        KITCHEN    = 'kitchen',    'Cocina'
        DELIVERY   = 'delivery',   'Delivery'
        MANAGER_OP = 'manager_op', 'Encargado Operativo'

    class CredentialType(models.TextChoices):
        PIN     = 'pin',      'PIN Numérico'
        QR_CODE = 'qr_code',  'Código QR'
        NFC_TAG = 'nfc_tag',  'Tag NFC'

    class Status(models.TextChoices):
        ACTIVE    = 'active',    'Activo'
        INACTIVE  = 'inactive',  'Inactivo'
        SUSPENDED = 'suspended', 'Suspendido'

    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # FK to HQ always (never to a branch). branch field scopes the employee optionally.
    business = models.ForeignKey(
        'business.Business',
        on_delete=models.CASCADE,
        related_name='employee_profiles',
    )
    # Optional branch scope. NULL = works in all branches of this business.
    branch = models.ForeignKey(
        'business.Business',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='branch_employee_profiles',
    )
    # Optional link to a Django auth.User for employees who also access the dashboard
    linked_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='employee_profiles',
    )
    first_name = models.CharField(max_length=120)
    last_name  = models.CharField(max_length=120)
    # alias is display-only (tickets, UI). NOT unique. Identification is via employee_code.
    alias      = models.CharField(max_length=80, blank=True)

    # ── Identification ────────────────────────────────────────────────────────
    # Unique per business (HQ). Format: e.g. EMP-0042. Index covers login lookup.
    employee_code   = models.CharField(max_length=20)
    role_type       = models.CharField(max_length=20, choices=RoleType.choices)
    credential_type = models.CharField(
        max_length=16, choices=CredentialType.choices, default=CredentialType.PIN,
    )
    # Hash of the PIN/code. NEVER queried by value; verified in-memory after fetching by employee_code.
    # DO NOT add a DB index to this field.
    login_code_hash  = models.CharField(max_length=256)
    must_change_pin  = models.BooleanField(
        default=False,
        help_text='If True, employee must change PIN on next POS login.',
    )
    permission_overrides = models.JSONField(
        null=True, blank=True,
        help_text='Per-employee overrides over role_type defaults.',
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

    # ── Audit trail for who created/updated this profile ────────────────────
    created_by_membership = models.ForeignKey(
        'accounts.Membership',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_employee_profiles',
    )
    updated_by_membership = models.ForeignKey(
        'accounts.Membership',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='updated_employee_profiles',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['business', 'employee_code'],
                name='uq_employee_code_per_business',
            ),
        ]
        indexes = [
            # Primary lookup for POS login: business_id + employee_code
            models.Index(fields=['business', 'employee_code'], name='employee_code_lookup_idx'),
            models.Index(fields=['business', 'status'],        name='employee_business_status_idx'),
            models.Index(fields=['branch',   'status'],        name='employee_branch_status_idx'),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.first_name} {self.last_name} [{self.employee_code}] · {self.business_id}"

