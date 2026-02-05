from __future__ import annotations

import uuid

from django.db import models
from django.utils.text import slugify


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
