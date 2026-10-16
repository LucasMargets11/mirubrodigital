from __future__ import annotations


from django.db import models

from .fields import EncryptedTextField

# ---------------------------------------------------------------------------
# MercadoPagoConnection — per-business OAuth connection to a merchant's own
# Mercado Pago account. Generic merchant-side payment infrastructure, shared
# across products (Menu/Tips today, Turnos and others later).
#
# Moved from apps.menu (Slice 5A extraction) without touching the underlying
# table: `db_table` keeps pointing at the original `menu_mercadopagoconnection`
# table, so no data migration was necessary and no rows were touched.
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
    # Encrypted at rest (Fernet, see fields.EncryptedTextField / crypto.py).
    # TextField rather than CharField(max_length=...): ciphertext is longer
    # than the plaintext token it wraps.
    access_token = EncryptedTextField()
    refresh_token = EncryptedTextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    mp_user_id = models.CharField(max_length=128, blank=True)
    scope = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='connected')
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'menu_mercadopagoconnection'

    def __str__(self) -> str:  # pragma: no cover
        return f"MPConnection · {self.business_id} ({self.status})"
