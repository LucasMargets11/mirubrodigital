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
  role = models.CharField(max_length=24, choices=ROLE_CHOICES, default='owner')
  created_at = models.DateTimeField(auto_now_add=True)

  class Meta:
    unique_together = ('user', 'business')

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
    ACTION_CHOICES = [
        ('PASSWORD_RESET', 'Password Reset'),
        ('PIN_ROTATED', 'PIN Rotated'),
        ('ACCOUNT_DISABLED', 'Account Disabled'),
        ('ACCOUNT_ENABLED', 'Account Enabled'),
        ('ROLE_CHANGED', 'Role Changed'),
        ('ROLE_PERMISSIONS_UPDATED', 'Role Permissions Updated'),
        ('SESSIONS_REVOKED', 'Sessions Revoked'),
        ('MEMBERSHIP_CREATED', 'Membership Created'),
        ('MEMBERSHIP_DELETED', 'Membership Deleted'),
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
        on_delete=models.CASCADE,
        help_text='User affected by the action'
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
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', '-created_at']),
            models.Index(fields=['target_user', '-created_at']),
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

