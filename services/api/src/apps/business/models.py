from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Business(models.Model):
  SERVICE_CHOICES = [
    ('gestion', 'Gestion Comercial'),
    ('restaurante', 'Restaurantes'),
    ('menu_qr', 'Menú QR Online'),
  ]

  name = models.CharField(max_length=255)
  parent = models.ForeignKey('self', null=True, blank=True, related_name='branches', on_delete=models.PROTECT)
  default_service = models.CharField(max_length=32, choices=SERVICE_CHOICES, default='gestion')
  
  STATUS_CHOICES = [
        ('pending_activation', 'Pending Activation'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
  ]
  status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='active') 
  
  created_at = models.DateTimeField(auto_now_add=True)

  def __str__(self) -> str:
    return self.name

  @property
  def is_hq(self) -> bool:
    return self.parent is None

  @property
  def is_branch(self) -> bool:
    return self.parent is not None

  def get_children_ids(self):
    return self.branches.values_list('id', flat=True)


class BusinessPlan(models.TextChoices):
  STARTER = 'starter', 'Starter'
  PRO = 'pro', 'Pro'
  PLUS = 'plus', 'Plus'
  MENU_QR = 'menu_qr', 'Menú QR'


class Subscription(models.Model):
  STATUS_CHOICES = [
    ('active', 'Active'),
    ('past_due', 'Past due'),
    ('canceled', 'Canceled'),
  ]

  business = models.OneToOneField('business.Business', related_name='subscription', on_delete=models.CASCADE)
  plan = models.CharField(max_length=32, choices=BusinessPlan.choices, default=BusinessPlan.STARTER)
  service = models.CharField(max_length=32, choices=Business.SERVICE_CHOICES, default='gestion')
  status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='active')
  max_branches = models.PositiveIntegerField(default=0)
  max_seats = models.PositiveIntegerField(default=5)
  renews_at = models.DateTimeField(null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  def __str__(self) -> str:
    return f"{self.business.name} · {self.plan} ({self.status})"

  def save(self, *args, **kwargs):  # pragma: no cover - simple guard
    if not self.service and self.business_id:
      business = getattr(self, 'business', None)
      if business is None:
        business = Business.objects.filter(pk=self.business_id).only('default_service').first()
      if business and business.default_service:
        self.service = business.default_service
    super().save(*args, **kwargs)


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


class BusinessBillingProfile(models.Model):
  """Perfil fiscal/legal del negocio para emisión de comprobantes."""
  
  TAX_ID_TYPE_CHOICES = [
    ('cuit', 'CUIT'),
    ('cuil', 'CUIL'),
    ('dni', 'DNI'),
    ('other', 'Otro'),
  ]
  
  VAT_CONDITION_CHOICES = [
    ('responsable_inscripto', 'Responsable Inscripto'),
    ('monotributo', 'Monotributo'),
    ('exento', 'Exento'),
    ('consumidor_final', 'Consumidor Final'),
    ('no_responsable', 'No Responsable'),
  ]
  
  business = models.OneToOneField(
    'business.Business',
    related_name='billing_profile',
    on_delete=models.CASCADE,
    primary_key=True
  )
  
  # Identificación fiscal
  legal_name = models.CharField(max_length=255, blank=True)
  trade_name = models.CharField(max_length=255, blank=True)
  tax_id_type = models.CharField(max_length=16, choices=TAX_ID_TYPE_CHOICES, blank=True)
  tax_id = models.CharField(max_length=64, blank=True, db_index=True)
  vat_condition = models.CharField(max_length=32, choices=VAT_CONDITION_CHOICES, blank=True)
  iibb = models.CharField(max_length=64, blank=True, help_text='Ingresos Brutos')
  activity_start_date = models.DateField(null=True, blank=True)
  
  # Domicilios
  commercial_address = models.TextField(blank=True)
  fiscal_address = models.TextField(blank=True)
  
  # Contacto
  email = models.EmailField(blank=True)
  phone = models.CharField(max_length=64, blank=True)
  website = models.URLField(blank=True)
  
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
  
  class Meta:
    verbose_name = 'Business Billing Profile'
    verbose_name_plural = 'Business Billing Profiles'
  
  def __str__(self) -> str:
    return f"Billing Profile · {self.business.name}"
  
  def is_complete(self) -> bool:
    """Valida si el perfil tiene los datos mínimos para emitir comprobantes."""
    return bool(self.legal_name and self.tax_id and self.commercial_address)


class BusinessBranding(models.Model):
  """Assets de branding del negocio (logos, colores)."""
  
  business = models.OneToOneField(
    'business.Business',
    related_name='branding',
    on_delete=models.CASCADE,
    primary_key=True
  )
  
  logo_horizontal = models.ImageField(
    upload_to='business/logos/',
    null=True,
    blank=True,
    help_text='Logo horizontal para encabezados de documentos'
  )
  logo_square = models.ImageField(
    upload_to='business/logos/',
    null=True,
    blank=True,
    help_text='Logo cuadrado/icono'
  )
  accent_color = models.CharField(
    max_length=7,
    blank=True,
    help_text='Color hex (ej: #0066CC)'
  )
  
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
  
  class Meta:
    verbose_name = 'Business Branding'
    verbose_name_plural = 'Business Branding'
  
  def __str__(self) -> str:
    return f"Branding · {self.business.name}"


@receiver(post_save, sender=Business)
def ensure_business_profiles(sender, instance: Business, created: bool, **kwargs):  # pragma: no cover
  """Auto-crear perfiles de billing y branding al crear un Business."""
  if created:
    BusinessBillingProfile.objects.get_or_create(business=instance)
    BusinessBranding.objects.get_or_create(business=instance)
