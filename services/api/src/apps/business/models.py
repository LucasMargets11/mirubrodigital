from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


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


class CommercialSettingsManager(models.Manager):
  def for_business(self, business: "Business") -> "CommercialSettings":
    if business is None:
      raise ValueError("Business is required to resolve commercial settings")
    settings, _ = self.get_or_create(business=business)
    return settings


class CommercialSettings(models.Model):
  business = models.OneToOneField('business.Business', related_name='commercial_settings', on_delete=models.CASCADE)
  allow_sell_without_stock = models.BooleanField(default=False)
  block_sales_if_no_open_cash_session = models.BooleanField(default=True)
  require_customer_for_sales = models.BooleanField(default=False)
  allow_negative_price_or_discount = models.BooleanField(default=False)
  warn_on_low_stock_threshold_enabled = models.BooleanField(default=True)
  low_stock_threshold_default = models.PositiveIntegerField(default=5)
  enable_sales_notes = models.BooleanField(default=True)
  enable_receipts = models.BooleanField(default=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  objects = CommercialSettingsManager()

  class Meta:
    verbose_name = 'Commercial Settings'
    verbose_name_plural = 'Commercial Settings'

  def __str__(self) -> str:
    return f"Settings · {self.business_id}"


@receiver(post_save, sender=Business)
def ensure_commercial_settings(sender, instance: Business, created: bool, **kwargs):  # pragma: no cover
  CommercialSettings.objects.get_or_create(business=instance)
