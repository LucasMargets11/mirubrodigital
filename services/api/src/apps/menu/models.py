from __future__ import annotations

import uuid

from django.db import models
from django.utils.text import slugify


# ---------------------------------------------------------------------------
# Engagement: tips + reviews modes
# ---------------------------------------------------------------------------

class TipsModeChoices(models.TextChoices):
    MP_LINK = 'mp_link', 'MP Link (Fase 1)'
    MP_QR_IMAGE = 'mp_qr_image', 'MP QR Image (Fase 1)'
    MP_OAUTH_CHECKOUT = 'mp_oauth_checkout', 'MP OAuth Checkout (Fase 2)'


class MenuCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey('business.Business', related_name='menu_categories', on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'name']
        indexes = [
            models.Index(fields=['business', 'position']),
            models.Index(fields=['business', 'is_active']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['business', 'name'], name='menu_category_unique_name_per_business'),
        ]

    def __str__(self) -> str:  # pragma: no cover - representational helper
        return f"Categoria · {self.name} ({self.business_id})"


class MenuItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey('business.Business', related_name='menu_items', on_delete=models.CASCADE)
    category = models.ForeignKey(
        MenuCategory,
        related_name='items',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sku = models.CharField(max_length=64, blank=True)
    tags = models.CharField(max_length=255, blank=True)
    is_available = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)
    estimated_time_minutes = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='menu/items/', blank=True, null=True)
    image_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'name']
        indexes = [
            models.Index(fields=['business', 'is_available']),
            models.Index(fields=['business', 'category']),
            models.Index(fields=['business', 'is_featured']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['business', 'sku'],
                name='menu_item_unique_sku_per_business',
                condition=~models.Q(sku=''),
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - representational helper
        return f"Item · {self.name} ({self.business_id})"

    @property
    def tag_list(self) -> list[str]:
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(',') if tag.strip()]

    @property
    def image_url_value(self) -> str | None:
        if self.image:
            return self.image.url
        return None


class PublicMenuConfig(models.Model):
    business = models.OneToOneField('business.Business', related_name='public_menu_config', on_delete=models.CASCADE)
    enabled = models.BooleanField(default=False)
    slug = models.SlugField(unique=True, max_length=50, db_index=True)
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    brand_name = models.CharField(max_length=120)
    logo_url = models.URLField(blank=True, null=True)
    theme_json = models.JSONField(default=dict, blank=True)
    template_key = models.CharField(max_length=50, default="default_v1")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"PublicConfig: {self.slug} ({self.business.name})"


class MenuBrandingSettings(models.Model):
    business = models.OneToOneField('business.Business', related_name='menu_branding', on_delete=models.CASCADE)
    display_name = models.CharField(max_length=140)
    logo_image = models.ImageField(upload_to='menu/branding/logos/', blank=True, null=True)
    palette_primary = models.CharField(max_length=7, default='#4C1D95')
    palette_secondary = models.CharField(max_length=7, default='#F97316')
    palette_background = models.CharField(max_length=7, default='#0F172A')
    palette_text = models.CharField(max_length=7, default='#F8FAFC')
    font_heading = models.CharField(max_length=64, default='playfair_display')
    font_body = models.CharField(max_length=64, default='inter')
    font_scale_heading = models.DecimalField(max_digits=4, decimal_places=2, default=1.25)
    font_scale_body = models.DecimalField(max_digits=4, decimal_places=2, default=1.00)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:  # pragma: no cover - representational helper
        return f"Branding · {self.business_id}"

    @property
    def logo_url(self) -> str | None:
        if self.logo_image:
            return self.logo_image.url
        return None


def ensure_public_menu_config(business):
    if business is None:
        raise ValueError('Business is required')
    config, _ = PublicMenuConfig.objects.get_or_create(
        business=business,
        defaults={
            'slug': _generate_menu_slug(business),
            'brand_name': business.name,
        },
    )
    return config


def ensure_menu_branding(business):
    if business is None:
        raise ValueError('Business is required')
    branding, _ = MenuBrandingSettings.objects.get_or_create(
        business=business,
        defaults={'display_name': business.name},
    )
    return branding


def _generate_menu_slug(business):
    base_slug = slugify(business.name) or f'biz-{str(business.id)[:8]}'
    slug = base_slug[:45]
    counter = 1
    while PublicMenuConfig.objects.filter(slug=slug).exists():
        slug = f"{base_slug[:40]}-{counter}"
        counter += 1
    return slug


# ---------------------------------------------------------------------------
# MenuEngagementSettings — tips + reviews configuration per business
# ---------------------------------------------------------------------------

class MenuEngagementSettings(models.Model):
    business = models.OneToOneField(
        'business.Business',
        related_name='menu_engagement_settings',
        on_delete=models.CASCADE,
    )
    # Tips
    tips_enabled = models.BooleanField(default=False)
    tips_mode = models.CharField(
        max_length=20,
        choices=TipsModeChoices.choices,
        default=TipsModeChoices.MP_LINK,
    )
    mp_tip_url = models.URLField(blank=True, null=True, help_text='Link de Mercado Pago para propinas (Fase 1)')
    mp_qr_image = models.ImageField(
        upload_to='menu/tips/qr/',
        blank=True,
        null=True,
        help_text='Imagen QR de Mercado Pago (Fase 1)',
    )
    # Reviews
    reviews_enabled = models.BooleanField(default=False)
    google_place_id = models.CharField(max_length=255, blank=True, null=True)
    google_review_url = models.URLField(blank=True, null=True, help_text='URL directa de reseña de Google (fallback si no hay place_id)')
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Menu Engagement Settings'
        verbose_name_plural = 'Menu Engagement Settings'

    def __str__(self) -> str:  # pragma: no cover
        return f"EngagementSettings · {self.business_id}"

    @property
    def google_write_review_url(self) -> str | None:
        """Returns the best Google write-review URL: place_id preferred, URL fallback."""
        place_id = (self.google_place_id or '').strip()
        if place_id:
            return f"https://search.google.com/local/writereview?placeid={place_id}"
        return self.google_review_url or None


# ---------------------------------------------------------------------------
# MercadoPagoConnection — per-business OAuth (Fase 2)
# ---------------------------------------------------------------------------

class MercadoPagoConnection(models.Model):
    STATUS_CHOICES = [
        ('connected', 'Connected'),
        ('expired', 'Expired'),
        ('revoked', 'Revoked'),
        ('error', 'Error'),
    ]

    business = models.OneToOneField(
        'business.Business',
        related_name='mp_connection',
        on_delete=models.CASCADE,
    )
    access_token = models.CharField(max_length=512)
    refresh_token = models.CharField(max_length=512, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    mp_user_id = models.CharField(max_length=128, blank=True)
    scope = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='connected')
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:  # pragma: no cover
        return f"MPConnection · {self.business_id} ({self.status})"


# ---------------------------------------------------------------------------
# TipTransaction — one tip payment attempt (Fase 2)
# ---------------------------------------------------------------------------

class TipTransaction(models.Model):
    STATUS_CHOICES = [
        ('created', 'Created'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        'business.Business',
        related_name='tip_transactions',
        on_delete=models.CASCADE,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default='ARS')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='created')
    provider = models.CharField(max_length=32, default='mercadopago')
    mp_preference_id = models.CharField(max_length=128, blank=True, null=True)
    mp_payment_id = models.CharField(max_length=128, blank=True, null=True)
    # Stable unique ref sent to MP; format: "TIP-{uuid}"
    external_reference = models.CharField(max_length=64, unique=True)
    # Context
    menu_slug = models.CharField(max_length=50, blank=True)
    table_ref = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['business', 'created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['external_reference']),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Tip · {self.external_reference} · {self.status}"


# ---------------------------------------------------------------------------
# MenuLayoutBlock — template-driven carta layout per business
# ---------------------------------------------------------------------------

class LayoutTemplateChoices(models.TextChoices):
    DRINKS_FIRST = 'drinks_first', 'Bebidas primero'
    FOOD_FIRST = 'food_first', 'Comida primero'
    CUSTOM = 'custom', 'Personalizado'


class BlockLayoutChoices(models.TextChoices):
    STACK = 'stack', 'Lista (stack)'
    GRID = 'grid', 'Cuadrícula (grid)'


class MenuLayoutBlock(models.Model):
    """An ordered section of the public menu (e.g. "Bebidas", "Comida", "Postres")."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        'business.Business',
        related_name='menu_layout_blocks',
        on_delete=models.CASCADE,
    )
    title = models.CharField(max_length=120)
    position = models.PositiveIntegerField(default=0)
    layout = models.CharField(
        max_length=16,
        choices=BlockLayoutChoices.choices,
        default=BlockLayoutChoices.STACK,
    )
    columns_desktop = models.PositiveSmallIntegerField(default=3)
    columns_tablet = models.PositiveSmallIntegerField(default=2)
    columns_mobile = models.PositiveSmallIntegerField(default=1)
    badge_text = models.CharField(max_length=80, blank=True)
    categories = models.ManyToManyField(
        MenuCategory,
        through='MenuLayoutBlockCategory',
        related_name='layout_blocks',
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'title']
        indexes = [
            models.Index(fields=['business', 'position']),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Block · {self.title} ({self.business_id})"


class MenuLayoutBlockCategory(models.Model):
    """Ordered M2M through model: category inside a layout block."""
    block = models.ForeignKey(MenuLayoutBlock, related_name='block_categories', on_delete=models.CASCADE)
    category = models.ForeignKey(MenuCategory, related_name='block_memberships', on_delete=models.CASCADE)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'category__name']
        unique_together = [('block', 'category')]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.block.title} → {self.category.name}"


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def ensure_menu_engagement(business) -> MenuEngagementSettings:
    """Get-or-create MenuEngagementSettings for a business."""
    if business is None:
        raise ValueError('Business is required')
    obj, _ = MenuEngagementSettings.objects.get_or_create(business=business)
    return obj
