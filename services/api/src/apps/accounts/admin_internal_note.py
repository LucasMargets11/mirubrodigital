"""
Admin Internal Note — generic staff-only observation model.

Allows platform staff to attach internal notes to any entity (Business,
SubscriptionV2, etc.) without exposing them to tenant users.
"""
import uuid

from django.conf import settings
from django.db import models


class AdminInternalNote(models.Model):
    """
    Generic internal note attachable to any entity by target_type + target_id.

    Convention:
      target_type = 'business'          → target_id = Business.pk (int)
      target_type = 'subscription_v2'   → target_id = SubscriptionV2.pk (uuid str)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    target_type = models.CharField(max_length=64, db_index=True)
    target_id = models.CharField(max_length=64, db_index=True)

    body = models.TextField()

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='admin_internal_notes',
        on_delete=models.SET_NULL,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['target_type', 'target_id'], name='admin_note_target_idx'),
        ]

    def __str__(self):
        return f'Note({self.target_type}:{self.target_id}) by {self.author_id}'
