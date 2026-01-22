from django.db import models


class Business(models.Model):
  SERVICE_CHOICES = [
    ('gestion', 'Gestion Comercial'),
    ('restaurante', 'Restaurantes'),
  ]

  name = models.CharField(max_length=255)
  default_service = models.CharField(max_length=32, choices=SERVICE_CHOICES, default='gestion')
  created_at = models.DateTimeField(auto_now_add=True)

  def __str__(self) -> str:
    return self.name


class BusinessPlan(models.TextChoices):
  STARTER = 'starter', 'Starter'
  PRO = 'pro', 'Pro'
  PLUS = 'plus', 'Plus'


class Subscription(models.Model):
  STATUS_CHOICES = [
    ('active', 'Active'),
    ('past_due', 'Past due'),
    ('canceled', 'Canceled'),
  ]

  business = models.OneToOneField('business.Business', related_name='subscription', on_delete=models.CASCADE)
  plan = models.CharField(max_length=32, choices=BusinessPlan.choices, default=BusinessPlan.STARTER)
  status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='active')
  renews_at = models.DateTimeField(null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  def __str__(self) -> str:
    return f"{self.business.name} · {self.plan} ({self.status})"
