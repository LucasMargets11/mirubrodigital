from __future__ import annotations

import uuid

from django.db import models


class ReviewConfig(models.Model):
    """Per-business configuration for the QR de Reseñas product."""

    business = models.OneToOneField(
        'business.Business',
        related_name='review_config',
        on_delete=models.CASCADE,
    )
    enabled = models.BooleanField(default=False)
    google_place_id = models.CharField(max_length=255, blank=True, default='')
    google_review_url = models.URLField(blank=True, default='')
    custom_redirect_url = models.URLField(blank=True, default='')
    redirect_threshold = models.PositiveSmallIntegerField(
        default=4,
        help_text='Ratings >= this value trigger external redirect instead of internal feedback.',
    )
    collect_contact = models.BooleanField(default=False)
    thank_you_message = models.CharField(
        max_length=500,
        blank=True,
        default='¡Gracias por tu opinión!',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Review Config'
        verbose_name_plural = 'Review Configs'

    def __str__(self) -> str:
        return f"ReviewConfig · {self.business_id}"

    @property
    def redirect_url(self) -> str | None:
        """Best redirect URL with priority: custom > place_id > google_review_url."""
        if self.custom_redirect_url:
            return self.custom_redirect_url
        place_id = (self.google_place_id or '').strip()
        if place_id:
            return f"https://search.google.com/local/writereview?placeid={place_id}"
        if self.google_review_url:
            return self.google_review_url
        return None


class ReviewSource(models.TextChoices):
    QR = 'qr', 'QR Code'
    MENU = 'menu', 'Carta Online'
    DIRECT = 'direct', 'Link directo'


class ReviewStatus(models.TextChoices):
    NEW = 'new', 'Nuevo'
    READ = 'read', 'Leído'
    CONTACTED = 'contacted', 'Contactado'
    RESOLVED = 'resolved', 'Resuelto'


class Review(models.Model):
    """Internal feedback review submitted by a customer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        'business.Business',
        related_name='reviews',
        on_delete=models.CASCADE,
    )
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True, default='')
    contact_info = models.CharField(max_length=255, blank=True, default='')
    source = models.CharField(
        max_length=16,
        choices=ReviewSource.choices,
        default=ReviewSource.QR,
    )
    status = models.CharField(
        max_length=16,
        choices=ReviewStatus.choices,
        default=ReviewStatus.NEW,
    )
    ip_hash = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', '-created_at']),
            models.Index(fields=['business', 'status']),
            models.Index(fields=['business', 'rating']),
        ]

    def __str__(self) -> str:
        return f"Review {self.id} · {self.business_id} · {self.rating}★"


class ReviewVisit(models.Model):
    """Tracks page visits to the public review landing page."""

    business = models.ForeignKey(
        'business.Business',
        related_name='review_visits',
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['business', '-created_at']),
        ]

    def __str__(self) -> str:
        return f"ReviewVisit · {self.business_id} · {self.created_at}"
