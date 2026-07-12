import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


# ── Platform Account Profile ───────────────────────────────────────────────────
# Extends the stock Django User without replacing it.
# Auto-created on User post_save (see signal at the bottom of this file).
# Carries state the stock model lacks: email verification, password-reset tokens.

class AccountProfile(models.Model):
    """
    One-to-one extension of the platform User.
    Holds email-verification state and transient token fields.
    Tokens are stored as SHA-256 hashes — plaintext is sent once in the email URL.
    """

    class AccountStatus(models.TextChoices):
        ACTIVE                   = 'active',                    'Activo'
        PENDING_EMAIL_VERIFICATION = 'pending_email_verification', 'Pendiente de verificación'
        SUSPENDED                = 'suspended',                 'Suspendido'

    # ── Account mode (secondary users only) ───────────────────────────
    class AccountMode(models.TextChoices):
        OWNER_MANAGED = 'owner_managed', 'Administrada por el propietario'
        PERSONAL      = 'personal',      'Personal'

    # ── Platform internal roles (backoffice admin) ────────────────────────
    class InternalRole(models.TextChoices):
        SUPERADMIN    = 'superadmin',    'Super Admin'
        OPERATIONS    = 'operations',    'Operaciones'
        SUPPORT_AGENT = 'support_agent', 'Agente de Soporte'
        CONTENT_ADMIN = 'content_admin', 'Admin de Contenido'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='account_profile',
        primary_key=True,
    )
    account_status = models.CharField(
        max_length=32,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING_EMAIL_VERIFICATION,
    )
    email_verified = models.BooleanField(default=False)

    # ── Platform staff fields (internal backoffice) ──────────────────────
    is_platform_staff = models.BooleanField(
        default=False,
        help_text='Marks this user as Mi Rubro internal staff with access to /admin.',
    )
    internal_role = models.CharField(
        max_length=24,
        choices=InternalRole.choices,
        null=True, blank=True,
        help_text='Internal backoffice role. Only meaningful when is_platform_staff=True.',
    )

    # ── MFA (TOTP) fields ─────────────────────────────────────────────────
    mfa_secret_encrypted = models.TextField(
        null=True, blank=True,
        help_text='Fernet-encrypted TOTP secret. Never store plaintext.',
    )
    mfa_enabled = models.BooleanField(
        default=False,
        help_text='True once TOTP enrollment is confirmed.',
    )
    mfa_recovery_codes = models.JSONField(
        null=True, blank=True,
        help_text='List of SHA-256 hashed single-use recovery codes.',
    )
    mfa_enrolled_at = models.DateTimeField(null=True, blank=True)

    # ── Auth provider metadata ────────────────────────────────────────────
    class AuthProvider(models.TextChoices):
        EMAIL  = 'email',  'Email + Password'
        OTP    = 'otp',    'Email OTP'
        GOOGLE = 'google', 'Google OAuth'

    auth_provider = models.CharField(
        max_length=16,
        choices=AuthProvider.choices,
        default=AuthProvider.EMAIL,
        help_text='Method used for initial registration. Informational — does not restrict login.',
    )
    google_sub = models.CharField(
        max_length=255,
        null=True, blank=True,
        unique=True, db_index=True,
        help_text='Google OAuth `sub` claim. Unique per Google account. NULL if never linked.',
    )

    # ── Account mode & forced password change ─────────────────────────────
    account_mode = models.CharField(
        max_length=16,
        choices=AccountMode.choices,
        default=AccountMode.OWNER_MANAGED,
        help_text='owner_managed: credential control by owner. personal: user self-service.',
    )
    must_change_password = models.BooleanField(
        default=False,
        help_text='True when a personal-mode user must change password on next login.',
    )

    # Verification token (SHA-256 hash; plaintext sent once in email link)
    email_verification_token_hash   = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    email_verification_token_created_at = models.DateTimeField(null=True, blank=True)

    # Password-reset token (SHA-256 hash; plaintext sent once in email link)
    password_reset_token_hash       = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    password_reset_token_created_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Token helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def generate_verification_token(self) -> str:
        """
        Generate a new email-verification token.
        Returns the plaintext token (send this in the email URL — NOT stored).
        """
        token = secrets.token_urlsafe(32)
        self.email_verification_token_hash = self._hash(token)
        self.email_verification_token_created_at = timezone.now()
        self.save(update_fields=['email_verification_token_hash', 'email_verification_token_created_at', 'updated_at'])
        return token

    def verify_email_token(self, token: str) -> bool:
        """
        Validate a verification token.  Returns True and marks email verified if valid.
        """
        if not self.email_verification_token_hash or not self.email_verification_token_created_at:
            return False
        hours = getattr(settings, 'EMAIL_VERIFICATION_TOKEN_HOURS', 48)
        if timezone.now() > self.email_verification_token_created_at + timedelta(hours=hours):
            return False
        # Constant-time comparison to prevent timing attacks
        if not secrets.compare_digest(self._hash(token), self.email_verification_token_hash):
            return False
        self.email_verified = True
        self.account_status = self.AccountStatus.ACTIVE
        self.email_verification_token_hash = None
        self.email_verification_token_created_at = None
        self.save(update_fields=[
            'email_verified', 'account_status',
            'email_verification_token_hash', 'email_verification_token_created_at',
            'updated_at',
        ])
        return True

    def generate_password_reset_token(self) -> str:
        """
        Generate a password-reset token.
        Returns the plaintext token (send this in the email URL — NOT stored).
        """
        token = secrets.token_urlsafe(32)
        self.password_reset_token_hash = self._hash(token)
        self.password_reset_token_created_at = timezone.now()
        self.save(update_fields=['password_reset_token_hash', 'password_reset_token_created_at', 'updated_at'])
        return token

    def verify_password_reset_token(self, token: str) -> bool:
        """
        Validate a password-reset token.  Single-use: clears the token on success.
        """
        if not self.password_reset_token_hash or not self.password_reset_token_created_at:
            return False
        hours = getattr(settings, 'PASSWORD_RESET_TOKEN_HOURS', 2)
        if timezone.now() > self.password_reset_token_created_at + timedelta(hours=hours):
            return False
        if not secrets.compare_digest(self._hash(token), self.password_reset_token_hash):
            return False
        # Single-use: clear immediately
        self.password_reset_token_hash = None
        self.password_reset_token_created_at = None
        self.save(update_fields=['password_reset_token_hash', 'password_reset_token_created_at', 'updated_at'])
        return True

    # ── Account-mode helpers ───────────────────────────────────────────────

    def can_change_password(self) -> bool:
        """True if the user is allowed to self-change their password."""
        return self.account_mode == self.AccountMode.PERSONAL

    def can_self_reset(self) -> bool:
        """True if the user may request a password-reset email."""
        return self.account_mode == self.AccountMode.PERSONAL and bool(self.user.email)

    def __str__(self) -> str:
        return f"AccountProfile({self.user_id}, verified={self.email_verified})"


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
    ('contador', 'Contador'),
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
from django.core.exceptions import ValidationError as DjangoValidationError

