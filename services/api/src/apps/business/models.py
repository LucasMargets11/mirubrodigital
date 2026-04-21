from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify

from common.storages import public_media_storage


class Business(models.Model):
  # ── Backward-compat choices (kept for existing code) ─────────────────────
  SERVICE_CHOICES = [
    ('gestion', 'Gestion Comercial'),
    ('restaurante', 'Restaurantes'),
    ('menu_qr', 'Menú QR Online'),
    ('menu_qr_visual', 'Menú QR Visual'),
    ('menu_qr_marca', 'Menú QR Marca'),
    ('qr_reviews', 'QR de Reseñas'),
  ]

  # ── Phase 2A: canonical service enum ─────────────────────────────────────
  class ServiceType(models.TextChoices):
    """Canonical service type. Coexists with deprecated `default_service`."""
    GESTION      = 'gestion',       'Gestión Comercial'
    RESTAURANTE  = 'restaurante',   'Restaurantes'
    MENU_QR      = 'menu_qr',       'Menú QR'
    MENU_QR_VISUAL = 'menu_qr_visual', 'Menú QR Visual'
    MENU_QR_MARCA  = 'menu_qr_marca',  'Menú QR Marca'
    QR_REVIEWS   = 'qr_reviews',    'QR de Reseñas'

  # ── Status choices (Phase 2A extends legacy 3-value set) ─────────────────
  STATUS_CHOICES = [
    # ── Canonical (Phase 1 v2.0) ─────────────────────────────────────
    ('onboarding', 'Onboarding'),         # Creado, sin suscripción activa
    ('trialing',   'Trialing'),           # Período de prueba activo (Wave 3)
    ('active',     'Active'),             # Operativo, suscripción al día
    ('past_due',   'Past Due'),           # Pago vencido, en período de gracia (Wave 3)
    ('suspended',  'Suspended'),          # Bloqueado por billing o admin
    ('canceled',   'Canceled'),           # Cerrado definitivamente
    # ── DEPRECATED legacy values (preserved for existing rows) ───────
    ('pending_activation', 'Pending Activation'),  # → migrate to onboarding
  ]

  # ── Core fields (existing) ────────────────────────────────────────────────
  name           = models.CharField(max_length=255)
  parent         = models.ForeignKey(
    'self', null=True, blank=True, related_name='branches', on_delete=models.PROTECT,
  )
  # DEPRECATED: use service_type. Kept for backward compat.
  default_service = models.CharField(max_length=32, choices=SERVICE_CHOICES, default='gestion')
  status          = models.CharField(max_length=32, choices=STATUS_CHOICES, default='active')
  created_at      = models.DateTimeField(auto_now_add=True)

  # ── Phase 2A: new fields ──────────────────────────────────────────────────
  slug         = models.SlugField(
    max_length=80, null=True, blank=True,
    help_text='URL-friendly identifier. Populated by data migration 0016.',
  )
  service_type = models.CharField(
    max_length=32, choices=ServiceType.choices, null=True, blank=True,
    help_text='Canonical service type. Populated from default_service via data migration 0016.',
  )
  country      = models.CharField(max_length=2,  default='AR')
  currency     = models.CharField(max_length=3,  default='ARS')
  timezone     = models.CharField(max_length=64, default='America/Argentina/Buenos_Aires')
  trial_starts_at = models.DateTimeField(null=True, blank=True)
  trial_ends_at   = models.DateTimeField(null=True, blank=True)
  activated_at    = models.DateTimeField(null=True, blank=True)
  suspended_at    = models.DateTimeField(null=True, blank=True)
  updated_at      = models.DateTimeField(auto_now=True)

  class Meta:
    indexes = [
      models.Index(fields=['status'],  name='business_status_idx'),
      models.Index(fields=['parent'],  name='business_parent_idx'),
    ]
    constraints = [
      # Sparse unique: allows multiple NULLs, prevents duplicate non-null slugs
      models.UniqueConstraint(
        fields=['slug'],
        condition=models.Q(slug__isnull=False),
        name='uq_business_slug',
      ),
    ]

  def save(self, *args, **kwargs):
    if not self.slug:
      base = slugify(self.name) or f'negocio-{self.pk or "new"}'
      base = base[:80]
      slug = base
      counter = 1
      while Business.objects.filter(slug=slug).exclude(pk=self.pk).exists():
        suffix = f'-{counter}'
        slug = f'{base[:80 - len(suffix)]}{suffix}'
        counter += 1
      self.slug = slug
    super().save(*args, **kwargs)

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
  BUSINESS = 'business', 'Business'
  ENTERPRISE = 'enterprise', 'Enterprise'
  MENU_QR = 'menu_qr', 'Menú QR'
  MENU_QR_VISUAL = 'menu_qr_visual', 'Menú QR Visual'
  MENU_QR_MARCA = 'menu_qr_marca', 'Menú QR Marca'

  # New Menu QR plans (Lite / Pro / Premium)
  MENU_QR_LITE = 'menu_qr_lite', 'Menú QR Lite'
  MENU_QR_PRO = 'menu_qr_pro', 'Menú QR Pro'
  MENU_QR_PREMIUM = 'menu_qr_premium', 'Menú QR Premium'

  # QR de Reseñas
  QR_REVIEWS = 'qr_reviews', 'QR de Reseñas'
  QR_REVIEWS_BASE = 'qr_reviews_base', 'Reseñas Base'
  QR_REVIEWS_PRO = 'qr_reviews_pro', 'Reseñas Pro'

  # Legacy plans (mantener para compatibilidad)
  START = 'start', 'Start (Legacy)'
  PLUS = 'plus', 'Plus (Legacy)'


