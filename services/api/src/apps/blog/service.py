"""
Blog editorial service — business logic for the admin CMS.

Keeps views thin by centralizing slug generation, status transitions,
validation, scheduled-publish resolution, and preview token generation.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time

from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify

from apps.blog.models import BlogPost

logger = logging.getLogger(__name__)

PREVIEW_TOKEN_MAX_AGE = 3600  # 1 hour


# ── Valid status transitions ──────────────────────────────────────────────────

_VALID_TRANSITIONS: dict[str, set[str]] = {
    'draft':     {'published', 'scheduled', 'archived'},
    'scheduled': {'published', 'draft', 'archived'},
    'published': {'draft', 'archived'},
    'archived':  {'draft'},
}


def is_valid_transition(current: str, target: str) -> bool:
    return target in _VALID_TRANSITIONS.get(current, set())


# ── Slug ──────────────────────────────────────────────────────────────────────

def resolve_slug(post: BlogPost, slug_input: str | None = None) -> str:
    """
    If slug_input is provided and unique, use it.
    Otherwise auto-generate from the title.
    """
    if slug_input and slug_input.strip():
        candidate = slugify(slug_input)[:270]
        counter = 1
        base = candidate
        while BlogPost.objects.filter(slug=candidate).exclude(pk=post.pk).exists():
            candidate = f'{base[:265]}-{counter}'
            counter += 1
        return candidate
    return post.generate_unique_slug()


# ── Publish / Unpublish ──────────────────────────────────────────────────────

def publish_post(post: BlogPost) -> list[str]:
    """
    Attempt to publish a post. Returns list of validation errors (empty = OK).
    """
    errors = post.validate_for_publish()
    if errors:
        return errors

    post.status = BlogPost.Status.PUBLISHED
    post.published_at = timezone.now()
    post.scheduled_publish_at = None
    post.save(update_fields=['status', 'published_at', 'scheduled_publish_at', 'updated_at'])
    return []


def unpublish_post(post: BlogPost) -> None:
    post.status = BlogPost.Status.DRAFT
    post.save(update_fields=['status', 'updated_at'])


def archive_post(post: BlogPost) -> None:
    post.status = BlogPost.Status.ARCHIVED
    post.save(update_fields=['status', 'updated_at'])


def schedule_post(post: BlogPost, publish_at) -> list[str]:
    """Schedule a post for future publication."""
    errors = post.validate_for_publish()
    if errors:
        return errors
    if publish_at <= timezone.now():
        return ['La fecha de publicación programada debe ser futura.']
    post.status = BlogPost.Status.SCHEDULED
    post.scheduled_publish_at = publish_at
    post.save(update_fields=['status', 'scheduled_publish_at', 'updated_at'])
    return []


# ── Scheduled publishing (called by Celery) ──────────────────────────────────

def publish_scheduled_posts() -> int:
    """Publish all posts whose scheduled_publish_at is in the past."""
    now = timezone.now()
    due = BlogPost.objects.filter(
        status=BlogPost.Status.SCHEDULED,
        scheduled_publish_at__lte=now,
    )
    count = 0
    for post in due:
        post.status = BlogPost.Status.PUBLISHED
        post.published_at = now
        post.scheduled_publish_at = None
        post.save(update_fields=['status', 'published_at', 'scheduled_publish_at', 'updated_at'])
        count += 1
        logger.info('Scheduled post published: %s (slug=%s)', post.id, post.slug)
    return count


# ── Preview tokens ────────────────────────────────────────────────────────────

def generate_preview_url(post: BlogPost) -> str | None:
    """Generate a secure, time-limited preview URL for any post."""
    if not post.slug:
        return None
    ts = int(time.time())
    secret = getattr(settings, 'SECRET_KEY', '')
    message = f'blog-preview:{post.id}:{ts}'
    token = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return f'/blog/preview/{post.id}?token={token}&ts={ts}'
