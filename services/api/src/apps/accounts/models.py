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