class Subscription(models.Model):
  STATUS_CHOICES = [
    ('active', 'Active'),
    ('past_due', 'Past due'),
    ('canceled', 'Canceled'),
  ]

  PRO_MODULE_CHOICES = [
    ('reviews', 'Reseñas de Google'),
    ('tips', 'Propina (Mercado Pago)'),
  ]

  business = models.OneToOneField('business.Business', related_name='subscription', on_delete=models.CASCADE)
  plan = models.CharField(max_length=32, choices=BusinessPlan.choices, default=BusinessPlan.STARTER)
  service = models.CharField(max_length=32, choices=Business.SERVICE_CHOICES, default='gestion')
  status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='active')
  max_branches = models.PositiveIntegerField(default=1, help_text='Sucursales incluidas en el plan base')
  max_seats = models.PositiveIntegerField(default=2, help_text='Usuarios incluidos en el plan base')
  renews_at = models.DateTimeField(null=True, blank=True)
  # Menú QR Pro: módulo incluido elegido por el usuario al contratar
  pro_included_module = models.CharField(
    max_length=16,
    choices=PRO_MODULE_CHOICES,
    null=True,
    blank=True,
    help_text='Solo para plan menu_qr_pro: módulo incluido en el precio base (reviews|tips)',
  )
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

  @property
  def effective_max_branches(self) -> int:
    """Calcula el límite efectivo de sucursales (plan + add-ons)."""
    base = self.max_branches
    extra = sum(
      addon.quantity 
      for addon in self.addons.filter(code='extra_branch', is_active=True)
    )
    
    # Aplicar límites máximos según plan
    max_allowed = self.get_max_addon_branches_allowed()
    if max_allowed is None:
      return base + extra  # Ilimitado
    return min(base + extra, max_allowed)
  
  @property
  def effective_max_seats(self) -> int:
    """Calcula el límite efectivo de usuarios (plan + add-ons)."""
    base = self.max_seats
    extra = sum(
      addon.quantity 
      for addon in self.addons.filter(code='extra_seat', is_active=True)
    )
    return base + extra
  
  def has_addon(self, code: str) -> bool:
    """Verifica si tiene un add-on específico activo."""
    return self.addons.filter(code=code, is_active=True).exists()
  
  def get_max_addon_branches_allowed(self) -> int | None:
    """
    Retorna el máximo de sucursales permitidas por plan.
    None significa ilimitado.
    """
    plan_limits = {
      'start': 1,       # No permite add-ons
      'starter': 1,     # Legacy, no permite add-ons
      'pro': 3,         # Hasta 3 total
      'business': None, # Ilimitado desde la 1ra
      'enterprise': None,
      'plus': None,     # Legacy, ilimitado
      # Menú QR plans
      'menu_qr': 1,
      'menu_qr_visual': 1,
      'menu_qr_marca': 1,
      'menu_qr_lite': 1,    # No permite sucursales extra
      'menu_qr_pro': 1,     # No permite sucursales extra
      'menu_qr_premium': None,  # Ilimitado
    }
    return plan_limits.get(self.plan.lower(), 1)


class SubscriptionAddon(models.Model):
  """
  Add-ons para subscripciones (sucursales extra, usuarios extra, módulos).
  """
  
  ADDON_CODE_CHOICES = [
    ('extra_branch', 'Sucursal Extra'),
    ('extra_seat', 'Usuario Extra'),
    ('invoices_module', 'Módulo de Facturación'),
    # Menú QR Pro add-ons
    ('menu_qr_addon_reviews', 'Módulo Reseñas (Menú QR)'),
    ('menu_qr_addon_tips', 'Módulo Propina (Menú QR)'),
  ]
  
  subscription = models.ForeignKey(
    'business.Subscription',
    related_name='addons',
    on_delete=models.CASCADE
  )
  code = models.CharField(max_length=64, choices=ADDON_CODE_CHOICES)
  quantity = models.PositiveIntegerField(default=1, help_text='Cantidad de unidades (ej: 2 sucursales extra)')
  is_active = models.BooleanField(default=True)
  activated_at = models.DateTimeField(auto_now_add=True)
  deactivated_at = models.DateTimeField(null=True, blank=True)
  
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
  
  class Meta:
    verbose_name = 'Subscription Add-on'
    verbose_name_plural = 'Subscription Add-ons'
    unique_together = ('subscription', 'code')
  
  def __str__(self) -> str:
    status = "✓" if self.is_active else "✗"
    return f"{status} {self.get_code_display()} x{self.quantity} · {self.subscription.business.name}"


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
    storage=public_media_storage,
    help_text='Logo horizontal para encabezados de documentos'
  )
  logo_square = models.ImageField(
    upload_to='business/logos/',
    null=True,
    blank=True,
    storage=public_media_storage,
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
