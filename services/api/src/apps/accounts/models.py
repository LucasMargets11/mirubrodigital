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