@receiver(pre_save, sender=Membership)
def check_seat_limit(sender, instance, raw=False, **kwargs):
    if raw or instance.pk: 
        return

    # Owner membership never consumes a seat — skip entirely.
    if instance.role == 'owner':
        return
        
    business = instance.business
    if not business:
        return

    # Restrict menu_qr service roles
    menu_qr_allowed_roles = {'owner', 'manager', 'staff', 'viewer'}
    if getattr(business, 'default_service', None) == 'menu_qr' and instance.role not in menu_qr_allowed_roles:
      raise DjangoValidationError("Este rol no está disponible para el servicio de Menú QR.")

    # Helper to find HQ
    hq = business.parent if getattr(business, 'parent', None) else business
    family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))

    # ── V2-first subscription resolution ──────────────────────────────
    from apps.billing.runtime import resolve_subscription
    from apps.billing.plans import get_seat_limit

    resolved = resolve_subscription(hq)

    # No active subscription → block member creation
    if not resolved.access_granted:
        raise DjangoValidationError(
            'No tenés una suscripción activa. '
            'Activá un plan para poder agregar usuarios.'
        )

    if resolved.source == 'v2':
        max_seats = get_seat_limit(resolved.plan)
    elif resolved.source == 'legacy':
        max_seats = resolved.legacy_sub.max_seats if resolved.legacy_sub else 0
    else:
        max_seats = 0  # Unreachable after access_granted gate

    if max_seats > 0:
        # Count only secondary users (exclude owner)
        current_count = Membership.objects.filter(
            business__id__in=family_ids,
        ).exclude(
            role='owner',
        ).count()

        if current_count >= max_seats:
            raise DjangoValidationError(
                f'Límite de usuarios ({max_seats}) alcanzado para la cuenta {hq.name}.'
            )


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
        ('MEMBER_REACTIVATED',    'Member Reactivated'),
        ('MEMBER_REMOVED',        'Member Removed'),
        # ── Alta directa de usuarios internos ─────────────────────────────
        ('USER_CREATED',          'Internal User Created'),
        # ── Contraseñas / acceso admin ────────────────────────────────────
        ('PASSWORD_RESET',              'Password Reset'),
        ('PASSWORD_RESET_CONFIRMED',    'Password Reset Confirmed'),
        ('PASSWORD_RESET_REQUESTED',    'Password Reset Requested'),
        ('PASSWORD_CHANGED',            'Password Changed (Self-Service)'),
        ('PASSWORD_FORCE_CHANGED',      'Password Force Changed (First Login)'),
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
        # ── Onboarding (Wave 3 / Wave 4) ─────────────────────────────────────────
        ('EMAIL_VERIFICATION_BLOCKED',   'Email Verification Blocked'),
        ('ONBOARDING_SERVICE_SELECTED',  'Onboarding Service Selected'),
        ('ONBOARDING_CHECKOUT_STARTED',  'Onboarding Checkout Started'),   # Wave 4
        ('ONBOARDING_COMPLETED',         'Onboarding Completed'),
        # ── Legacy ────────────────────────────────────────────────────────
        ('ACCOUNT_DISABLED', 'Account Disabled'),  # legacy → EMPLOYEE_SUSPENDED
        ('ACCOUNT_ENABLED',  'Account Enabled'),   # legacy
        # ── Platform Admin (Backoffice Interno) ──────────────────────────
        ('PLATFORM_ADMIN_LOGIN',       'Platform Admin Login'),
        ('PLATFORM_ADMIN_ACTION',      'Platform Admin Generic Action'),
        ('PLATFORM_STAFF_GRANTED',     'Platform Staff Access Granted'),
        ('PLATFORM_STAFF_REVOKED',     'Platform Staff Access Revoked'),
        ('PLATFORM_ROLE_CHANGED',      'Platform Internal Role Changed'),
        # ── Platform Admin Auth Hardening (Phase 1.1) ─────────────────────
        ('ADMIN_LOGIN_SUCCESS',        'Admin Login Success'),
        ('ADMIN_LOGIN_FAILED',         'Admin Login Failed'),
        ('ADMIN_LOGIN_THROTTLED',      'Admin Login Throttled'),
        ('ADMIN_LOGIN_COOLDOWN',       'Admin Login Cooldown Triggered'),
        ('ADMIN_LOGIN_BLOCKED_IP',     'Admin Login Blocked IP'),
        ('ADMIN_MFA_REQUIRED',         'Admin MFA Required'),
        ('ADMIN_MFA_SUCCESS',          'Admin MFA Success'),
        ('ADMIN_MFA_FAILED',           'Admin MFA Failed'),
        ('ADMIN_MFA_RECOVERY_USED',    'Admin MFA Recovery Code Used'),
        ('ADMIN_MFA_ENABLED',          'Admin MFA Enabled'),
        ('ADMIN_MFA_DISABLED',         'Admin MFA Disabled'),
        ('ADMIN_MFA_RESET',            'Admin MFA Reset'),
        ('ADMIN_SUSPICIOUS_AUTH',      'Admin Suspicious Auth Pattern'),
        # ── Admin Backoffice Phase 2 ──────────────────────────────────────
        ('ADMIN_CLIENT_VIEWED',        'Admin Client Viewed'),
        ('ADMIN_SUBSCRIPTION_VIEWED',  'Admin Subscription Viewed'),
        ('ADMIN_SUBSCRIPTION_CANCELED', 'Admin Subscription Canceled'),
        ('ADMIN_NOTE_CREATED',         'Admin Internal Note Created'),
        # ── Admin Backoffice Phase 3 — Support ────────────────────────────
        ('ADMIN_TICKET_CREATED',       'Admin Ticket Created'),
        ('ADMIN_TICKET_UPDATED',       'Admin Ticket Updated'),
        ('ADMIN_TICKET_VIEWED',        'Admin Ticket Viewed'),
        ('ADMIN_TICKET_MESSAGE',       'Admin Ticket Message Sent'),
        # ── Admin Backoffice Phase 4 — Reports ─────────────────────────────
        ('ADMIN_REPORT_VIEWED',        'Admin Report Viewed'),
        ('ADMIN_ALERTS_VIEWED',        'Admin Alerts Viewed'),
        # ── Admin Backoffice Phase 5 — Blog CMS ──────────────────────────────
        ('BLOG_POST_CREATED',          'Blog Post Created'),
        ('BLOG_POST_UPDATED',          'Blog Post Updated'),
        ('BLOG_POST_PUBLISHED',        'Blog Post Published'),
        ('BLOG_POST_UNPUBLISHED',      'Blog Post Unpublished'),
        ('BLOG_POST_ARCHIVED',         'Blog Post Archived'),
        ('BLOG_POST_SCHEDULED',        'Blog Post Scheduled'),
        ('BLOG_POST_VIEWED',           'Blog Post Viewed'),
        # ── Tenant Support ────────────────────────────────────────────────
        ('TENANT_TICKET_CREATED',      'Tenant Ticket Created'),
        ('TENANT_TICKET_REPLIED',      'Tenant Ticket Replied'),
        ('TENANT_TICKET_CLOSED',       'Tenant Ticket Closed'),
        ('TENANT_TICKET_REOPENED',     'Tenant Ticket Reopened'),
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
        on_delete=models.SET_NULL,
        null=True, blank=True,
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


# ── Auto-create AccountProfile on User creation ───────────────────────────────
# This keeps existing users working: the migration backfills existing rows,
# and new users get a profile created automatically.

from django.db.models.signals import post_save  # noqa: E402
from django.dispatch import receiver as _receiver  # noqa: E402


@_receiver(post_save, sender=settings.AUTH_USER_MODEL)
def _create_account_profile(sender, instance, created: bool, **kwargs):
    if created:
        AccountProfile.objects.get_or_create(user=instance)


# ── Split-file models — imported here so Django's migration framework
#    discovers them when it imports apps.accounts.models. ───────────────────────
from apps.accounts.admin_internal_note import AdminInternalNote  # noqa: E402, F401
from apps.accounts.admin_notification import AdminNotification    # noqa: E402, F401
from apps.accounts.support_ticket import SupportTicket, TicketMessage  # noqa: E402, F401

